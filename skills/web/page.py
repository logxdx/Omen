"""Turn crawlberg markdown into short, clean text a small model can use."""

from __future__ import annotations

import math
import re
from collections import Counter

# "canonical: ...", "meta-og:title: ...", "title: ..." lines crawlberg puts before the content.
_META_LINE = re.compile(r"^[\w:.-]+: .*$")
# [text](url "title") and ![alt](src), allowing one level of parentheses inside the url.
_LINK = re.compile(r"!?\[([^\]]*)\]\((?:[^()\s]|\([^()]*\))*(?:\s+\"[^\"]*\")?\)")
_STOPWORDS = set(
    "a an and are as at be by do for from has have how i in is it of on or that the this to was "
    "what when where which who why with you your".split()
)


def strip_metadata_block(text: str) -> str:
    lines = text.splitlines()
    i = 0
    while i < len(lines) and _META_LINE.match(lines[i]):
        i += 1
    if i and (i == len(lines) or not lines[i].strip()):
        return "\n".join(lines[i:]).lstrip("\n")
    return text


def clean_markdown(text: str) -> str:
    """Drop metadata, link-only lines (nav, language lists) and link targets; keep the text."""
    out = []
    for line in strip_metadata_block(text).splitlines():
        stripped = line.strip()
        if _LINK.search(stripped) and not _LINK.sub("", stripped).strip(" -*•|>.,;:()[]"):
            continue
        if stripped in ("[ ]", "[x]"):
            continue
        out.append(_LINK.sub(lambda m: m.group(1), line).rstrip())
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


def paragraphs(text: str) -> list[str]:
    """Blank-line separated blocks; a heading is kept with the block that follows it."""
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    merged: list[str] = []
    for block in blocks:
        if merged and merged[-1].lstrip().startswith("#") and "\n" not in merged[-1]:
            merged[-1] = f"{merged[-1]}\n{block}"
        else:
            merged.append(block)
    return merged


def _terms(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _STOPWORDS and len(w) > 1]


def rank(text: str, query: str, budget: int) -> str:
    """The paragraphs most relevant to `query` (BM25-style), up to `budget` chars, in page order."""
    paras = paragraphs(text)
    terms = set(_terms(query))
    if not paras or not terms:
        return fit(text, budget)
    docs = [Counter(_terms(p)) for p in paras]
    avg_len = sum(sum(d.values()) for d in docs) / len(docs) or 1
    df = Counter(t for d in docs for t in terms if t in d)
    scores = []
    for i, d in enumerate(docs):
        length = sum(d.values()) or 1
        score = 0.0
        for t in terms:
            if t in d:
                idf = math.log(1 + (len(docs) - df[t] + 0.5) / (df[t] + 0.5))
                score += idf * d[t] * 2.2 / (d[t] + 1.2 * (0.25 + 0.75 * length / avg_len))
        scores.append((score, i))
    chosen, used = [], 0
    ranked = sorted(scores, reverse=True)
    threshold = ranked[0][0] * 0.35  # weak matches (only common words) are noise
    for score, i in ranked:
        if score <= 0 or score < threshold:
            break
        if used + len(paras[i]) > budget and chosen:
            continue
        chosen.append(i)
        used += len(paras[i]) + 2
        if used >= budget:
            break
    if not chosen:
        return fit(text, budget)
    return fit("\n\n".join(paras[i] for i in sorted(chosen)), budget)


def fit(text: str, budget: int) -> str:
    if len(text) <= budget:
        return text
    cut = text[:budget]
    end = max(cut.rfind("\n\n"), cut.rfind(". "))
    return cut[: end + 1] if end > budget * 0.6 else cut
