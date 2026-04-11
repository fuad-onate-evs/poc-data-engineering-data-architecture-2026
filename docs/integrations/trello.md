# Trello integration

> Lives in [`write/integrations/trello/`](../../write/integrations/trello/). First-class module: client, models, sync layer, CLI, tests, and a GitHub Actions workflow.

The integration covers four use cases on a single board:

1. **Sprint board sync** — pull a Trello board's state to a JSON snapshot for analytics and GitHub Issues mirroring
2. **PR ↔ card sync** — auto-move cards between Backlog → In Progress → Review → Done as PR events fire
3. **Pipeline alerts** — turn DAG/DQ failures into idempotent incident cards
4. **Asset tracking** — one card per Bronze/Silver/Gold table, refreshed with row count + freshness on every run

## 1. Authentication

You need a **Trello API key** and a **user token**.

1. Sign in to Trello and visit <https://trello.com/app-key>
2. Copy your **API key** → `TRELLO_API_KEY`
3. Click **Token** at the top of the page, authorize, copy the long string → `TRELLO_TOKEN`
4. Open your board → URL → grab the board ID (the chunk between `/b/` and the next `/`) → `TRELLO_BOARD_ID`

Tokens are scoped to your user. Use a service account in qa/prd, not your personal account.

## 2. Discover list IDs

Lists are board-specific. Once you have the board ID:

```bash
source envs/.env.dev   # or wherever you put the secrets
uv run python -m write.integrations.trello.cli list-lists --board "$TRELLO_BOARD_ID"
```

Output is `<list_id>\t<list_name>`. Map them to env vars:

| Trello list | Env var |
|---|---|
| Backlog | `TRELLO_LIST_ID_BACKLOG` |
| TODO / In Progress | `TRELLO_LIST_ID_IN_PROGRESS` |
| Review | `TRELLO_LIST_ID_REVIEW` |
| Done | `TRELLO_LIST_ID_DONE` |
| Incidents | `TRELLO_LIST_ID_INCIDENTS` |
| Assets | `TRELLO_LIST_ID_ASSETS` |

If the lists don't exist yet, create them in the Trello UI first.

## 3. CLI reference

All commands read auth from the active env file (`envs/.env.<env>` or `.env`).

```bash
# List boards visible to the auth token
uv run python -m write.integrations.trello.cli list-boards

# List columns on a board
uv run python -m write.integrations.trello.cli list-lists --board <board_id>

# Snapshot a board to JSON (lists + cards)
uv run python -m write.integrations.trello.cli pull-board --board <board_id> --out snapshot.json

# Move a card between lists (used by CI on PR events)
uv run python -m write.integrations.trello.cli move-card \
  --card <card_short_link> \
  --to <list_id> \
  --pr-url https://github.com/.../pull/123

# Create or comment on an incident card (idempotent on title)
uv run python -m write.integrations.trello.cli incident \
  --list "$TRELLO_LIST_ID_INCIDENTS" \
  --title "DAG energy_ingestion failed" \
  --body "task=consume_to_bronze; error=ConnectionError" \
  --severity P1

# Create or refresh an asset card for a Bronze/Silver/Gold table
uv run python -m write.integrations.trello.cli upsert-asset \
  --list "$TRELLO_LIST_ID_ASSETS" \
  --table bronze.scada_telemetry \
  --rows 1234 \
  --freshness 2026-04-11T10:00:00Z
```

## 4. Programmatic API

```python
from write.config.settings import TrelloConfig
from write.integrations.trello import (
    TrelloClient,
    pull_board_snapshot,
    move_card_for_pr_event,
    upsert_incident_card,
    upsert_asset_card,
)

client = TrelloClient(TrelloConfig())

# Sprint snapshot
snap = pull_board_snapshot(client, "abc123", out_path=None)

# CI card move
move_card_for_pr_event(client, "shortlink", target_list_id="L_REVIEW", pr_url="...")

# Incident card from a DAG callback
def on_failure(context):
    upsert_incident_card(
        client,
        incidents_list_id=os.environ["TRELLO_LIST_ID_INCIDENTS"],
        title=f"DAG {context['dag'].dag_id} failed",
        body=str(context.get("exception")),
        severity="P1",
    )

# Asset card refresh from a dbt run callback
upsert_asset_card(
    client,
    assets_list_id=os.environ["TRELLO_LIST_ID_ASSETS"],
    table_name="bronze.scada_telemetry",
    row_count=12_345,
    freshness_iso=datetime.now(UTC).isoformat(),
)
```

