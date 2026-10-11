"""Eval runner: runs evals/tasks.yaml against the configured model.

Reports, per task: pass/fail, tool-call validity (calls that weren't unknown
tools or bad arguments), LLM steps and latency. Results are also written to
evals/results/<timestamp>.json so runs can be compared across models and
harness changes.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

import yaml

from evals.tools import EVAL_TOOLS
from omen.config import main_model
from omen.core import Agent, ToolRegistry
from omen.core.events import RunError, RunFinished, StepStarted, ToolCallArgs, ToolCallResult, ToolCallStart
from omen.core.llm import LLM, LiteLLMClient
from omen.core.tools import parse_arguments

HERE = Path(__file__).parent
SYSTEM = (
    "You are a concise personal assistant. Use the tools when they help; "
    "answer in one or two sentences."
)


@dataclass
class TaskResult:
    id: str
    passed: bool
    failures: list[str] = field(default_factory=list)
    calls: list[dict] = field(default_factory=list)
    invalid_calls: int = 0
    steps: int = 0
    seconds: float = 0.0
    answer: str = ""
    finish: str = ""


async def run_task(task: dict, llm: LLM) -> TaskResult:
    agent = Agent(llm, ToolRegistry(EVAL_TOOLS), SYSTEM, max_turns=task.get("max_steps", 4))
    result = TaskResult(id=task["id"], passed=False)
    args_by_id: dict[str, str] = {}
    names_by_id: dict[str, str] = {}
    started = time.perf_counter()

    async for event in agent.run(task["prompt"]):
        if isinstance(event, StepStarted):
            result.steps = event.step
        elif isinstance(event, ToolCallStart):
            names_by_id[event.tool_call_id] = event.name
        elif isinstance(event, ToolCallArgs):
            args_by_id[event.tool_call_id] = event.delta
        elif isinstance(event, ToolCallResult):
            result.calls.append({
                "name": event.name,
                "requested": names_by_id.get(event.tool_call_id),
                "arguments": args_by_id.get(event.tool_call_id, ""),
                "error": event.error,
                "content": event.content[:300],
            })
            if event.error in ("unknown_tool", "invalid_args"):
                result.invalid_calls += 1
        elif isinstance(event, RunError):
            result.failures.append(f"run error: {event.message}")
        elif isinstance(event, RunFinished):
            result.finish = event.reason

    result.seconds = round(time.perf_counter() - started, 2)
    final = [m for m in agent.messages if m["role"] == "assistant" and not m.get("tool_calls")]
    result.answer = (final[-1]["content"] or "") if final else ""
    result.failures += check(task, result)
    result.passed = not result.failures
    return result


def _args(raw: str) -> dict:
    try:
        return parse_arguments(raw)
    except ValueError:
        return {}


def check(task: dict, r: TaskResult) -> list[str]:
    failures = []
    if r.finish != "done":
        failures.append(f"run ended with '{r.finish}'")
    called = [c["name"] for c in r.calls if c["error"] not in ("unknown_tool", "invalid_args")]
    expected = task.get("expect_tools")
    if expected == [] and r.calls:
        failures.append(f"expected no tool calls, got {called}")
    for name in expected or []:
        if name not in called:
            failures.append(f"missing tool call: {name}")
    for name, want in (task.get("expect_args") or {}).items():
        attempts = [_args(c["arguments"]) for c in r.calls if c["name"] == name]
        for key, value in want.items():
            if not any(str(value).lower() in str(a.get(key, "")).lower() for a in attempts):
                failures.append(f"{name}: no call with {key}~'{value}'")
    for needle in task.get("expect_answer", []):
        if str(needle).lower() not in r.answer.lower():
            failures.append(f"answer missing '{needle}'")
    return failures


async def run_suite(only: list[str] | None = None, repeat: int = 1, llm: LLM | None = None) -> int:
    tasks = yaml.safe_load((HERE / "tasks.yaml").read_text())
    if only:
        tasks = [t for t in tasks if t["id"] in only]
    config = main_model()
    llm = llm or LiteLLMClient(config)
    print(f"model: {config.model} @ {config.base_url}   tasks: {len(tasks)} × {repeat}\n")

    results: list[TaskResult] = []
    for task in tasks:
        for _ in range(repeat):
            r = await run_task(task, llm)
            results.append(r)
            mark = "PASS" if r.passed else "FAIL"
            print(f"{mark}  {r.id:<28} steps={r.steps} calls={len(r.calls)} invalid={r.invalid_calls} {r.seconds:>6.2f}s")
            for f in r.failures:
                print(f"      - {f}")

    total_calls = sum(len(r.calls) for r in results)
    invalid = sum(r.invalid_calls for r in results)
    passed = sum(r.passed for r in results)
    validity = 100 * (total_calls - invalid) / total_calls if total_calls else 100.0
    print(
        f"\npassed {passed}/{len(results)}  ·  valid tool calls {validity:.0f}% ({total_calls - invalid}/{total_calls})"
        f"  ·  avg steps {sum(r.steps for r in results) / max(len(results), 1):.1f}"
        f"  ·  avg {sum(r.seconds for r in results) / max(len(results), 1):.1f}s"
    )

    out = HERE / "results" / f"{datetime.now():%Y%m%d-%H%M%S}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"model": config.model, "results": [asdict(r) for r in results]}, indent=2))
    print(f"results: {out}")
    return 0 if passed == len(results) else 1
