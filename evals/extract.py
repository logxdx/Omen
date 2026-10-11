"""Extractor eval: field accuracy of the JSON model that fills UI components (evals/extract_tasks.yaml)."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import yaml

import omen  # noqa: F401  (forked SDK on the path)
from omen.config import extractor_model
from omen.ui.extract import Extractor

HERE = Path(__file__).parent


def check(expect: dict[str, Any], props: dict[str, Any]) -> list[str]:
    failures = []
    for key, want in expect.items():
        got = props.get(key)
        if want is None:
            if got not in (None, ""):
                failures.append(f"{key}: expected nothing, got {got!r}")
        elif isinstance(want, list):
            if not isinstance(got, list) or len(got) != len(want):
                failures.append(f"{key}: expected {len(want)} items, got {got!r}")
            elif any(not _same(w, g) for w, g in zip(want, got)):
                failures.append(f"{key}: expected {want}, got {got}")
        elif not _same(want, got):
            failures.append(f"{key}: expected ~{want!r}, got {got!r}")
    return failures


def _same(want: Any, got: Any) -> bool:
    if isinstance(want, (int, float)) and not isinstance(want, bool):
        try:
            return abs(float(got) - float(want)) < 1e-6
        except (TypeError, ValueError):
            return False
    return str(want).lower() in str(got or "").lower()


async def run_extract_suite(extractor: Extractor | None = None, repeat: int = 1) -> int:
    tasks = yaml.safe_load((HERE / "extract_tasks.yaml").read_text())
    extractor = extractor or Extractor()
    config = extractor_model()
    print(f"extractor: {config.model} @ {config.base_url}   tasks: {len(tasks)} × {repeat}\n")
    passed = total = 0
    for task in tasks:
        for _ in range(repeat):
            total += 1
            started = time.perf_counter()
            result = await extractor.extract(task["kind"], task["context"])
            seconds = time.perf_counter() - started
            failures = ["no component"] if result is None else check(task["expect"], result.props)
            passed += not failures
            print(f"{'PASS' if not failures else 'FAIL'}  {task['id']:<24} {seconds:>5.2f}s")
            for f in failures:
                print(f"      - {f}")
    print(f"\npassed {passed}/{total}")
    return 0 if passed == total else 1
