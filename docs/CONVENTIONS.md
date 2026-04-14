# Naming & style conventions

> Source of truth for reviewers. Link this doc from any PR comment enforcing a naming choice.

Covers Python code, SQL, Kafka topics, Delta tables, branches, commits, and energy-domain units. Extracted from [../CONTEXT.md](../CONTEXT.md) §Coding conventions and expanded with domain rules.

---

## 1. Python

| Aspect | Rule |
|---|---|
| Python version | 3.12+ — type hints on public functions and dataclass fields. |
| Style | `ruff format` (black-compatible, 100-char lines, double quotes). `ruff check` with rules `E, F, I, B, UP, N, C4, SIM, PT` — see [../pyproject.toml](../pyproject.toml). |
| Package layout | Top-level action-named packages: `write/` (ingest), `transform/` (dbt), `dags/` (Airflow). Avoid noun-named buckets like `utils/` — prefer a domain name (`write/validators/`, `write/dq/`). |
| Modules | `snake_case.py`. Module docstring describes what the module is *for*, not what it does. |
| Classes | `PascalCase`. Exception names end in `Error` (ruff N818). |
| Functions | `snake_case`. Verb-first (`load_scada_batch`, `upsert_incident_card`). |
| Constants | `UPPER_SNAKE_CASE` at module top. |
| Imports | `ruff`-sorted. No wildcard imports. Absolute imports everywhere (`from write.config.settings import config`). |
| Dataclasses | Prefer `@dataclass(frozen=True)` for config; use `field(default_factory=...)` for mutables. |
| Errors | Raise domain errors (`TrelloError`, `DQError`) not `RuntimeError` directly at API boundaries. |
| Logging | `log = logging.getLogger(__name__)` at module top. No `print()` in library code — CLI entry points can `print` user-facing output. |

## 2. SQL / dbt

| Aspect | Rule |
|---|---|
| Dialect | Databricks (sqlfluff enforced). |
| Line length | 120 (SQL-only; Python stays at 100). |
| Case | `lowercase_snake_case` for identifiers; SQL keywords uppercase (`SELECT`, `CREATE OR REPLACE TABLE`). |
| Table prefixes | `seed_*` raw CSV imports · `stg_*` Silver staging · `int_*` Silver intermediates · `fact_*` Gold facts · `dim_*` Gold dims. |
| Partition convention | Time-series tables partitioned by `(node_id, DATE(timestamp))`. |
| Column order | keys first → metrics → meta (`_loaded_at`, `_source`, `_batch_id`, …). |
| Nullability | Declare `NOT NULL` on every key column. Metrics default to nullable. |
| Comments | Use `COMMENT` on columns (Unity Catalog surfaces these in the UI). |

## 3. Kafka

| Aspect | Rule |
|---|---|
| Topic names | `energy.bronze.{table}` — e.g. `energy.bronze.scada_telemetry`. DLQ: `energy.bronze.dlq`. |
| Partitions | 6 per topic (scale up only when consumer lag forces it). |
| Compression | `snappy`. |
| Keys | Hash of `node_id` (preserves ordering per node across retries). |
| Values | JSON, UTF-8. Each message carries `dataset`, `timestamp`, `node_id`. |

## 4. Delta Bronze / Silver / Gold

| Aspect | Rule |
|---|---|
| Catalog | `energy_catalog` (dev: `energy_catalog_dev`, qa: `energy_catalog_qa`). |
| Schemas | `bronze`, `silver`, `gold`. |
| Meta columns on every Bronze row | `_loaded_at`, `_source`, `_batch_id`, `_kafka_partition`, `_kafka_offset`, `_dataset`. |
| Optimization | `delta.autoOptimize.optimizeWrite = true`. Z-ORDER on high-cardinality filter columns (`node_id`, `plant_id`) on Silver/Gold. |
| Idempotency | Writers MUST be safe to replay: Bronze uses `(_kafka_partition, _kafka_offset)` as the dedup key; Silver/Gold use `MERGE` on natural keys. |

## 5. Energy domain units

Normalize currency and units at Silver. Bronze carries raw values + context; don't do arithmetic in Bronze.

