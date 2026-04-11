"""Trello integration for the POC data platform.

Public surface:
    TrelloClient — REST wrapper, auth via TrelloConfig
    TrelloError, TrelloNotConfiguredError — exceptions
    Board, TrelloList, Card — domain dataclasses
    pull_board_snapshot — sprint board → JSON
    move_card_for_pr_event — CI/CD card moves
    upsert_incident_card — pipeline alert → Trello
    upsert_asset_card — Bronze/Silver/Gold table → Trello
"""

from .client import TrelloClient, TrelloError, TrelloNotConfiguredError
from .models import Board, Card, TrelloList
from .sync import (
    move_card_for_pr_event,
    pull_board_snapshot,
    upsert_asset_card,
    upsert_incident_card,
)

__all__ = [
    "Board",
    "Card",
    "TrelloClient",
    "TrelloError",
    "TrelloList",
    "TrelloNotConfiguredError",
    "move_card_for_pr_event",
    "pull_board_snapshot",
    "upsert_asset_card",
    "upsert_incident_card",
]
