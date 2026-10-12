"""Eval runner: runs evals/tasks.yaml against the configured model.

Reports, per task: pass/fail, tool-call validity (calls that weren't unknown
tools or bad arguments), LLM steps and latency. A multi-turn task runs its
turns in one session, so later turns see what the model actually said and did
earlier, and each turn is checked on its own. Results are also written to
evals/results/<timestamp>.json so runs can be compared across models and
harness changes.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

import yaml

import omen  # noqa: F401  (puts the forked SDK on the path before `agents` is imported)
from agents import Agent, Model
from evals.tools import EVAL_TOOLS, lookup_contact, search_notes
from omen.assistant import build_assistant
from omen.config import main_model
from omen.core import Runtime, delegate_tool
from omen.core.events import (
    RunError,
    RunFinished,
    StepStarted,
    TextMessageContent,
    TextMessageEnd,
    ToolCallArgs,
    ToolCallResult,
    ToolCallStart,
)
from omen.core.models import make_model, make_settings

HERE = Path(__file__).parent
SYSTEM = (
    "You are a concise personal assistant. Use the tools when they help; "
    "answer in one or two sentences."
)


@dataclass
class Turn:
    calls: list[dict] = field(default_factory=list)
    invalid_calls: int = 0
    steps: int = 0
    answer: str = ""
    finish: str = ""
    errors: list[str] = field(default_factory=list)


@dataclass
class TaskResult:
    id: str
    passed: bool
    failures: list[str] = field(default_factory=list)
    calls: list[dict] = field(default_factory=list)  # every turn's calls, each tagged with its turn
    invalid_calls: int = 0
    steps: int = 0
    seconds: float = 0.0
    answer: str = ""  # the last turn's
    finish: str = ""  # the last turn's
    answers: list[str] = field(default_factory=list)  # one per turn


async def _auto_answer(question: str, options: list[str] | None) -> str:
    """Stand-in user: confirms yes/no questions, otherwise asks the assistant to proceed."""
    if options and any(o.lower() in ("yes", "y") for o in options):
        return "yes"
    return "I don't know, just do your best."


def _plain(text: str) -> str:
    """Answer text as a reader sees it (markdown emphasis removed)."""
    return text.replace("*", "").replace("`", "").replace("_", "")


def build_omen(task: dict, model: Model, workdir: Path) -> Runtime:
    """The real assistant (all repo skills) in a fresh sandbox and memory under `workdir`."""
    sandbox = workdir / "sandbox"
    for rel, content in (task.get("files") or {}).items():
        (sandbox / rel).parent.mkdir(parents=True, exist_ok=True)
        (sandbox / rel).write_text(content)
    sandbox.mkdir(parents=True, exist_ok=True)
    os.environ["OMEN_SANDBOX"] = str(sandbox)  # read when skills are imported
    assistant = build_assistant(
        model=model,
        memory_path=workdir / "facts.jsonl",
        use_router=task.get("router", True),
    )
    return Runtime.for_assistant(assistant, max_turns=task.get("max_steps", 6), ask_handler=_auto_answer)


def build_agent(task: dict, model: Model) -> Agent:
    settings = make_settings(main_model())
    if task.get("agent") == "delegator":
        researcher = Agent(
            name="researcher",
            handoff_description="Looks things up in the user's notes and contacts.",
            instructions="You look things up with your tools and report exactly what you found.",
            model=model,
            model_settings=settings,
            tools=[search_notes, lookup_contact],
        )
        # 6, not 4: with 4 the researcher often ran out on wordy briefs ("look through the notes…"),
        # which measured the step cap rather than delegation.
        tools = [delegate_tool([researcher], max_turns=6)]
    else:
        tools = EVAL_TOOLS
    return Agent(name="eval", instructions=SYSTEM, model=model, model_settings=settings, tools=tools)


async def run_turn(runtime: Runtime, prompt: str) -> Turn:
    turn = Turn()
    args_by_id: dict[str, str] = {}
    names_by_id: dict[str, str] = {}
    text: list[str] = []
    async for event in runtime.run(prompt):
        if isinstance(event, StepStarted):
            turn.steps += 1
        elif isinstance(event, TextMessageContent):
            text.append(event.delta)
        elif isinstance(event, TextMessageEnd):
            turn.answer, text = "".join(text).strip(), []
        elif isinstance(event, ToolCallStart):
            names_by_id[event.tool_call_id] = event.name
        elif isinstance(event, ToolCallArgs):
            args_by_id[event.tool_call_id] = event.delta
        elif isinstance(event, ToolCallResult):
            turn.calls.append({
                "name": event.name,
                "requested": names_by_id.get(event.tool_call_id),
                "arguments": args_by_id.get(event.tool_call_id, ""),
                "error": event.error,
                "content": event.content[:300],
            })
            if event.error in ("unknown_tool", "invalid_args"):
                turn.invalid_calls += 1
        elif isinstance(event, RunError):
            turn.errors.append(f"run error: {event.message}")
        elif isinstance(event, RunFinished):
            turn.finish = event.reason
    return turn


async def run_task(task: dict, model: Model) -> TaskResult:
    workdir = Path(tempfile.mkdtemp(prefix="omen-eval-"))
    if task.get("agent") == "omen":
        runtime = build_omen(task, model, workdir)
    else:
        runtime = Runtime(build_agent(task, model), max_turns=task.get("max_steps", 4))
    result = TaskResult(id=task["id"], passed=False)
    if task.get("history"):
        await runtime.session.add_items(task["history"])
    turns = task.get("turns") or [task]
    max_steps = runtime.max_turns
    started = time.perf_counter()

    for n, spec in enumerate(turns, 1):
        runtime.max_turns = spec.get("max_steps", max_steps)
        turn = await run_turn(runtime, spec["prompt"])
        result.calls += [{**c, "turn": n} for c in turn.calls]
        result.invalid_calls += turn.invalid_calls
        result.steps += turn.steps
        result.answers.append(turn.answer)
        result.answer, result.finish = turn.answer, turn.finish
        prefix = f"turn {n}: " if len(turns) > 1 else ""
        result.failures += [prefix + f for f in turn.errors + check(spec, turn)]

    result.seconds = round(time.perf_counter() - started, 2)
    for rel, needles in (task.get("expect_files") or {}).items():
        path = workdir / "sandbox" / rel
        if not path.exists():
            result.failures.append(f"file {rel} was not created")
            continue
        content = path.read_text().lower()
        for needle in needles if isinstance(needles, list) else [needles]:
            if str(needle).lower() not in content:
                result.failures.append(f"file {rel} lacks '{needle}'")
    shutil.rmtree(workdir, ignore_errors=True)
    result.passed = not result.failures
    return result


def _args(raw: str) -> dict:
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _flag(args: dict, key: str) -> bool:
    return str(args.get(key)).lower() == "true"


def check(task: dict, r: Turn) -> list[str]:
    """Failures of one turn against its expectations (a single-turn task is its own turn)."""
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
    answer = _plain(r.answer).lower()
    for needle in task.get("expect_answer", []):
        if str(needle).lower() not in answer:
            failures.append(f"answer missing '{needle}'")
    needle = task.get("expect_context_passed")
    if needle:
        delegations = [_args(c["arguments"]) for c in r.calls if c["name"] == "delegate"]
        passed = any(
            _flag(a, "share_context") or str(needle).lower() in str(a.get("task", "")).lower()
            for a in delegations
        )
        if not passed:
            failures.append(f"delegate got neither share_context nor '{needle}' in the task")
    any_of = task.get("expect_answer_any") or []
    if any_of and not any(str(n).lower() in answer for n in any_of):
        failures.append(f"answer has none of {any_of}")
    return failures


async def run_suite(only: list[str] | None = None, repeat: int = 1, model: Model | None = None) -> int:
    tasks = yaml.safe_load((HERE / "tasks.yaml").read_text())
    if only:
        tasks = [t for t in tasks if t["id"] in only]
    if not os.environ.get("OMEN_EVAL_NETWORK"):
        tasks = [t for t in tasks if not t.get("network")]  # live web/weather tasks are opt-in
    config = main_model()
    model = model or make_model(config)
    print(f"model: {config.model} @ {config.base_url}   tasks: {len(tasks)} × {repeat}\n")

    results: list[TaskResult] = []
    for task in tasks:
        for _ in range(repeat):
            r = await run_task(task, model)
            results.append(r)
            mark = "PASS" if r.passed else "FAIL"
            turns = f" turns={len(r.answers)}" if len(r.answers) > 1 else ""
            print(
                f"{mark}  {r.id:<28} steps={r.steps} calls={len(r.calls)} invalid={r.invalid_calls}"
                f" {r.seconds:>6.2f}s{turns}"
            )
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
    delegations = [_args(c["arguments"]) for r in results for c in r.calls if c["name"] == "delegate"]
    if delegations:  # how often the model shares the conversation / continues a specialist's thread itself
        shared = sum(_flag(a, "share_context") for a in delegations)
        follow = sum(_flag(a, "follow_up") for a in delegations)
        asked = sum(" paused to ask: " in c["content"] for r in results for c in r.calls if c["name"] == "delegate")
        print(
            f"delegations {len(delegations)}  ·  share_context {shared}/{len(delegations)}"
            f"  ·  follow_up {follow}/{len(delegations)}  ·  specialist questions {asked}"
        )
    print(f"results: {out}")
    return 0 if passed == len(results) else 1
