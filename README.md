# POC: Renewable Energy Data Platform

> **Status:** Sprint 1 — Discovery & Architecture
> **Client:** Evalueserve
> **Stack:** Airflow · Kafka · Databricks Photon · Delta Lake · dbt · GitHub Actions

End-to-end data engineering POC for renewable-energy grid telemetry. Ingests SCADA, weather, demand, and dispatch data from 12 Chilean SEN nodes (real CEN references) and 12 Final Fantasy Gaia nodes (mapped from Chile with realistic divergence). Pipeline: **Seeds → Kafka → Databricks Bronze (Delta Lake)**, orchestrated by Airflow, validated by DQ checks.

10-week timeline · 5 sprints · 3 DEs + 1 PM · target cost $400–$1,000/month.

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

**Medallion layers**

- **Bronze** (`energy_catalog.bronze.*`) — raw landing from Kafka. 5 tables + DLQ. Partitioned by `(node_id, DATE(timestamp))`. Meta columns for lineage + idempotency.
- **Silver** (`energy_catalog.silver.*`) — *TODO* — typed, cleaned, weather-generation joins.
- **Gold** (`energy_catalog.gold.*`) — *TODO* — `fact_generation`, `fact_revenue`, `fact_dispatch`, `fact_carbon`, dims.

## Quick start

Prerequisites: WSL2/Linux/macOS, Python 3.12+, [uv](https://docs.astral.sh/uv/), git.

```bash
# 1. Install uv (one-time)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Sync dependencies
uv venv --python 3.12
uv sync                       # runtime
uv sync --group dev           # ruff, pytest, pre-commit, sqlfluff

# 3. Configure env
cp .env.example .env          # edit secrets, or source envs/.env.dev

# 4. Generate seed data
uv run python ingestion/generate_seeds_unified.py --mode both --days 3

# 5. Run smoke tests + lint
uv run pytest
uv run ruff check .
```

For the full pipeline (Kafka → Bronze) and onboarding details see [docs/ONBOARDING.md](docs/ONBOARDING.md).

## Project layout

```
poc-data-eng/
├── ingestion/                 # producers, consumers, config, schemas, seed generator
│   ├── generate_seeds_unified.py
│   ├── config/settings.py
│   ├── producers/seed_producer.py
│   ├── consumers/bronze_writer.py
│   └── schemas/bronze_ddl.sql
├── dags/energy_ingestion_dag.py
├── transform/{seeds,seeds_ff}/   # seed CSV outputs (gitignored)
├── tests/                     # smoke tests (real suite Sprint 5)
├── envs/.env.{dev,qa,prd}     # env templates (gitignored secrets)
├── .github/workflows/         # CI/CD skeletons
└── docs/
    ├── ONBOARDING.md          # team walkthrough
    ├── poc-overview.md        # canonical POC brief
    ├── poc-agile-plan-energy.md
    ├── widgets/               # interactive Chile + FF grid visualizations
    └── pm/                    # sprint board screenshots
```

## Documentation

- [CLAUDE.md](CLAUDE.md) — full project context (architecture, conventions, current status)
- [docs/ONBOARDING.md](docs/ONBOARDING.md) — first-day team walkthrough
- [docs/poc-overview.md](docs/poc-overview.md) — original POC brief (description, cost, schedule)
- [docs/poc-agile-plan-energy.md](docs/poc-agile-plan-energy.md) — bilingual sprint plan (5 sprints, 6 epics, 15 stories, 148 SP)
- [docs/widgets/](docs/widgets/) — interactive Chile + FF grid simulations
- GitHub: <https://github.com/fuad-onate-evs/poc-data-engineering-data-architecture-2026>

## License

Proprietary — Evalueserve POC.
