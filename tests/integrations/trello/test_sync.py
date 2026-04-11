"""Unit tests for write.integrations.trello.sync.

These exercise the four sync use cases against a hand-rolled fake
TrelloClient (no HTTP). Keeps the assertions about *behavior* (idempotency,
correct list-id targeting, comment posting) decoupled from the wire format.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from write.integrations.trello import (
    Board,
    Card,
    TrelloList,
    move_card_for_pr_event,
    pull_board_snapshot,
    upsert_asset_card,
    upsert_incident_card,
)


class FakeTrelloClient:
    """In-memory stand-in for TrelloClient. Records every call."""

    def __init__(self) -> None:
        self.boards: dict[str, Board] = {}
        self.lists_by_board: dict[str, list[TrelloList]] = {}
        self.cards_by_id: dict[str, Card] = {}
        self.cards_by_list: dict[str, list[Card]] = {}
        self.cards_by_board: dict[str, list[Card]] = {}
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._next_id = 1

    def _record(self, method: str, **kwargs: Any) -> None:
        self.calls.append((method, kwargs))

    def _new_id(self, prefix: str = "C") -> str:
        cid = f"{prefix}{self._next_id}"
        self._next_id += 1
        return cid

    # Read API
    def get_board(self, board_id: str) -> Board:
        self._record("get_board", board_id=board_id)
        return self.boards[board_id]

    def list_lists_in_board(self, board_id: str) -> list[TrelloList]:
        self._record("list_lists_in_board", board_id=board_id)
        return list(self.lists_by_board.get(board_id, []))

    def list_cards_in_board(self, board_id: str) -> list[Card]:
        self._record("list_cards_in_board", board_id=board_id)
        return list(self.cards_by_board.get(board_id, []))

    def list_cards_in_list(self, list_id: str) -> list[Card]:
        self._record("list_cards_in_list", list_id=list_id)
        return list(self.cards_by_list.get(list_id, []))

    def get_card(self, card_id: str) -> Card:
        self._record("get_card", card_id=card_id)
        return self.cards_by_id[card_id]

    # Write API
    def create_card(
        self,
        list_id: str,
        name: str,
        description: str = "",
        labels: list[str] | None = None,
    ) -> Card:
        cid = self._new_id()
        card = Card(
            id=cid,
            name=name,
            list_id=list_id,
            board_id="board-fake",
            description=description,
            labels=labels or [],
            url=f"https://trello.com/c/{cid}",
        )
        self.cards_by_id[cid] = card
        self.cards_by_list.setdefault(list_id, []).append(card)
        self._record("create_card", list_id=list_id, name=name, description=description)
        return card

    def update_card(self, card_id: str, **fields: Any) -> Card:
        existing = self.cards_by_id[card_id]
        if "idList" in fields:
            new_list = fields["idList"]
            self.cards_by_list.get(existing.list_id, []).remove(existing)
            self.cards_by_list.setdefault(new_list, []).append(existing)
            existing.list_id = new_list
        if "desc" in fields:
            existing.description = fields["desc"]
        if "closed" in fields:
            existing.closed = fields["closed"]
        self._record("update_card", card_id=card_id, fields=fields)
        return existing

    def move_card(self, card_id: str, target_list_id: str) -> Card:
        return self.update_card(card_id, idList=target_list_id)

    def add_comment(self, card_id: str, text: str) -> dict[str, Any]:
        self._record("add_comment", card_id=card_id, text=text)
        return {"id": "comment-fake", "data": {"text": text}}


@pytest.fixture
def fake() -> FakeTrelloClient:
    f = FakeTrelloClient()
    f.boards["B1"] = Board(id="B1", name="POC Sprint", url="u")
    f.lists_by_board["B1"] = [
        TrelloList(id="L_BACK", name="Backlog", board_id="B1", pos=1),
        TrelloList(id="L_PROG", name="In Progress", board_id="B1", pos=2),
        TrelloList(id="L_DONE", name="Done", board_id="B1", pos=3),
        TrelloList(id="L_INC", name="Incidents", board_id="B1", pos=4),
        TrelloList(id="L_ASSET", name="Assets", board_id="B1", pos=5),
    ]
    f.cards_by_board["B1"] = []
    return f


# ─── 1. Board pull ──────────────────────────────────────────────────


def test_pull_board_snapshot_returns_lists_and_cards(fake: FakeTrelloClient) -> None:
    fake.cards_by_board["B1"] = [
        Card(id="C1", name="t1", list_id="L_BACK", board_id="B1"),
        Card(id="C2", name="t2", list_id="L_PROG", board_id="B1"),
    ]
    snap = pull_board_snapshot(fake, "B1")  # type: ignore[arg-type]
    assert snap["board"]["id"] == "B1"
    assert len(snap["lists"]) == 5
    backlog = next(li for li in snap["lists"] if li["id"] == "L_BACK")
    assert len(backlog["cards"]) == 1
    assert backlog["cards"][0]["name"] == "t1"


def test_pull_board_snapshot_writes_to_disk(
    fake: FakeTrelloClient,
    tmp_path: Path,
) -> None:
    out = tmp_path / "snap.json"
    pull_board_snapshot(fake, "B1", out_path=out)  # type: ignore[arg-type]
    assert out.exists()
    loaded = json.loads(out.read_text())
    assert loaded["board"]["id"] == "B1"


# ─── 2. PR card move ────────────────────────────────────────────────


def test_move_card_for_pr_event_moves_and_comments(fake: FakeTrelloClient) -> None:
    card = fake.create_card("L_BACK", "story")
    move_card_for_pr_event(fake, card.id, "L_PROG", pr_url="https://github.com/x/y/pull/1")  # type: ignore[arg-type]
    assert fake.cards_by_id[card.id].list_id == "L_PROG"
    methods = [c[0] for c in fake.calls]
    assert "add_comment" in methods


def test_move_card_no_pr_url_skips_comment(fake: FakeTrelloClient) -> None:
    card = fake.create_card("L_BACK", "story")
    fake.calls.clear()
    move_card_for_pr_event(fake, card.id, "L_PROG", pr_url=None)  # type: ignore[arg-type]
    assert not any(c[0] == "add_comment" for c in fake.calls)


# ─── 3. Incident upsert ─────────────────────────────────────────────


def test_upsert_incident_creates_when_no_match(fake: FakeTrelloClient) -> None:
    card = upsert_incident_card(
        fake,  # type: ignore[arg-type]
        incidents_list_id="L_INC",
        title="DAG energy_ingestion failed",
        body="task=consume_to_bronze; error=...",
        severity="P1",
    )
    assert "[INCIDENT]" in card.name
    assert "[P1]" in card.name
    assert card.list_id == "L_INC"


def test_upsert_incident_appends_comment_on_duplicate(fake: FakeTrelloClient) -> None:
    upsert_incident_card(fake, "L_INC", "DAG failed", "first", "P2")  # type: ignore[arg-type]
    upsert_incident_card(fake, "L_INC", "DAG failed", "second", "P2")  # type: ignore[arg-type]
    # Only ONE incident card should exist
    assert len(fake.cards_by_list["L_INC"]) == 1
    # And there should be a comment from the second call
    comment_calls = [c for c in fake.calls if c[0] == "add_comment"]
    assert any(c[1].get("text") == "second" for c in comment_calls)


def test_upsert_incident_treats_closed_card_as_absent(fake: FakeTrelloClient) -> None:
    first = upsert_incident_card(fake, "L_INC", "DAG failed", "first", "P2")  # type: ignore[arg-type]
    fake.cards_by_id[first.id].closed = True  # archive
    second = upsert_incident_card(fake, "L_INC", "DAG failed", "second", "P2")  # type: ignore[arg-type]
    assert second.id != first.id


# ─── 4. Asset upsert ────────────────────────────────────────────────


def test_upsert_asset_creates_card_when_absent(fake: FakeTrelloClient) -> None:
    card = upsert_asset_card(
        fake,  # type: ignore[arg-type]
        assets_list_id="L_ASSET",
        table_name="bronze.scada_telemetry",
        row_count=1234,
        freshness_iso="2026-04-11T10:00:00Z",
    )
    assert "[ASSET]" in card.name
    assert "bronze.scada_telemetry" in card.name
    assert "1,234" in card.description


def test_upsert_asset_refreshes_existing_card(fake: FakeTrelloClient) -> None:
    first = upsert_asset_card(
        fake,  # type: ignore[arg-type]
        assets_list_id="L_ASSET",
        table_name="bronze.weather",
        row_count=100,
        freshness_iso="2026-04-11T10:00:00Z",
    )
    second = upsert_asset_card(
        fake,  # type: ignore[arg-type]
        assets_list_id="L_ASSET",
        table_name="bronze.weather",
        row_count=999,
        freshness_iso="2026-04-11T11:00:00Z",
    )
    assert first.id == second.id  # same card refreshed
    assert "999" in second.description
    assert len(fake.cards_by_list["L_ASSET"]) == 1
