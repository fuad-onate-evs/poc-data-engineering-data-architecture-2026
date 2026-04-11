"""Sync layer — the four use cases approved for the Trello integration.

1. **Board pull** (sprint board sync): snapshot a Trello board to a local
   JSON file so the team can diff sprint scope across days, or feed it into
   GitHub Issues / a dashboard.

2. **PR card move** (CI/CD): given a card short link from a PR branch name
   like `feat/abc123-foo`, move the card between Backlog → In Progress →
   Review → Done as PR events fire.

3. **Incident** (pipeline alerts): create an Incidents-list card when a DAG
   task or DQ check fails. Idempotent on title-prefix so re-runs don't
   spam the board.

4. **Asset upsert** (data catalog stand-in): one card per Bronze table on
   the Assets list, kept up to date with row count + freshness on each run.

These functions take an injected `TrelloClient` so tests can mock it cleanly
and so callers can decide where the client comes from (CLI, DAG callback,
GitHub Action runner).
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .client import TrelloClient
from .models import Board, Card, TrelloList

log = logging.getLogger(__name__)


# ─── 1. Board pull ──────────────────────────────────────────────────


def pull_board_snapshot(
    client: TrelloClient,
    board_id: str,
    out_path: Path | None = None,
) -> dict[str, Any]:
    """Fetch a board's lists + cards, return a JSON-serializable snapshot.

    If `out_path` is given, also write it to disk. The snapshot is the
    primitive data we use for board → GitHub Issues mirroring or for
    sprint velocity analytics.
    """
    board = client.get_board(board_id)
    lists = client.list_lists_in_board(board_id)
    cards_by_list: dict[str, list[Card]] = {li.id: [] for li in lists}
    for card in client.list_cards_in_board(board_id):
        cards_by_list.setdefault(card.list_id, []).append(card)

    snapshot: dict[str, Any] = {
        "snapshot_at": datetime.now(UTC).isoformat(),
        "board": _board_to_dict(board),
        "lists": [
            {
                **_list_to_dict(li),
                "cards": [_card_to_dict(c) for c in cards_by_list.get(li.id, [])],
            }
            for li in lists
        ],
    }

    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(snapshot, indent=2, sort_keys=True))
        log.info("Wrote board snapshot to %s", out_path)

    return snapshot


# ─── 2. PR ↔ card sync ──────────────────────────────────────────────


def move_card_for_pr_event(
    client: TrelloClient,
    card_short_link: str,
    target_list_id: str,
    pr_url: str | None = None,
) -> Card:
    """Move a card to the list that matches the new PR state.

    Resolves the card by short link (the 8-char id Trello shows in URLs),
    moves it, and posts a comment with the PR URL for traceability.
    """
    card = client.get_card(card_short_link)
    moved = client.move_card(card.id, target_list_id)
    if pr_url:
        client.add_comment(card.id, f"PR: {pr_url}")
    log.info("Moved card %s (%s) to list %s", card.id, card.name, target_list_id)
    return moved


# ─── 3. Pipeline alerts → Trello ────────────────────────────────────


_INCIDENT_TITLE_PREFIX = "[INCIDENT]"


def upsert_incident_card(
    client: TrelloClient,
    incidents_list_id: str,
    title: str,
    body: str,
    severity: str = "P2",
) -> Card:
    """Create or comment on an incident card.

    Idempotent on the exact title — if a card with the same title already
    exists on the Incidents list (and is open), append the new body as a
    comment instead of creating a duplicate. This keeps the board readable
    when a DAG fails repeatedly.
    """
    full_title = f"{_INCIDENT_TITLE_PREFIX} [{severity}] {title}"
    existing = [
        c
        for c in client.list_cards_in_list(incidents_list_id)
        if c.name == full_title and not c.closed
    ]
    if existing:
        card = existing[0]
        client.add_comment(card.id, body)
        log.info("Appended to existing incident card %s", card.id)
        return card
    card = client.create_card(
        list_id=incidents_list_id,
        name=full_title,
        description=body,
    )
    log.info("Created incident card %s for %s", card.id, full_title)
    return card


# ─── 4. Asset / Bronze-table tracking ───────────────────────────────


_ASSET_TITLE_PREFIX = "[ASSET]"


def upsert_asset_card(
    client: TrelloClient,
    assets_list_id: str,
    table_name: str,
    row_count: int,
    freshness_iso: str,
    extra_lines: list[str] | None = None,
) -> Card:
    """Create or update the asset card for a Bronze/Silver/Gold table.

    Each table gets exactly one open card on the Assets list. The
    description is rewritten on every call to reflect the latest snapshot
    (row count + freshness + any extra lines passed by the caller).
    """
    full_title = f"{_ASSET_TITLE_PREFIX} {table_name}"
    body_lines = [
        f"**Table**: `{table_name}`",
        f"**Row count**: {row_count:,}",
        f"**Freshness**: {freshness_iso}",
        f"**Updated**: {datetime.now(UTC).isoformat()}",
    ]
    if extra_lines:
        body_lines.extend(extra_lines)
    body = "\n\n".join(body_lines)

    existing = [
        c
        for c in client.list_cards_in_list(assets_list_id)
        if c.name == full_title and not c.closed
    ]
    if existing:
        card = client.update_card(existing[0].id, desc=body)
        log.info("Refreshed asset card %s for %s", card.id, table_name)
        return card
    card = client.create_card(
        list_id=assets_list_id,
        name=full_title,
        description=body,
    )
    log.info("Created asset card %s for %s", card.id, table_name)
    return card


# ─── helpers ────────────────────────────────────────────────────────


def _board_to_dict(b: Board) -> dict[str, Any]:
    return {
        "id": b.id,
        "name": b.name,
        "url": b.url,
        "closed": b.closed,
        "description": b.description,
    }


def _list_to_dict(li: TrelloList) -> dict[str, Any]:
    return {
        "id": li.id,
        "name": li.name,
        "board_id": li.board_id,
        "closed": li.closed,
        "pos": li.pos,
    }


def _card_to_dict(c: Card) -> dict[str, Any]:
    return {
        "id": c.id,
        "short_link": c.short_link,
        "name": c.name,
        "list_id": c.list_id,
        "url": c.url,
        "description": c.description,
        "closed": c.closed,
        "due": c.due.isoformat() if c.due else None,
        "labels": c.labels,
    }
