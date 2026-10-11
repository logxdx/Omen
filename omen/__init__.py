"""Omen: a personal assistant built for small local models."""

import sys
from pathlib import Path

# Prefer the vendored, forked Agents SDK. After `uv sync` the same directory is installed in
# editable mode (pyproject [tool.uv.sources]); until then this keeps `python -m omen` working.
_FORK = Path(__file__).resolve().parent.parent / "vendor" / "openai-agents" / "src"
if _FORK.is_dir() and "agents" not in sys.modules and str(_FORK) not in sys.path:
    sys.path.insert(0, str(_FORK))
