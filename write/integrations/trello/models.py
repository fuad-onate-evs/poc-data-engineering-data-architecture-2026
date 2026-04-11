"""Trello domain dataclasses — typed slices of the REST API responses.

We deliberately keep these as plain dataclasses (not pydantic) to stay
dependency-light and match the rest of `write.config.settings`. Only the
fields we actually use are mapped; unknown fields from the API are dropped.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Board:
    """A Trello board (the top-level container for lists and cards)."""

    id: str
    name: str
    url: str
    closed: bool = False
    description: str = ""

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Board:
        return cls(
            id=data["id"],
            name=data["name"],
            url=data.get("url", ""),
            closed=data.get("closed", False),
            description=data.get("desc", ""),
        )


@dataclass
class TrelloList:
    """A Trello list (column on a board — Backlog / TODO / In Progress / etc.)."""

    id: str
    name: str
    board_id: str
    closed: bool = False
    pos: float = 0.0

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> TrelloList:
        return cls(
            id=data["id"],
            name=data["name"],
            board_id=data.get("idBoard", ""),
            closed=data.get("closed", False),
            pos=float(data.get("pos", 0)),
        )


@dataclass
class Card:
    """A Trello card (one task / story / issue)."""

    id: str
    name: str
    list_id: str
    board_id: str
    url: str = ""
    description: str = ""
    closed: bool = False
    due: datetime | None = None
    labels: list[str] = field(default_factory=list)
    short_link: str = ""

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Card:
        due_raw = data.get("due")
        due_parsed: datetime | None = None
        if due_raw:
            # Trello returns ISO 8601 with Z suffix; replace for fromisoformat compatibility
            due_parsed = datetime.fromisoformat(due_raw.replace("Z", "+00:00"))
        return cls(
            id=data["id"],
            name=data["name"],
            list_id=data.get("idList", ""),
            board_id=data.get("idBoard", ""),
            url=data.get("url", ""),
            description=data.get("desc", ""),
            closed=data.get("closed", False),
            due=due_parsed,
            labels=[lbl.get("name", "") for lbl in data.get("labels", [])],
            short_link=data.get("shortLink", ""),
        )
