"""
OmniSearch Search API
"""

import requests
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import List

from browserforge.headers import HeaderGenerator

BASE_URL = "http://localhost:8087/search"


@dataclass
class SearchResult:
    title: str
    desc: str
    url: str

    def __str__(self) -> str:
        return f"Title: {self.title}\nSnippet: {self.desc}\nURL: {self.url}"


class OmniSearchHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.results: List[SearchResult] = []

        self._in_result = False
        self._result_div_depth = 0
        self._capture_title = False
        self._capture_desc = False

        self._current_title = ""
        self._current_desc = ""
        self._current_url = ""

    @staticmethod
    def _attr_dict(attrs: list[tuple[str, str | None]]) -> dict[str, str]:
        return {k: (v or "") for k, v in attrs}

    @staticmethod
    def _has_class(class_value: str, expected: str) -> bool:
        return expected in class_value.split()

    @staticmethod
    def _append_text(current: str, fragment: str) -> str:
        text = fragment.strip()
        if not text:
            return current
        if not current:
            return text
        return f"{current} {text}"

    def _reset_current(self) -> None:
        self._current_title = ""
        self._current_desc = ""
        self._current_url = ""

    def _finalize_current(self) -> None:
        if self._current_url or self._current_title or self._current_desc:
            self.results.append(
                SearchResult(
                    title=self._current_title,
                    desc=self._current_desc,
                    url=self._current_url,
                )
            )
        self._reset_current()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = self._attr_dict(attrs)
        class_value = attr.get("class", "")

        if not self._in_result:
            if tag == "div" and self._has_class(class_value, "result"):
                self._in_result = True
                self._result_div_depth = 1
                self._reset_current()
            return

        if tag == "div":
            self._result_div_depth += 1

        if tag == "a":
            is_cached = self._has_class(class_value, "cached")
            href = attr.get("href", "")
            if not is_cached and not self._current_url and href:
                self._current_url = href
                self._capture_title = True

        if tag == "p" and self._has_class(class_value, "desc"):
            self._capture_desc = True

    def handle_endtag(self, tag: str) -> None:
        if not self._in_result:
            return

        if tag == "a" and self._capture_title:
            self._capture_title = False

        if tag == "p" and self._capture_desc:
            self._capture_desc = False

        if tag == "div":
            self._result_div_depth -= 1
            if self._result_div_depth <= 0:
                self._in_result = False
                self._result_div_depth = 0
                self._capture_title = False
                self._capture_desc = False
                self._finalize_current()

    def handle_data(self, data: str) -> None:
        if self._capture_title:
            self._current_title = self._append_text(self._current_title, data)
        elif self._capture_desc:
            self._current_desc = self._append_text(self._current_desc, data)


def search(
    query: str,
    base_url: str = BASE_URL,
    engine: str = "all",
    page: int = 1,
) -> List[SearchResult]:
    base = base_url.rstrip("/") + "/"

    params = {"q": query, "engine": engine}
    if page > 1:
        params["p"] = str(page)

    headers = HeaderGenerator().generate()

    response = requests.get(
        base,
        params=params,
        headers=headers,
    )
    response.raise_for_status()

    html = response.text
    parser = OmniSearchHTMLParser()
    parser.feed(html)
    return parser.results


def main() -> None:

    query = input("Enter search query: ")

    results = search(query)

    print()
    print(
        f"\n\n{chr(10)}".join(f"{idx}. {r}" for idx, r in enumerate(results, start=1))
    )


if __name__ == "__main__":
    main()
