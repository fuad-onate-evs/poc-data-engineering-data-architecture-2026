"""Unit tests for write.integrations.trello.client.

We mock the HTTP layer with `responses` so these tests run hermetically
in CI without burning Trello rate limits.
"""

from __future__ import annotations

import pytest
import responses

from write.config.settings import TrelloConfig
from write.integrations.trello import (
    Board,
    Card,
    TrelloClient,
    TrelloError,
    TrelloList,
    TrelloNotConfiguredError,
)

BASE = "https://api.trello.com/1"


@pytest.fixture
def configured() -> TrelloConfig:
    """A TrelloConfig with fake but non-empty creds."""
    return TrelloConfig(api_key="fake-key", token="fake-token", base_url=BASE)


@pytest.fixture
def client(configured: TrelloConfig) -> TrelloClient:
    return TrelloClient(configured)


# ─── Construction / config ──────────────────────────────────────────


def test_client_raises_when_not_configured() -> None:
    config = TrelloConfig(api_key="", token="")
    with pytest.raises(TrelloNotConfiguredError):
        TrelloClient(config)


def test_config_is_configured_predicate() -> None:
    assert TrelloConfig(api_key="k", token="t").is_configured is True
    assert TrelloConfig(api_key="k", token="").is_configured is False
    assert TrelloConfig(api_key="", token="t").is_configured is False


def test_config_auth_params() -> None:
    config = TrelloConfig(api_key="K", token="T")
    assert config.auth_params == {"key": "K", "token": "T"}


# ─── Read endpoints ─────────────────────────────────────────────────


@responses.activate
def test_get_board(client: TrelloClient) -> None:
    responses.get(
        f"{BASE}/boards/abc",
        json={"id": "abc", "name": "Sprint", "url": "u", "closed": False, "desc": "d"},
        status=200,
    )
    board = client.get_board("abc")
    assert isinstance(board, Board)
    assert board.id == "abc"
    assert board.name == "Sprint"


@responses.activate
def test_list_boards_for_member(client: TrelloClient) -> None:
    responses.get(
        f"{BASE}/members/me/boards",
        json=[
            {"id": "1", "name": "A", "url": "u1"},
            {"id": "2", "name": "B", "url": "u2"},
        ],
        status=200,
    )
    boards = client.list_boards_for_member()
    assert [b.id for b in boards] == ["1", "2"]
    assert all(isinstance(b, Board) for b in boards)


@responses.activate
def test_list_lists_in_board(client: TrelloClient) -> None:
    responses.get(
        f"{BASE}/boards/B1/lists",
        json=[{"id": "L1", "name": "Backlog", "idBoard": "B1", "pos": 1.0}],
        status=200,
    )
    lists = client.list_lists_in_board("B1")
    assert len(lists) == 1
    assert isinstance(lists[0], TrelloList)
    assert lists[0].name == "Backlog"


@responses.activate
def test_list_cards_in_list(client: TrelloClient) -> None:
    responses.get(
        f"{BASE}/lists/L1/cards",
        json=[
            {
                "id": "C1",
                "name": "Card one",
                "idList": "L1",
                "idBoard": "B1",
                "url": "https://trello.com/c/sl1",
                "shortLink": "sl1",
                "labels": [{"name": "high"}],
            },
        ],
        status=200,
    )
    cards = client.list_cards_in_list("L1")
    assert len(cards) == 1
    assert isinstance(cards[0], Card)
    assert cards[0].name == "Card one"
    assert cards[0].labels == ["high"]


@responses.activate
def test_get_card_parses_due_date(client: TrelloClient) -> None:
    responses.get(
        f"{BASE}/cards/C1",
        json={
            "id": "C1",
            "name": "x",
            "idList": "L1",
            "idBoard": "B1",
            "due": "2026-04-15T12:00:00.000Z",
        },
        status=200,
    )
    card = client.get_card("C1")
    assert card.due is not None
    assert card.due.year == 2026
    assert card.due.month == 4


# ─── Write endpoints ────────────────────────────────────────────────


@responses.activate
def test_create_card(client: TrelloClient) -> None:
    responses.post(
        f"{BASE}/cards",
        json={"id": "Cnew", "name": "x", "idList": "L1", "idBoard": "B1"},
        status=200,
    )
    card = client.create_card(list_id="L1", name="x", description="d")
    assert card.id == "Cnew"
    # The request body should have made it through with the right keys
    sent = responses.calls[0].request.body
    assert sent is not None
    # Body is JSON-encoded; we just check the key is in there
    assert b'"idList"' in sent
    assert b'"name"' in sent


@responses.activate
def test_move_card(client: TrelloClient) -> None:
    responses.put(
        f"{BASE}/cards/C1",
        json={"id": "C1", "name": "x", "idList": "L2", "idBoard": "B1"},
        status=200,
    )
    moved = client.move_card("C1", "L2")
    assert moved.list_id == "L2"


@responses.activate
def test_add_comment(client: TrelloClient) -> None:
    responses.post(
        f"{BASE}/cards/C1/actions/comments",
        json={"id": "actionX", "data": {"text": "hi"}},
        status=200,
    )
    result = client.add_comment("C1", "hi")
    assert result["id"] == "actionX"


# ─── Error handling ─────────────────────────────────────────────────


@responses.activate
def test_4xx_raises_trello_error_no_retry(client: TrelloClient) -> None:
    """4xx is a contract bug — should raise immediately, not retry."""
    responses.get(f"{BASE}/cards/bad", json={"error": "not found"}, status=404)
    with pytest.raises(TrelloError):
        client.get_card("bad")
    assert len(responses.calls) == 1  # no retries


@responses.activate
def test_5xx_retries_then_succeeds(client: TrelloClient) -> None:
    """5xx is transient — should retry and eventually succeed."""
    responses.get(f"{BASE}/boards/B1", status=503)
    responses.get(f"{BASE}/boards/B1", status=503)
    responses.get(
        f"{BASE}/boards/B1",
        json={"id": "B1", "name": "ok", "url": "u"},
        status=200,
    )
    board = client.get_board("B1")
    assert board.id == "B1"
    assert len(responses.calls) == 3
