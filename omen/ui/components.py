"""UI components: the single source of truth for what frontends render.

Every tool can return `ToolResult(details={"type": ..., ...})`; `payload()` validates
those details into a `UIPayload`:

    {"type": "weather", "version": 1, "valid": true, "props": {...}, "text": "Pune: 26°C ..."}

`text` is the plain fallback (voice, markdown clients, unknown types). A payload
whose props don't validate is still delivered, with `valid: false`, so a frontend
can fall back to `text` instead of rendering broken props. `json_schema()` exports
all component schemas for the web frontend's TypeScript types.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any, Literal, Union, get_args

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, model_validator

logger = logging.getLogger(__name__)
VERSION = 1


class Component(BaseModel):
    model_config = ConfigDict(extra="ignore")


# -- from tool results -------------------------------------------------------


class ForecastDay(BaseModel):
    date: str
    min_c: int
    max_c: int


class Weather(Component):
    type: Literal["weather"]
    place: str
    temp_c: int
    condition: str
    feels_like_c: int | None = None
    humidity: int | None = None
    wind_kmph: int | None = None
    observed: str | None = None
    forecast: list[ForecastDay] = []


class LinkPreview(Component):
    type: Literal["link_preview"]
    url: str
    title: str
    description: str | None = None
    site: str | None = None
    status: int | None = None
    chars: int | None = None


class SearchHit(BaseModel):
    title: str
    link: str
    snippet: str = ""


class SearchResults(Component):
    type: Literal["search_results"]
    query: str
    results: list[SearchHit] = []


class Video(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: str | None = None
    url: str | None = None
    channel: str | None = None
    duration: str | None = None


class VideoResults(Component):
    type: Literal["video_results"]
    query: str
    results: list[Video] = []


class FileView(Component):
    type: Literal["file"]
    path: str
    start: int
    end: int
    total_lines: int


class FileList(Component):
    type: Literal["file_list"]
    path: str
    entries: list[str] = []


class FileWrite(Component):
    type: Literal["file_write"]
    path: str
    created: bool | None = None


class FileDelete(Component):
    type: Literal["file_delete"]
    path: str


class Diff(Component):
    type: Literal["diff"]
    path: str
    before: str
    after: str


class Grep(Component):
    type: Literal["grep"]
    pattern: str
    matches: list[str] = []


class Choice(Component):
    type: Literal["choice"]
    question: str
    options: list[str] | None = None
    answer: str | None = None


class Delegation(Component):
    type: Literal["delegation"]
    persona: str
    task: str
    shared_context: bool = False
    branch: str | None = None
    steps: int = 0


class MemorySaved(Component):
    type: Literal["memory_saved"]
    fact: str


class SkillLoaded(Component):
    type: Literal["skill_loaded"]
    skill: str


class Download(Component):
    type: Literal["download"]
    kind: str
    url: str


# -- composed from assistant text (rules or the extractor model) -------------------


class Table(Component):
    type: Literal["table"]
    title: str | None = None
    columns: list[str] = Field(max_length=12)
    rows: list[list[str]] = Field(max_length=50)


class Chart(Component):
    type: Literal["chart"]
    title: str | None = None
    kind: Literal["bar", "line"] = "bar"
    labels: list[str] = Field(max_length=30, description="One label per value: the item, category or date each number belongs to.")
    values: list[float] = Field(max_length=30, description="The numbers, in the same order as labels.")

    @model_validator(mode="after")
    def _one_label_per_value(self) -> "Chart":
        if len(self.labels) != len(self.values):
            raise ValueError(f"{len(self.labels)} labels for {len(self.values)} values; give one label per value")
        return self


class Card(Component):
    type: Literal["card"]
    title: str
    body: str
    url: str | None = None


_CLASSES: tuple[type[Component], ...] = (
    Weather, LinkPreview, SearchResults, VideoResults, FileView, FileList, FileWrite, FileDelete,
    Diff, Grep, Choice, Delegation, MemorySaved, SkillLoaded, Download, Table, Chart, Card,
)
AnyComponent = Annotated[Union[_CLASSES], Field(discriminator="type")]  # type: ignore[valid-type]
_ADAPTER: TypeAdapter = TypeAdapter(AnyComponent)
TYPES: dict[str, type[Component]] = {get_args(cls.model_fields["type"].annotation)[0]: cls for cls in _CLASSES}
# Components the extractor model can fill from assistant text (flat, small schemas).
EXTRACTABLE = {"table": Table, "chart": Chart, "card": Card}


class UIPayload(BaseModel):
    type: str
    version: int = VERSION
    valid: bool = True
    props: dict[str, Any]
    text: str


def payload(details: Any, text: str) -> UIPayload | None:
    """Validate tool/extractor `details` into a UIPayload (None if there are no details)."""
    if not isinstance(details, dict) or "type" not in details:
        return None
    kind = str(details["type"])
    try:
        component = _ADAPTER.validate_python(details)
        props = component.model_dump(exclude={"type"}, exclude_none=True)
        return UIPayload(type=kind, props=props, text=text)
    except ValidationError as e:
        if kind in TYPES:
            logger.warning("invalid %s component: %s", kind, e.errors()[:2])
        props = {k: v for k, v in details.items() if k != "type"}
        return UIPayload(type=kind, valid=False, props=props, text=text)


def json_schema() -> dict:
    """JSON Schema for UIPayload and every component's props (for TypeScript generation)."""
    return {
        "payload": UIPayload.model_json_schema(),
        "components": {name: cls.model_json_schema() for name, cls in TYPES.items()},
        "version": VERSION,
    }
