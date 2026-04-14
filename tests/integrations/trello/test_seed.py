"""Unit tests for seed_board_from_plan.

Mirrors the FakeTrelloClient pattern from test_sync.py, extended with label
and list-rename support. Exercises: create, idempotent re-run (no duplicates),
update-on-diff, label reuse, missing-list error reporting, dry-run safety.
"""

from __future__ import annotations

from typing import Any

import pytest

from write.integrations.trello import (
    Board,
    Card,
    Label,
    SeedReport,
    TrelloList,
    seed_board_from_plan,
)


class FakeTrelloClient:
    """In-memory TrelloClient stand-in with labels + list rename support."""

    def __init__(self) -> None:
        self.boards: dict[str, Board] = {}
        self.lists_by_board: dict[str, list[TrelloList]] = {}
        self.cards_by_id: dict[str, Card] = {}
        self.cards_by_list: dict[str, list[Card]] = {}
        self.cards_by_board: dict[str, list[Card]] = {}
        self.labels_by_board: dict[str, list[Label]] = {}
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._next_id = 1

    def _new_id(self, prefix: str) -> str:
        cid = f"{prefix}{self._next_id}"
        self._next_id += 1
        return cid

    def _record(self, method: str, **kwargs: Any) -> None:
        self.calls.append((method, kwargs))

    # Read
    def list_lists_in_board(self, board_id: str) -> list[TrelloList]:
        self._record("list_lists_in_board", board_id=board_id)
        return list(self.lists_by_board.get(board_id, []))

    def list_cards_in_board(self, board_id: str) -> list[Card]:
        self._record("list_cards_in_board", board_id=board_id)
        return list(self.cards_by_board.get(board_id, []))

    def list_labels_in_board(self, board_id: str) -> list[Label]:
        self._record("list_labels_in_board", board_id=board_id)
        return list(self.labels_by_board.get(board_id, []))

    # Write
    def create_label(self, board_id: str, name: str, color: str | None = None) -> Label:
        lid = self._new_id("L")
        lbl = Label(id=lid, name=name, color=color, board_id=board_id)
        self.labels_by_board.setdefault(board_id, []).append(lbl)
        self._record("create_label", board_id=board_id, name=name, color=color)
        return lbl

    def create_card(
        self,
        list_id: str,
        name: str,
        description: str = "",
        labels: list[str] | None = None,
    ) -> Card:
        cid = self._new_id("C")
        card = Card(
            id=cid,
            name=name,
            list_id=list_id,
            board_id="B1",
            description=description,
            labels=[],
            label_ids=list(labels or []),
            url=f"https://trello.com/c/{cid}",
        )
        self.cards_by_id[cid] = card
        self.cards_by_list.setdefault(list_id, []).append(card)
        self.cards_by_board.setdefault("B1", []).append(card)
        self._record("create_card", list_id=list_id, name=name, labels=labels or [])
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
        if "idLabels" in fields:
            existing.label_ids = list(fields["idLabels"])
        self._record("update_card", card_id=card_id, fields=fields)
        return existing


SPRINT_1_PLAN: dict[str, Any] = {
    "board_id": "B1",
    "lists": {
        "backlog": "Backlog",
        "todo": "TODO",
        "in_progress": "In Progress",
        "done": "Done",
    },
    "labels": [
        {"name": "Sprint 1", "color": "blue"},
        {"name": "Epic 1 — Discovery", "color": "sky"},
        {"name": "DE1", "color": None},
    ],
    "stories": [
        {
            "key": "US-1.1",
            "title": "Source inventory & env setup",
            "sprint": "Sprint 1",
            "epic": "Epic 1 — Discovery",
            "tasks": [
                {
                    "title": "Map SCADA sources",
                    "owner": "DE1",
                    "sp": 3,
                    "state": "todo",
                    "acceptance": "Source catalog",
                },
                {
                    "title": "Setup GitHub repos",
                    "owner": "DE1",
                    "sp": 2,
                    "state": "done",
                },
            ],
        },
    ],
}


@pytest.fixture
def fake_board() -> FakeTrelloClient:
    f = FakeTrelloClient()
    f.boards["B1"] = Board(id="B1", name="POC", url="https://trello.com/b/B1")
    f.lists_by_board["B1"] = [
        TrelloList(id="L_BACK", name="Backlog", board_id="B1", pos=1),
        TrelloList(id="L_TODO", name="TODO", board_id="B1", pos=2),
        TrelloList(id="L_PROG", name="In Progress", board_id="B1", pos=3),
        TrelloList(id="L_DONE", name="Done", board_id="B1", pos=4),
    ]
    return f


def test_seed_creates_labels_and_cards_on_empty_board(fake_board: FakeTrelloClient) -> None:
    report = seed_board_from_plan(fake_board, SPRINT_1_PLAN)  # type: ignore[arg-type]
    assert report.labels_created == ["Sprint 1", "Epic 1 — Discovery", "DE1"]
    assert not report.labels_existing
    assert len(report.cards_created) == 2
    assert not report.errors
    assert len(fake_board.cards_by_id) == 2


def test_seed_places_cards_in_correct_list_by_state(fake_board: FakeTrelloClient) -> None:
    seed_board_from_plan(fake_board, SPRINT_1_PLAN)  # type: ignore[arg-type]
    todo_cards = fake_board.cards_by_list["L_TODO"]
    done_cards = fake_board.cards_by_list["L_DONE"]
    assert len(todo_cards) == 1
    assert "Map SCADA sources" in todo_cards[0].name
    assert len(done_cards) == 1
    assert "Setup GitHub repos" in done_cards[0].name


