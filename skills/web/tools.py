"""Web skill: search + read_url (crawlberg, with blocked-page detection)."""

from __future__ import annotations

from urllib.parse import urlparse

from omen.core.tools import ToolResult, tool

from .blocking import BlockVerdict, assess
from .DuckDuckGoSearch import search as ddg_search
from .page import clean_markdown, fit, rank

READ_BUDGET = 3500  # characters of page text returned to the model (~900 tokens)

_engine = None


def _crawl_engine():
    """One crawlberg engine per process (single page, no crawling)."""
    global _engine
    if _engine is None:
        import crawlberg
        from crawlberg import ContentConfig, CrawlConfig

        _engine = crawlberg.create_engine(
            CrawlConfig(
                max_depth=0,
                max_pages=1,
                soft_http_errors=True,  # return 4xx/5xx so we can classify them
                request_timeout=20_000,
                content=ContentConfig(
                    output_format="markdown",
                    preprocessing_preset="standard",
                    remove_navigation=True,
                    skip_images=True,
                ),
            )
        )
    return _engine


def _get(obj, name, default=None):
    if obj is None:
        return default
    return obj.get(name, default) if isinstance(obj, dict) else getattr(obj, name, default)


@tool
def search(query: str, max_results: int = 5) -> ToolResult:
    """Search the web. Returns titles, links and snippets.

    Args:
        query: A short search query, 3-6 words.
        max_results: How many results (1-8).
    """
    results = ddg_search(query, max_results=min(max(max_results, 1), 8))
    if not results:
        return ToolResult(f"No results for '{query}'.", details={"type": "search_results", "query": query, "results": []})
    lines = [f"{i}. {r.title}\n   {r.link}\n   {r.snippet}" for i, r in enumerate(results, 1)]
    return ToolResult(
        "\n".join(lines),
        details={"type": "search_results", "query": query, "results": [r.to_dict() for r in results]},
    )


@tool(max_chars=READ_BUDGET + 400)
async def read_url(url: str, query: str | None = None) -> ToolResult:
    """Read a web page as clean text. Pass `query` to get only the paragraphs about it.

    Args:
        url: The page address.
        query: Optional: what you are looking for on the page.
    """
    import crawlberg

    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        raw = await crawlberg.scrape(_crawl_engine(), url)
    except Exception as e:  # crawlberg raises RuntimeError("<tag>: <detail>")
        tag = str(e).split(":", 1)[0].strip().lower()
        status = {"timeout": "TIMEOUT", "browser_timeout": "TIMEOUT", "not_found": "NOT_FOUND", "gone": "NOT_FOUND"}.get(
            tag, "BLOCKED" if tag in {"forbidden", "unauthorized", "rate_limited", "waf_blocked"} else "FAILED"
        )
        return ToolResult(f"{status}: {url} ({e}). Try another result.", error="unavailable")

    markdown = _get(raw, "markdown")
    full = _get(markdown, "content") or ""
    text = clean_markdown(_get(markdown, "fit_content") or full)
    metadata = _get(raw, "metadata")
    title = _get(metadata, "title") or urlparse(url).netloc
    final_url = _get(raw, "final_url") or url
    status_code = _get(raw, "status_code")
    verdict = assess(
        status_code=status_code,
        html=_get(raw, "html"),
        extracted_length=len(full),
        title=_get(metadata, "title"),
        retry_after=_get(_get(raw, "response_meta"), "retry_after"),
    )
    details = {
        "type": "link_preview",
        "url": final_url,
        "title": title,
        "description": _get(metadata, "description"),
        "site": urlparse(final_url).netloc,
        "status": status_code,
        "chars": len(text),
    }

    if verdict.verdict == BlockVerdict.NOT_FOUND:
        return ToolResult(f"NOT_FOUND: {final_url} ({verdict.reason}). Try another result.", details=details, error="unavailable")
    if verdict.blocked:
        why = verdict.vendor or verdict.reason
        if _get(raw, "js_render_hint") and len(text) < 200:
            return ToolResult(f"JS_REQUIRED: {final_url} needs a browser. Try another result.", details=details, error="unavailable")
        return ToolResult(f"BLOCKED ({why}): {final_url}. Try another result.", details=details, error="unavailable")
    if not text:
        return ToolResult(f"EMPTY: {final_url} has no readable text. Try another result.", details=details, error="unavailable")

    shown = rank(text, query, READ_BUDGET) if query else fit(text, READ_BUDGET)
    header = f"{title} | {final_url} | showing {len(shown)} of {len(text)} characters"
    if query:
        header += f" most relevant to '{query}'"
    return ToolResult(f"{header}\n\n{shown}", details=details)


TOOLS = [search, read_url]