## 5. CI/CD wiring

[`.github/workflows/trello-pr-sync.yml`](../../.github/workflows/trello-pr-sync.yml) runs on PR events and moves cards based on the branch name. To enable it, add these repo secrets at **Settings → Secrets and variables → Actions**:

| Secret | Where it comes from |
|---|---|
| `TRELLO_API_KEY` | <https://trello.com/app-key> |
| `TRELLO_TOKEN` | Click "Token" on the same page |
| `TRELLO_LIST_ID_IN_PROGRESS` | `cli list-lists` output |
| `TRELLO_LIST_ID_REVIEW` | `cli list-lists` output |
| `TRELLO_LIST_ID_DONE` | `cli list-lists` output |

The workflow extracts the card short link from the branch name. Branch convention:

```
feat/abc12345-add-source-validator
fix/abc12345-bronze-writer-currency-bug
docs/abc12345-update-onboarding
```

The 8-char hex chunk (`abc12345`) is the Trello card short link visible in any card URL: `https://trello.com/c/abc12345/...`. Branches without a card id no-op gracefully (the workflow skips the move step).

## 6. Idempotency guarantees

The sync layer is built around the assumption that operations can replay safely:

- **Incident cards** — match on the full title (`[INCIDENT] [P1] DAG ... failed`). A duplicate call appends a comment instead of creating a second card.
- **Asset cards** — match on the table name (`[ASSET] bronze.scada_telemetry`). A duplicate call rewrites the description to reflect the latest snapshot.
- **PR card moves** — Trello accepts repeated moves to the same list as no-ops; the comment gets re-posted, which is acceptable as a per-event audit trail.
- **Board snapshots** — read-only and write to a content-addressed file; safe to run on a cron.

## 7. Failure modes

| Symptom | Likely cause | Fix |
|---|---|---|
| `TrelloNotConfiguredError` | `TRELLO_API_KEY` or `TRELLO_TOKEN` empty | Set them in `envs/.env.<env>` |
| `TrelloError: ... 401 Unauthorized` | Token expired or revoked | Regenerate at <https://trello.com/app-key> |
| `TrelloError: ... 404 Not Found` | Wrong board/list/card id | Re-run `cli list-lists` to refresh ids |
| `TrelloError: ... 429 Too Many Requests` | Hitting Trello rate limit (300 req / 10s per token) | Add backoff, or split sync work across tokens |
| Workflow runs but card doesn't move | Branch name has no 8-char hex segment | Rename the branch to include the card short link |
| Workflow skipped entirely | `TRELLO_API_KEY` secret not set on the repo | Add it under repo settings (the workflow gates on it) |

## 8. Operational notes

- **Rate limit**: Trello allows 300 requests per 10 seconds per token. The client uses tenacity with exponential backoff (3 attempts, 0.5s → 4s) for transient errors.
- **5xx is retried, 4xx is not**: 4xx is a contract bug (bad token, bad list id) and retrying just hides it.
- **Service-account token**: Don't use a personal token in CI. Create a Trello bot user, grant it board access, and use its token as `TRELLO_TOKEN` in GitHub secrets.
- **Card short links** (8-char) are stable across renames and live forever; **card ids** (24-char) are also stable. Either can be passed to commands that take `--card`.

## 9. Tests

```bash
uv run pytest tests/integrations/trello/ -v
```

22 tests cover the client (HTTP mocked with `responses`) and the sync layer (tested with a fake in-memory client). Both retry behavior (5xx retried, 4xx not retried) and idempotency are exercised.
