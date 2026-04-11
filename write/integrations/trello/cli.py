"""CLI entry point for the Trello integration.

Usage:
    uv run python -m write.integrations.trello.cli list-boards
    uv run python -m write.integrations.trello.cli list-lists --board <board_id>
    uv run python -m write.integrations.trello.cli pull-board --board <board_id> --out snapshot.json
    uv run python -m write.integrations.trello.cli move-card --card <short_link> --to <list_id> [--pr-url URL]
    uv run python -m write.integrations.trello.cli incident --list <list_id> --title "..." --body "..." --severity P1
    uv run python -m write.integrations.trello.cli upsert-asset --list <list_id> --table bronze.scada --rows 12345 --freshness 2026-04-11T10:00:00Z

Auth comes from the standard env file (`envs/.env.<env>` or `.env`):
    TRELLO_API_KEY, TRELLO_TOKEN, TRELLO_BOARD_ID, etc.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from write.config.settings import TrelloConfig

from .client import TrelloClient, TrelloError, TrelloNotConfiguredError
from .sync import (
    move_card_for_pr_event,
    pull_board_snapshot,
    upsert_asset_card,
    upsert_incident_card,
)

log = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trello",
        description="Trello sync CLI for the POC data platform",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # list-boards
    sub.add_parser("list-boards", help="List boards visible to the auth token")

    # list-lists
    p = sub.add_parser("list-lists", help="List columns on a board")
    p.add_argument("--board", required=True)

    # pull-board
    p = sub.add_parser("pull-board", help="Snapshot a board (lists + cards) to JSON")
    p.add_argument("--board", required=True)
    p.add_argument("--out", type=Path, help="Write snapshot to this path")

    # move-card
    p = sub.add_parser("move-card", help="Move a card to a target list")
    p.add_argument("--card", required=True, help="Card id or short link")
    p.add_argument("--to", required=True, dest="target_list", help="Target list id")
    p.add_argument("--pr-url", default=None)

    # incident
    p = sub.add_parser("incident", help="Create or update an incident card")
    p.add_argument("--list", required=True, dest="incidents_list")
    p.add_argument("--title", required=True)
    p.add_argument("--body", required=True)
    p.add_argument("--severity", default="P2")

    # upsert-asset
    p = sub.add_parser("upsert-asset", help="Create or refresh an asset (table) card")
    p.add_argument("--list", required=True, dest="assets_list")
    p.add_argument("--table", required=True)
    p.add_argument("--rows", type=int, required=True)
    p.add_argument("--freshness", required=True, help="ISO 8601 timestamp")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    try:
        client = TrelloClient(TrelloConfig())
    except TrelloNotConfiguredError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    try:
        return _dispatch(args, client)
    except TrelloError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


def _dispatch(args: argparse.Namespace, client: TrelloClient) -> int:
    if args.cmd == "list-boards":
        boards = client.list_boards_for_member()
        for b in boards:
            print(f"{b.id}\t{b.name}")
        return 0

    if args.cmd == "list-lists":
        lists = client.list_lists_in_board(args.board)
        for li in lists:
            print(f"{li.id}\t{li.name}")
        return 0

    if args.cmd == "pull-board":
        snapshot = pull_board_snapshot(client, args.board, args.out)
        if args.out is None:
            print(json.dumps(snapshot, indent=2, sort_keys=True))
        return 0

    if args.cmd == "move-card":
        card = move_card_for_pr_event(client, args.card, args.target_list, args.pr_url)
        print(f"moved {card.id} -> list {card.list_id}")
        return 0

    if args.cmd == "incident":
        card = upsert_incident_card(
            client,
            incidents_list_id=args.incidents_list,
            title=args.title,
            body=args.body,
            severity=args.severity,
        )
        print(f"incident card: {card.id} {card.url}")
        return 0

    if args.cmd == "upsert-asset":
        card = upsert_asset_card(
            client,
            assets_list_id=args.assets_list,
            table_name=args.table,
            row_count=args.rows,
            freshness_iso=args.freshness,
        )
        print(f"asset card: {card.id} {card.url}")
        return 0

    raise SystemExit(f"unknown command: {args.cmd}")


if __name__ == "__main__":
    raise SystemExit(main())
