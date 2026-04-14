"""Sync layer — the sync use cases approved for the Trello integration.

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

5. **Seed board from plan.yaml** (sprint scaffolding): populate the board
   with stories/tasks declared in `docs/sprints/plan.yaml`. Idempotent by
   card title; re-runs update labels + description + list placement instead
   of duplicating.

These functions take an injected `TrelloClient` so tests can mock it cleanly
and so callers can decide where the client comes from (CLI, DAG callback,
GitHub Action runner).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .client import TrelloClient
from .models import Board, Card, Label, TrelloList

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


# ─── 5. Seed board from plan.yaml ───────────────────────────────────


@dataclass
class SeedReport:
    """Summary of a `seed_board_from_plan` run."""

    labels_created: list[str] = field(default_factory=list)
    labels_existing: list[str] = field(default_factory=list)
    cards_created: list[str] = field(default_factory=list)
    cards_updated: list[str] = field(default_factory=list)
    cards_unchanged: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"labels: {len(self.labels_created)} created / {len(self.labels_existing)} existing · "
            f"cards: {len(self.cards_created)} created / {len(self.cards_updated)} updated / "
            f"{len(self.cards_unchanged)} unchanged · errors: {len(self.errors)}"
        )


def _task_title(story_key: str, task_title: str) -> str:
    """Stable title used as the idempotency key for a plan-seeded card."""
    return f"{story_key} · {task_title}"


def _task_description(story_key: str, story_title: str, task: dict[str, Any]) -> str:
    lines = [
        f"**Story**: {story_key} — {story_title}",
        f"**Owner**: {task.get('owner', '?')}",
        f"**Story points**: {task.get('sp', '?')}",
    ]
    if task.get("acceptance"):
        lines.append(f"**Acceptance**: {task['acceptance']}")
    if task.get("notes"):
        lines.append(f"**Notes**: {task['notes']}")
    return "\n\n".join(lines)


def _resolve_label_ids(
    labels_by_name: dict[str, Label],
    wanted_names: list[str],
) -> list[str]:
    """Map plan-declared label names to Trello label ids. Skips silently on unknowns."""
    return [labels_by_name[n].id for n in wanted_names if n in labels_by_name]


def seed_board_from_plan(
    client: TrelloClient,
    plan: dict[str, Any],
    *,
    dry_run: bool = False,
) -> SeedReport:
    """Populate a board from a declarative `plan.yaml` payload.

    The `plan` dict is the parsed YAML — this function is schema-agnostic to
    the loader so callers can pass whatever source (file, stdin, test fixture).

    Idempotent contract:
      - Labels are matched by `name`. Missing labels are created with the
        declared color; existing labels are reused unchanged.
      - Cards are matched by title (`{story_key} · {task title}`). Missing
        cards are created in the list corresponding to their `state`.
        Existing cards get desc, labels, and `idList` reconciled against
        the plan — a re-run after editing the YAML is safe.

    Args:
        client: Authenticated TrelloClient.
        plan: Parsed YAML with keys `board_id`, `lists`, `labels`, `stories`.
        dry_run: If True, no Trello write calls are issued — the returned
            SeedReport still reflects what *would* be created/updated.

    Returns:
        SeedReport with per-entity breakdown. Never raises on individual
        task failures; records them under `errors` and keeps going.
    """
    board_id = plan["board_id"]
    state_to_list_name: dict[str, str] = plan.get("lists", {})

    report = SeedReport()

    # ─── Resolve lists ────────────────────────────────────────────
    board_lists = client.list_lists_in_board(board_id)
    list_by_name_lower: dict[str, TrelloList] = {li.name.lower(): li for li in board_lists}
    # Also index by trimmed lowercase to tolerate minor typos (e.g. "In Pogress").
    state_to_list_id: dict[str, str] = {}
    for state, declared_name in state_to_list_name.items():
        li = list_by_name_lower.get(declared_name.lower())
        if li is None:
            # Fall back to first-4-char match so the Sprint 1 seed still works
            # against boards with typos like "In Pogress" — the seed runs
            # before the rename-list subcommand is applied.
            declared_prefix = declared_name.lower().strip()[:4]
            for name_l, trello_list in list_by_name_lower.items():
                if declared_prefix and name_l.strip()[:4] == declared_prefix:
                    li = trello_list
                    break
        if li is None:
            report.errors.append(f"list for state '{state}' ({declared_name!r}) not found on board")
            continue
        state_to_list_id[state] = li.id

    # ─── Reconcile labels ────────────────────────────────────────
    existing_labels = {lbl.name: lbl for lbl in client.list_labels_in_board(board_id) if lbl.name}
    for lbl_spec in plan.get("labels", []):
        name = lbl_spec["name"]
        color = lbl_spec.get("color")  # may be None for colorless labels
        if name in existing_labels:
            report.labels_existing.append(name)
            continue
        if dry_run:
            report.labels_created.append(name)
            continue
        try:
            new_label = client.create_label(board_id, name=name, color=color)
            existing_labels[name] = new_label
            report.labels_created.append(name)
        except Exception as e:
            report.errors.append(f"create_label {name!r}: {e}")

    # ─── Reconcile cards ─────────────────────────────────────────
    existing_cards = {c.name: c for c in client.list_cards_in_board(board_id) if not c.closed}

    for story in plan.get("stories", []):
        story_key = story["key"]
        story_title = story.get("title", "")
        story_labels = [story["sprint"], story.get("epic", "")]
        story_labels = [n for n in story_labels if n]

        for task in story.get("tasks", []):
            title = _task_title(story_key, task["title"])
            desc = _task_description(story_key, story_title, task)
            task_state = task.get("state", "backlog")
            target_list_id = state_to_list_id.get(task_state)
            if target_list_id is None:
                report.errors.append(f"{title}: unknown state {task_state!r}")
                continue

            task_label_names = [*story_labels]
            owner = task.get("owner")
            if owner:
                # Owner may be a comma-separated list — split so each becomes its own label.
                for part in str(owner).split(","):
                    part = part.strip()
                    if part:
                        task_label_names.append(part)

            wanted_label_ids = _resolve_label_ids(existing_labels, task_label_names)

            if title in existing_cards:
                card = existing_cards[title]
                needs_update = (
                    card.description != desc
                    or card.list_id != target_list_id
                    or set(card.label_ids) != set(wanted_label_ids)
                )
                if not needs_update:
                    report.cards_unchanged.append(title)
                    continue
                if dry_run:
                    report.cards_updated.append(title)
                    continue
                try:
                    client.update_card(
                        card.id,
                        desc=desc,
                        idList=target_list_id,
                        idLabels=wanted_label_ids,
                    )
                    report.cards_updated.append(title)
                except Exception as e:
                    report.errors.append(f"update_card {title!r}: {e}")
                continue

            if dry_run:
                report.cards_created.append(title)
                continue
            try:
                client.create_card(
                    list_id=target_list_id,
                    name=title,
                    description=desc,
                    labels=wanted_label_ids,
                )
                report.cards_created.append(title)
            except Exception as e:
                report.errors.append(f"create_card {title!r}: {e}")

    return report


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
