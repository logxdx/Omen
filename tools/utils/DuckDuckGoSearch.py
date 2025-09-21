from typing import Literal
from ddgs import DDGS


class SearchResult:
    def __init__(self, title: str, link: str, snippet: str):
        self.title = title
        self.link = link
        self.snippet = snippet

    def __repr__(self) -> str:
        return f"SearchResult(title={self.title}, link={self.link}, snippet={self.snippet})"

    def __str__(self) -> str:
        return f"[{self.title}]({self.link})\nSnippet: {self.snippet}"

    def to_dict(self) -> dict:
        return {"title": self.title, "link": self.link, "snippet": self.snippet}

    def get(self, key, default=None):
        return getattr(self, key, default)


def search(
    query: str,
    category: Literal["text", "news", "images", "videos"] = "text",
    max_results: int = 5,
    region: str = "us-en",
    safesearch: Literal["on", "moderate", "off"] = "moderate",
    timerange: Literal["d", "w", "m", "y"] | None = None,
) -> list[SearchResult]:
    """
    Perform a web search.

    Args:
        query: The search query.
        category: The category of search engines (e.g., 'text', 'news', 'images', 'videos').
        max_results: The maximum number of results to return. Defaults to 5.
        region: The region to use for the search (e.g., us-en, uk-en, etc.).
        safesearch: The safesearch setting (e.g., on, moderate, off).
        timerange: The timerange for the search (e.g., d, w, m, y).
    """

    ddgs = DDGS()

    if category == "text":
        src = ddgs.text(
            query,
            max_results=max_results,
            region=region,
            safesearch=safesearch,
            timelimit=timerange,
        )
    elif category == "news":
        src = ddgs.news(
            query,
            max_results=max_results,
            region=region,
            safesearch=safesearch,
            timelimit=timerange,
        )
    elif category == "images":
        src = ddgs.images(
            query,
            max_results=max_results,
            region=region,
            safesearch=safesearch,
            timelimit=timerange,
        )
    elif category == "videos":
        src = ddgs.videos(
            query,
            max_results=max_results,
            region=region,
            safesearch=safesearch,
            timelimit=timerange,
        )
    results = []
    for s in src:
        results.append(
            SearchResult(title=s["title"], link=s["href"], snippet=s["body"])
        )
    return results


if __name__ == "__main__":

    query = input("🔍 Search query: ")
    results = search(query, max_results=5)
    for result in results:
        print(result)
