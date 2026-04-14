"""Trello integration for the POC data platform.

Public surface:
    TrelloClient — REST wrapper, auth via TrelloConfig
    TrelloError, TrelloNotConfiguredError — exceptions
    Board, TrelloList, Card, Label — domain dataclasses
    pull_board_snapshot — sprint board → JSON
    move_card_for_pr_event — CI/CD card moves
    upsert_incident_card — pipeline alert → Trello
    upsert_asset_card — Bronze/Silver/Gold table → Trello
    seed_board_from_plan, SeedReport — scaffold a board from a declarative YAML
"""

from .client import TrelloClient, TrelloError, TrelloNotConfiguredError
from .models import Board, Card, Label, TrelloList
from .sync import (
    SeedReport,
    move_card_for_pr_event,
    pull_board_snapshot,
    seed_board_from_plan,
    upsert_asset_card,
    upsert_incident_card,
)

__all__ = [
    "Board",
    "Card",
    "Label",
    "SeedReport",
    "TrelloClient",
    "TrelloError",
    "TrelloList",
    "TrelloNotConfiguredError",
    "move_card_for_pr_event",
    "pull_board_snapshot",
    "seed_board_from_plan",
    "upsert_asset_card",
    "upsert_incident_card",
]