def test_seed_applies_story_and_owner_labels(fake_board: FakeTrelloClient) -> None:
    seed_board_from_plan(fake_board, SPRINT_1_PLAN)  # type: ignore[arg-type]
    labels = {lbl.name: lbl.id for lbl in fake_board.labels_by_board["B1"]}
    scada_card = next(c for c in fake_board.cards_by_id.values() if "SCADA" in c.name)
    # Each task should carry sprint + epic + owner labels.
    assert labels["Sprint 1"] in scada_card.label_ids
    assert labels["Epic 1 — Discovery"] in scada_card.label_ids
    assert labels["DE1"] in scada_card.label_ids


def test_seed_is_idempotent_on_rerun(fake_board: FakeTrelloClient) -> None:
    seed_board_from_plan(fake_board, SPRINT_1_PLAN)  # type: ignore[arg-type]
    second = seed_board_from_plan(fake_board, SPRINT_1_PLAN)  # type: ignore[arg-type]
    assert not second.cards_created
    assert not second.cards_updated
    assert len(second.cards_unchanged) == 2
    assert second.labels_existing == ["Sprint 1", "Epic 1 — Discovery", "DE1"]
    assert not second.errors
    # Still only 2 cards on the board — no duplicates.
    assert len(fake_board.cards_by_id) == 2


def test_seed_updates_existing_card_when_plan_changes(fake_board: FakeTrelloClient) -> None:
    seed_board_from_plan(fake_board, SPRINT_1_PLAN)  # type: ignore[arg-type]
    # Mutate plan: move the SCADA task from todo → in_progress and change desc.
    modified: dict[str, Any] = {
        **SPRINT_1_PLAN,
        "stories": [
            {
                **SPRINT_1_PLAN["stories"][0],
                "tasks": [
                    {
                        **SPRINT_1_PLAN["stories"][0]["tasks"][0],
                        "state": "in_progress",
                        "acceptance": "Updated criteria",
                    },
                    SPRINT_1_PLAN["stories"][0]["tasks"][1],
                ],
            }
        ],
    }
    second: SeedReport = seed_board_from_plan(fake_board, modified)  # type: ignore[arg-type]
    assert len(second.cards_updated) == 1
    scada = next(c for c in fake_board.cards_by_id.values() if "SCADA" in c.name)
    assert scada.list_id == "L_PROG"
    assert "Updated criteria" in scada.description


def test_seed_reuses_existing_labels(fake_board: FakeTrelloClient) -> None:
    # Pre-populate one label so the run has to dedup.
    pre = Label(id="L_PRE", name="Sprint 1", color="blue", board_id="B1")
    fake_board.labels_by_board["B1"] = [pre]
    report = seed_board_from_plan(fake_board, SPRINT_1_PLAN)  # type: ignore[arg-type]
    assert "Sprint 1" in report.labels_existing
    assert "Sprint 1" not in report.labels_created
    # The label id reused on cards must be the pre-existing one.
    scada_card = next(c for c in fake_board.cards_by_id.values() if "SCADA" in c.name)
    assert "L_PRE" in scada_card.label_ids


def test_seed_dry_run_issues_no_writes(fake_board: FakeTrelloClient) -> None:
    report = seed_board_from_plan(fake_board, SPRINT_1_PLAN, dry_run=True)  # type: ignore[arg-type]
    assert len(report.cards_created) == 2
    assert len(report.labels_created) == 3
    # Nothing actually persisted.
    assert not fake_board.cards_by_id
    assert not fake_board.labels_by_board
    # No write calls recorded.
    write_calls = [c for c, _ in fake_board.calls if c in ("create_card", "create_label")]
    assert not write_calls


def test_seed_reports_error_when_state_has_no_list(fake_board: FakeTrelloClient) -> None:
    bad_plan: dict[str, Any] = {
        **SPRINT_1_PLAN,
        "lists": {"backlog": "NonExistentList"},
        "stories": [
            {
                "key": "US-X",
                "title": "broken",
                "sprint": "Sprint 1",
                "tasks": [{"title": "bad task", "owner": "DE1", "sp": 1, "state": "backlog"}],
            }
        ],
    }
    report = seed_board_from_plan(fake_board, bad_plan)  # type: ignore[arg-type]
    assert report.errors
    assert any("NonExistentList" in e or "backlog" in e for e in report.errors)


def test_seed_tolerates_typo_in_list_name(fake_board: FakeTrelloClient) -> None:
    # Simulate the real board's "In Pogress" typo: prefix-match fallback
    # should still resolve it to the declared `in_progress` state.
    fake_board.lists_by_board["B1"] = [
        TrelloList(id="L_BACK", name="Backlog", board_id="B1", pos=1),
        TrelloList(id="L_TODO", name="TODO", board_id="B1", pos=2),
        TrelloList(id="L_PROG", name="In Pogress", board_id="B1", pos=3),  # typo
        TrelloList(id="L_DONE", name="Done", board_id="B1", pos=4),
    ]
    plan_with_progress: dict[str, Any] = {
        **SPRINT_1_PLAN,
        "stories": [
            {
                "key": "US-1.1",
                "title": "x",
                "sprint": "Sprint 1",
                "tasks": [
                    {"title": "mid", "owner": "DE1", "sp": 1, "state": "in_progress"},
                ],
            }
        ],
    }
    report = seed_board_from_plan(fake_board, plan_with_progress)  # type: ignore[arg-type]
    assert not report.errors
    assert len(fake_board.cards_by_list.get("L_PROG", [])) == 1