| Concept | Unit | Notes |
|---|---|---|
| Power | MW | Instantaneous. |
| Energy | MWh | Integrated over time. |
| Irradiance | W/m² | Solar resource. |
| Temperature | °C | Not Fahrenheit. |
| Wind speed | m/s | Not km/h. |
| Prices | USD/MWh (Chile), Gil/MWh (FF) | Currency normalization column: `spot_price_usd`. Keep `_dataset` to distinguish. |
| Revenue | USD (Chile), Gil (FF) | Same normalization rule. |
| Carbon offset | tCO₂e | Tonnes of CO₂ equivalent avoided vs. grid baseline. |
| Capacity factor | ratio ∈ [0, 1] | DQ check enforces bounds. |
| Availability | ratio ∈ [0, 1] | DQ check enforces bounds. |

**Currency normalization rule:** in Silver, add columns `*_usd` (and `*_gil` for FF) alongside the raw amount. Gold surfaces only the normalized columns. Never mix currencies in a single calculation.

## 6. Branches & PRs

Branch naming:

```text
feat/<card-shortlink>-<slug>      # new feature
fix/<card-shortlink>-<slug>       # bug fix
docs/<card-shortlink>-<slug>      # docs only
chore/<card-shortlink>-<slug>     # tooling / deps
refactor/<card-shortlink>-<slug>  # behavior-preserving refactor
test/<card-shortlink>-<slug>      # adding tests
```

- `<card-shortlink>` is the 8-char hex id from the Trello card URL (`https://trello.com/c/{shortlink}/...`). Required — the `trello-pr-sync.yml` workflow uses it to move the card between lists as the PR progresses.
- `<slug>` is 1–5 kebab-case words describing the change.
- Example: `feat/abc12345-add-source-validator`.

PRs:

- Target `develop` for day-to-day work. Release PRs go `develop → main`.
- ≥ 1 reviewer, CI green (lint, tests, `no-ai-attribution`, `trello-pr-sync`).
- **No AI/coding-agent attribution** in title, body, commit messages, or code — enforced by [../.github/workflows/no-ai-attribution.yml](../.github/workflows/no-ai-attribution.yml) and the pre-commit hook. Full rule in [../CONTRIBUTING.md](../CONTRIBUTING.md).

## 7. Commits

[Conventional Commits](https://www.conventionalcommits.org/) — enforced by pre-commit:

```text
feat:     new user-facing feature
fix:      bug fix
docs:     documentation only
chore:    tooling / deps / config
refactor: behavior-preserving restructure
test:     adding or fixing tests
ci:       CI/CD config changes
build:    build system / packaging
perf:     performance improvement
```

Optional scope in parens: `feat(trello): add seed-board CLI subcommand`.

Body (optional, wrap at ~72): explain *why*, not *what*. The diff shows what.

## 8. Environments

| Env | Kafka | Databricks catalog | Consumer mode | DQ strictness |
|---|---|---|---|---|
| dev | `localhost:9092`, PLAINTEXT | `energy_catalog_dev` | `local-delta` (Polars + Parquet) | lenient (null ≤ 5%, dupe ≤ 1%, freshness ≤ 7d, warn) |
| qa | SASL_SSL shared | `energy_catalog_qa` | `databricks-sql` | moderate (null ≤ 2%, dupe ≤ 0.5%, freshness ≤ 48h, warn) |
| prd | SASL_SSL, 3+ brokers | `energy_catalog` | `databricks-sql` | strict (null ≤ 0.1%, dupe ≤ 0.1%, freshness ≤ 2h, fail-on-warn) |

Configuration lives in `envs/.env.{dev,qa,prd}` — gitignored. Template at [../.env.example](../.env.example).

## 9. Files & directories

| Location | What it holds |
|---|---|
| `write/` | Ingest and write-to-Bronze code (producer, consumer, writers, validators, dq). |
| `transform/` | dbt project (Silver, Gold). |
| `dags/` | Airflow DAG definitions. |
| `docs/` | Team-facing documentation. Narrative plans, onboarding, domain specifics. |
| `docs/sprints/plan.yaml` | Source of truth for the Trello board — `seed-board` consumes it. |
| `sessions/` | Chronological session handoffs. Append-only. |
| `envs/` | Per-env dotfiles (all gitignored except `.env.example`). |
| `tests/` | pytest test modules, mirroring the package layout under test. |
| `scripts/hooks/` | Git-hook scripts invoked by `.pre-commit-config.yaml` and CI. |

---

## When this doc and reality disagree

**Reality wins** if reality is intentional. Update this doc in the same PR that intentionally diverges. A review comment citing this doc should be answered either by fixing the code *or* by changing the rule here.
