# CONTEXT.md — POC Data Engineering & Architecture Platform

> Canonical project context for contributors and coding agents. If your tooling expects a different filename (`AGENTS.md`, `CLAUDE.md`, `.cursorrules`, etc.), symlink it locally — those alternate names are gitignored.

## Project overview

Renewable energy grid data platform POC for **Evalueserve**. Ingests SCADA telemetry, weather, demand, and dispatch data from 12 Chilean SEN nodes (real CEN references) + 12 Final Fantasy Gaia nodes (mapped from Chile with realistic divergence). Pipeline: **Seeds → Kafka → Databricks Bronze (Delta Lake)**, orchestrated by Airflow, validated by DQ checks.

**Stack:** Airflow · Kafka · Databricks Photon · Delta Lake · GitHub Actions · dbt-core · Great Expectations
**Business domain:** Electricity provision from renewable energy sources (solar, wind, hydro, geothermal, tidal)
**Timeline:** 10-week POC, 5 sprints, 3 DEs + 1 PM
**Target cost:** $400–$1,000 USD/month (pay-as-you-go)
**Repo:** <https://github.com/fuad-onate-evs/poc-data-engineering-data-architecture-2026>

## Architecture

```
Seeds (CSV) → Source Validator → Kafka (5 topics) → Bronze Writer → Databricks Delta (Bronze)
                                                                          ↓
                                                              DQ Checks (gate)
                                                                          ↓
                                                              dbt (Silver → Gold)
                                                                          ↓
                                                              Power BI / Tableau / Superset
```

### Medallion layers

- **Bronze** (`energy_catalog.bronze.*`): Raw landing from Kafka. 5 tables + DLQ. Partitioned by `(node_id, DATE(timestamp))`. Meta columns: `_loaded_at`, `_source`, `_batch_id`, `_kafka_partition`, `_kafka_offset`, `_dataset`.
- **Silver** (`energy_catalog.silver.*`): TODO — cleaned, typed, aligned timeseries, weather-generation joins, SCD2 for asset registry.
- **Gold** (`energy_catalog.gold.*`): TODO — `fact_generation`, `fact_revenue`, `fact_dispatch`, `fact_carbon`, dims.

### Environments

| Env | Kafka | Databricks catalog | Consumer mode | DQ strictness |
|-----|-------|--------------------|---------------|---------------|
| dev | localhost:9092, PLAINTEXT | `energy_catalog_dev` | `local-delta` | Lenient |
| qa  | SASL_SSL, shared cluster | `energy_catalog_qa` | `databricks-sql` | Moderate |
| prd | SASL_SSL, 3+ brokers | `energy_catalog` | `databricks-sql` | Strict (fail-on-warn) |

## Project structure

```
poc-data-eng/
├── README.md                       # Concise project overview + quick start
├── CONTEXT.md                      # ← you are here (canonical project context)
├── sessions/                       # Cross-session handoff archive (latest first)
├── pyproject.toml                  # uv-managed deps + tool configs
├── .python-version                 # 3.12
├── .gitignore .editorconfig .pre-commit-config.yaml
├── .env.example
├── envs/
│   ├── .env.dev
│   ├── .env.qa
│   └── .env.prd
├── .github/workflows/
│   ├── ci-dev-qa.yml               # Stub: lint + smoke tests on PR
│   └── cd-production.yml           # Stub: DAB deploy with approval gate
├── write/                          # ingest/produce/consume into Bronze
│   ├── generate_seeds_unified.py   # Chile (real SEN) + FF (mapped + jitter)
│   ├── config/settings.py          # KafkaConfig, DatabricksConfig, TrelloConfig, AppConfig
│   ├── producers/seed_producer.py  # CSV → Kafka topics
│   ├── consumers/bronze_writer.py  # Kafka → Bronze (3 modes: local-delta, databricks-sql, spark)
│   ├── integrations/
│   │   └── trello/                 # First-class Trello sync (PM + CI/CD + alerts + assets)
│   └── schemas/bronze_ddl.sql      # Unity Catalog DDL for Bronze tables + DLQ
├── dags/
│   └── energy_ingestion_dag.py     # Airflow DAG (currently single-env, see TODO)
├── transform/
│   ├── seeds/                      # Chile CSV outputs (gitignored)
│   └── seeds_ff/                   # FF CSV outputs (gitignored)
├── tests/
│   └── test_smoke.py               # ast.parse smoke tests (real suite Sprint 5)
└── docs/
    ├── ONBOARDING.md               # Team walkthrough
    ├── poc-overview.md             # Original POC brief (cost, schedule)
    ├── poc-agile-plan-energy.md    # Bilingual sprint plan
    ├── pm/sprint1.png              # Sprint board snapshot
    └── widgets/                    # Interactive Chile + FF grid sims
```

## Key commands

