"""型付きの外部データモデル。"""

from typing import TypedDict


class SiteRecord(TypedDict, total=False):
    entityId: str
    id: str
    entityTitle: str
    title: str


class ResourceRecord(TypedDict):
    url: str
    name: str
    relative_path: str
    type: str
    size: int | str | None
