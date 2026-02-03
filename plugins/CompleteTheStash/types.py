"""Type definitions for CompleteTheStash plugin."""
from typing import Any, TypedDict


class StashId(TypedDict):
    """Stash ID with endpoint."""
    stash_id: str
    endpoint: str


class Scene(TypedDict, total=False):
    """Scene data structure."""
    id: int
    title: str
    stash_ids: list[StashId]
    details: str
    url: str
    studio_id: int
    performer_ids: list[int]
    tag_ids: list[int]
    cover_image: str | None
    date: str | None
    code: str | None


class Performer(TypedDict, total=False):
    """Performer data structure."""
    id: int
    name: str
    stash_ids: list[StashId]
    gender: str
    tags: list[dict[str, Any]]
    tag_ids: list[int]
    scenes: list[Scene]
    scene_count: int
    image: str | None
    image_path: str | None
    custom_fields: dict[str, Any] | None


class Studio(TypedDict, total=False):
    """Studio data structure."""
    id: int
    name: str
    stash_ids: list[StashId]
    parent_id: int | None
    image: str | None


class Tag(TypedDict):
    """Tag data structure."""
    id: int
    name: str


class ServerConnection(TypedDict, total=False):
    """Server connection configuration."""
    scheme: str
    host: str
    port: int
    apikey: str
    SessionCookie: dict[str, Any]
