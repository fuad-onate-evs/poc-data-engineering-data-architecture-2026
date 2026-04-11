"""Thin Trello REST client.

Wraps `requests` with auth, retry, timeout, and JSON unwrapping. Returns
plain dicts (or our domain dataclasses, via `models.py`) — never the raw
`requests.Response` — so callers don't depend on the HTTP layer.

Auth is keyed off `TrelloConfig` (see `write.config.settings`); the client
raises `TrelloNotConfiguredError` early if api_key/token are missing rather than
making a useless network call.
"""

from __future__ import annotations

import logging
from typing import Any

import requests
from tenacity import (
    retry,
    retry_if_exception,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from write.config.settings import TrelloConfig

from .models import Board, Card, TrelloList

log = logging.getLogger(__name__)


class TrelloError(RuntimeError):
    """Raised on any non-2xx Trello response that survives retries."""


class TrelloNotConfiguredError(RuntimeError):
    """Raised when api_key or token is missing — fail fast, don't burn the network."""


def _is_retryable_http_error(exc: BaseException) -> bool:
    """5xx HTTP responses are retryable; 4xx is a contract bug and is not."""
    return (
        isinstance(exc, requests.HTTPError)
        and exc.response is not None
        and 500 <= exc.response.status_code < 600
    )


# Connection-level errors and 5xx responses are both transient.
_RETRY_DECORATOR = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
    retry=(
        retry_if_exception_type((requests.ConnectionError, requests.Timeout))
        | retry_if_exception(_is_retryable_http_error)
    ),
    reraise=True,
)


class TrelloClient:
    """Trello REST API client.

    Usage:
        client = TrelloClient(config.trello)
        board = client.get_board("abc123")
        cards = client.list_cards_in_list("def456")
    """

    def __init__(self, config: TrelloConfig | None = None) -> None:
        self.config = config or TrelloConfig()
        if not self.config.is_configured:
            raise TrelloNotConfiguredError(
                "TRELLO_API_KEY and TRELLO_TOKEN must be set "
                "(see envs/.env.example or docs/integrations/trello.md)"
            )
        self._session = requests.Session()
        self._session.headers.update({"Accept": "application/json"})

    # ─── HTTP plumbing ──────────────────────────────────────────────

    def _url(self, path: str) -> str:
        return f"{self.config.base_url.rstrip('/')}/{path.lstrip('/')}"

    @_RETRY_DECORATOR
    def _request_raw(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> requests.Response:
        """Issue one HTTP request. Raises raw HTTPError on non-2xx so the
        retry decorator can inspect the status and decide whether to retry.
        """
        merged_params: dict[str, Any] = dict(self.config.auth_params)
        if params:
            merged_params.update(params)
        resp = self._session.request(
            method=method,
            url=self._url(path),
            params=merged_params,
            json=json_body,
            timeout=self.config.timeout_s,
        )
        resp.raise_for_status()
        return resp

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        """Public request entry — runs the retried raw call, converts any
        terminal HTTPError into TrelloError for callers.
        """
        try:
            resp = self._request_raw(method, path, params, json_body)
        except requests.HTTPError as e:
            status = e.response.status_code if e.response is not None else "?"
            body = e.response.text[:200] if e.response is not None else ""
            log.error("Trello %s %s -> %s: %s", method, path, status, body)
            raise TrelloError(f"{method} {path} failed: {e}") from e
        if not resp.content:
            return None
        return resp.json()

    # ─── Read endpoints ─────────────────────────────────────────────

    def get_board(self, board_id: str) -> Board:
        return Board.from_api(self._request("GET", f"boards/{board_id}"))

    def list_boards_for_member(self, member: str = "me") -> list[Board]:
        data = self._request("GET", f"members/{member}/boards", params={"filter": "open"})
        return [Board.from_api(b) for b in data]

    def list_lists_in_board(self, board_id: str) -> list[TrelloList]:
        data = self._request("GET", f"boards/{board_id}/lists", params={"filter": "open"})
        return [TrelloList.from_api(li) for li in data]

    def list_cards_in_list(self, list_id: str) -> list[Card]:
        data = self._request("GET", f"lists/{list_id}/cards")
        return [Card.from_api(c) for c in data]

    def list_cards_in_board(self, board_id: str) -> list[Card]:
        data = self._request("GET", f"boards/{board_id}/cards", params={"filter": "open"})
        return [Card.from_api(c) for c in data]

    def get_card(self, card_id: str) -> Card:
        return Card.from_api(self._request("GET", f"cards/{card_id}"))

    # ─── Write endpoints ────────────────────────────────────────────

    def create_card(
        self,
        list_id: str,
        name: str,
        description: str = "",
        labels: list[str] | None = None,
    ) -> Card:
        body: dict[str, Any] = {
            "idList": list_id,
            "name": name,
            "desc": description,
        }
        if labels:
            body["idLabels"] = labels
        return Card.from_api(self._request("POST", "cards", json_body=body))

    def update_card(self, card_id: str, **fields: Any) -> Card:
        """Update arbitrary card fields. Trello expects camelCase keys.

        Common fields: idList, name, desc, due, closed.
        """
        return Card.from_api(self._request("PUT", f"cards/{card_id}", json_body=fields))

    def move_card(self, card_id: str, target_list_id: str) -> Card:
        return self.update_card(card_id, idList=target_list_id)

    def add_comment(self, card_id: str, text: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"cards/{card_id}/actions/comments",
            json_body={"text": text},
        )

    def archive_card(self, card_id: str) -> Card:
        return self.update_card(card_id, closed=True)
