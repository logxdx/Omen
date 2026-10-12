"""Does a per-call tail block break llama.cpp prompt-cache reuse? (Phase 9 gate)

    python -m evals.cache_tail            # against OLLAMA_BASE_URL (default localhost:11434)

Omen's prompts are append-only: each request is the previous request (prompt + the model's
output) plus new text, so the server reuses its whole cache. A tail block that is re-sent on
every call but never stored breaks that: the next request drops the old tail. This measures how
many prompt tokens the server must re-evaluate for the second request in two layouts:

  A  append-only (today):  req1 = P + T1 -> G1;  req2 = P + T1 + G1 + R
  B  ephemeral tail:       req1 = P + T1 -> G1;  req2 = P + G1 + R + T2

On a plain transformer B costs ~len(G1 + R + T2). On a hybrid model (ling3: recurrent KDA layers
that can't be rewound to any position) it can cost far more, depending on context checkpoints.
Each case uses a different slice of text so the cases can't reuse each other's cache.
"""

from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1").removesuffix("/v1")


def post(path: str, body: dict) -> dict:
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read())


def tok(text: str) -> list[int]:
    return post("/tokenize", {"content": text, "add_special": False})["tokens"]


def complete(tokens: list[int], n: int = 40) -> tuple[int, str]:
    r = post("/completion", {"prompt": tokens, "n_predict": n, "temperature": 0, "cache_prompt": True, "ignore_eos": True})
    return r["timings"]["prompt_n"], r["content"]


def main() -> None:
    text = "\n\n".join(p.read_text(errors="ignore") for p in sorted((ROOT / "omen").rglob("*.py")))
    corpus = tok(text + "\n\n" + (ROOT / "plan.md").read_text())
    cases = [("A append-only", 6000), ("B ephemeral tail", 6000), ("A append-only", 20000), ("B ephemeral tail", 20000)]
    need = sum(size for _, size in cases)
    if len(corpus) < need:
        corpus = (corpus * (need // len(corpus) + 1))[:need]
    offset = 0
    for label, size in cases:
        p = corpus[offset : offset + size]
        offset += size
        t1, t2 = tok("\n[goal: answer the user's question | step 1 of 50]\n"), tok("\n[goal: answer the user's question | step 2 of 50]\n")
        r = tok("\nTool result: 42 files found.\n")
        n1, out = complete(p + t1)
        g1 = tok(out)
        req2 = p + t1 + g1 + r if label.startswith("A") else p + g1 + r + t2
        n2, _ = complete(req2)
        print(f"{label:18s} {size:6d}-token prefix: req2 re-evaluated {n2:6d} of {len(req2)} tokens (req1: {n1})")


if __name__ == "__main__":
    main()