```bash
# ── Setup ──
uv venv --python 3.12
uv sync                                          # runtime deps
uv sync --group dev                              # dev deps (ruff, pytest, pre-commit)
uv run pre-commit install
uv run pre-commit install --hook-type commit-msg
cp .env.example .env

# ── Generate seed data ──
uv run python write/generate_seeds_unified.py --mode both --days 7
uv run python write/generate_seeds_unified.py --mode chile --days 30  # prd volume

# ── Kafka produce + consume ──
uv run python -m write.producers.seed_producer --create-topics --dataset chile
uv run python -m write.producers.seed_producer --dataset ff
uv run python -m write.consumers.bronze_writer --mode local-delta --timeout 30      # dev
uv run python -m write.consumers.bronze_writer --mode databricks-sql --timeout 60   # qa/prd

# ── Lint, format, test ──
uv run ruff check .
uv run ruff format .
uv run pytest
uv run sqlfluff lint transform/                  # when dbt models land

# ── Airflow ──
airflow dags trigger energy_ingestion_dag
```

## Data sources

### Chile (12 SEN nodes, Arica → Coyhaique)

Real data references from Coordinador Eléctrico Nacional (CEN):
- SCADA real-time: `coordinador.cl/operacion/.../generacion-real-horaria-scada/`
- Hourly gen CSV: `coordinador.cl/reportes-y-estadisticas/` → "Generación Horaria por Central"
- API Portal: `portal.api.coordinador.cl/`
- CNE Energía Abierta: `energiaabierta.cl/` + `desarrolladores.energiaabierta.cl/`

Each node includes `cen_barra` reference for joining with real CEN API data.

### Final Fantasy (12 Gaia nodes, mapped from Chile)

Chile is the source of truth. FF nodes diverge via:
- `source_overrides`: independent capacity values (not scaled from Chile)
- `cap_jitter`: random ±15-30% per source type
- `unique_traits`: demand shape modifiers (night boost, evening spike, heating, etc.)
- Mapping table: `transform/seeds_ff/chile_to_ff_mapping.csv`

## Coding conventions

- **Python**: 3.12+, type hints, dataclasses for config, f-strings
- **Formatting**: ruff format (line length 100, double quotes)
- **Linting**: ruff (`uv run ruff check .`); SQL via sqlfluff (Databricks dialect)
- **Tests**: pytest under `tests/`
- **Naming**: `snake_case` everywhere. Tables: `seed_scada`, `stg_scada`, `fact_generation`
- **Kafka topics**: `energy.bronze.{table}` (6 partitions, snappy compression)
- **Delta tables**: partitioned by `(node_id, DATE(timestamp))`, autoOptimize enabled
- **Meta columns**: every Bronze row gets `_loaded_at`, `_source`, `_batch_id`, `_kafka_partition`, `_kafka_offset`, `_dataset`
- **DQ**: always run offline checks in CI, online checks post-ingestion
- **Env**: never hardcode credentials, use `envs/.env.{dev,qa,prd}` + GitHub Secrets for CI/CD
- **Currency**: USD for Chile, Gil for FF — normalized to generic columns in Bronze (`spot_price`, `revenue`)
- **Commits**: Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`, `ci:`, `build:`, `perf:`) — enforced by pre-commit hook

## Current status

### Done (after 2026-04-10 bootstrap session)

- [x] Project scaffold + git initialized
- [x] `pyproject.toml` (uv-managed, runtime + dev deps incl. ruff, pytest, mypy, sqlfluff, pre-commit)
- [x] Tooling configs: ruff, pytest, mypy, sqlfluff, pre-commit, editorconfig
- [x] Env file templates: `.env.example`, `envs/.env.{dev,qa,prd}`
- [x] CI/CD workflow skeletons (lint + smoke tests; full pipeline TODO)
- [x] Seed generator (Chile 12 nodes + FF 12 nodes with realistic divergence)
- [x] Kafka producer (`seed_producer.py`)
- [x] Kafka consumer → Bronze (`bronze_writer.py`, 3 modes: local-delta / databricks-sql / spark)
- [x] Bronze DDL (Unity Catalog, 5 tables + DLQ)
- [x] Settings module (KafkaConfig, DatabricksConfig, TrelloConfig, AppConfig)
- [x] Trello integration (`write/integrations/trello/`) — first-class module: client + 4 sync use cases (board pull, PR card move, incident, asset upsert) + CLI + 22 unit tests + GHA workflow + docs
- [x] Airflow DAG (`energy_ingestion_dag.py` — single-env, **not yet env-aware**)
- [x] README + ONBOARDING + POC overview docs
- [x] Interactive simulation widgets (Chile + FF)

### TODO (deferred to next sessions)

- [ ] Source validator (`write/validators/source_validator.py`) — Sprint 2
- [ ] Bronze DQ checks (`write/dq/bronze_checks.py`) — Sprint 2
- [ ] Make `energy_ingestion_dag.py` env-aware (currently hardcoded `databricks-sql` mode + `kafka:9092`)
- [ ] dbt project: `dbt_project.yml`, `profiles.yml` (databricks adapter), Silver staging models, Gold marts
- [ ] Databricks Asset Bundle (`databricks.yml`) — Sprint 4
- [ ] Great Expectations suites — Sprint 5
- [ ] CI/CD: full integration test, source validation, DAB deploy with approval gate — Sprint 4
- [ ] Real test suite (currently only smoke tests) — Sprint 5
- [ ] Power BI / Tableau / Superset dashboards — Sprint 5
- [ ] OpenMetadata / Unity Catalog tagging — Sprint 3
- [ ] UAT test cases for grid ops / trading / compliance stakeholders — Sprint 5
