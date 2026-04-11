# 2026-04-10 — Bootstrap

> **Session type:** Project bootstrap
> **Owner:** Fuad Oñate — Tech Lead @ BairesDev (Evalueserve POC)
> **Repo:** <https://github.com/fuad-onate-evs/poc-data-engineering-data-architecture-2026>
> **Index:** [README.md](README.md)

---

## What this session did

1. **Validated the project context.** Found a major gap between docs and disk: project context doc claimed a fully built scaffold, but only loose root-level files existed (no git, ~30 WSL2 metadata files, two unextracted ZIPs containing competing stack iterations).
2. **Resolved the stack conflict.** Two ZIPs reflected two different architectures: `poc-data-eng.zip` (older, Trino + MinIO + Iceberg, generic events) vs `bronze-pipeline.zip` (newer, Databricks + Delta Lake, energy domain). Confirmed **Databricks-only** with the user; dropped the Trino/MinIO/Iceberg artifacts.
3. **Materialized the scaffold** from `bronze-pipeline.zip` into the documented directory layout: `ingestion/{config,producers,consumers,schemas}`, `dags/`, `transform/{seeds,seeds_ff}`, `tests/`, `envs/`, `.github/workflows/`, `docs/{pm,widgets}`.
4. **Bootstrapped project hygiene** with `uv`: `pyproject.toml` with runtime + dev deps (dbt-databricks, airflow, confluent-kafka, GE, databricks SDK, polars, pandas, pyarrow + ruff, pytest, pre-commit, mypy, sqlfluff). Added `.python-version`, `.gitignore`, `.editorconfig`, `.pre-commit-config.yaml`.
5. **Authored env templates** for dev/qa/prd with realistic DQ thresholds (lenient → strict).
6. **Wrote CI/CD skeletons** (`ci-dev-qa.yml`, `cd-production.yml`) — lint + smoke tests now, full pipeline TODO Sprint 4.
7. **Wrote a smoke test suite** (`tests/test_smoke.py`) that ast-parses every pipeline module.
8. **Authored docs**: `README.md` (rewritten with industry-grade conventions), `docs/ONBOARDING.md` (team walkthrough), `docs/poc-overview.md` (canonical project brief from the original Evalueserve doc).
9. **Reconciled `AGENTS.md`** to disk truth — Done/TODO blocks now reflect what genuinely exists.
10. **Cleaned cruft**: deleted ~30 `:Zone.Identifier` and `:mshield` files, browser-download dupes (`(1).py`, `ff2.html`, `sprint1.png (1).png`), older seed-generator variants, both ZIPs after extraction, empty `ff/` and `pm/` dirs.
11. **Initialized git**, made the first commit, added the GitHub remote (no push), installed pre-commit hooks.
12. **Adopted the [agents.md](https://agents.md/) convention** for the project context doc (`AGENTS.md`); added gitignore entries for tool-specific alternate filenames so local symlinks stay possible without polluting commits.
13. **Restructured** `SESSION_UPDATE.md` into a versioned `sessions/` directory for cross-session context.

---

## State at end of session

- **Tree** matches the layout in [../AGENTS.md](../AGENTS.md) (Databricks-only)
- **Deps** installed in `.venv` via `uv sync` + `uv sync --group dev` (writes `uv.lock`)
- **Smoke tests** green (`uv run pytest`)
- **Lint** clean (`uv run ruff check .`)
- **Git**: initialized, multiple commits landed, `origin` remote added, **not pushed**
- **Pre-commit**: hooks active (commit-msg + pre-commit)

---

## Next-up priorities

### Immediate

1. **Resolve `energy_ingestion_dag.py` env-awareness gap.** Currently hardcoded to `databricks-sql` mode + `kafka:9092` despite the project context claiming env-aware switching. Make it read `ENV` from settings.
2. **Build `ingestion/validators/source_validator.py`** (Sprint 2 / US-2.1). 9 pre-ingestion checks: file exists, schema, row counts, node coverage, uniqueness, ranges, timestamps, cross-ref, energy balance.
3. **Build `ingestion/dq/bronze_checks.py`** (Sprint 2 / US-2.1). Offline (CSV) + online (Databricks) modes, env-aware thresholds.

### Sprint 2-3 work

1. **Wire dbt with the `dbt-databricks` adapter.** Create `transform/dbt_project.yml`, `transform/profiles.yml`, then start on `transform/models/staging/{stg_scada,stg_weather,stg_demand,stg_dispatch,stg_plants}.sql`.
2. **Gold marts**: `fact_generation`, `fact_revenue`, `fact_dispatch`, `fact_carbon`, `dim_node`, `dim_plant`, `dim_time`.

### Sprint 4-5 work

1. **Databricks Asset Bundle** (`databricks.yml`) for DAB deploy.
2. **Flesh out CI/CD** workflows: source validation, offline DQ, Kafka integration test, DAB deploy with approval gate.
3. **Great Expectations** suites for Silver/Gold.
4. **Real test suite** (currently only smoke tests).

### After stakeholder review

1. **First push** to GitHub: `git push -u origin main` (do not push without confirming with the team).

---

## Open questions for next session

- Which **Databricks workspace** is actually provisioned for dev/qa/prd? The `.env.{qa,prd}` templates have placeholder hostnames.
- Which **Kafka cluster** are we using for qa/prd? Confluent Cloud, MSK, self-hosted? Determines SASL config and broker addresses.
- Does the team want to migrate from the custom `seed_producer.py + bronze_writer.py` to **Databricks Lakeflow Connect**? If so, the custom Kafka consumer becomes scaffolding only.
- Is the **Trello board** ("POC Evalueserve") the source of truth for sprint scope, or are we using GitHub Issues / Projects? (Possible Trello API integration into the CI/CD workflow — open follow-up.)

---

## Files to read first when resuming

| Order | File | Why |
|---|---|---|
| 1 | [../AGENTS.md](../AGENTS.md) | Architecture, conventions, current Done/TODO |
| 2 | [../docs/ONBOARDING.md](../docs/ONBOARDING.md) | Setup + commands + troubleshooting |
| 3 | [../docs/poc-agile-plan-energy.md](../docs/poc-agile-plan-energy.md) | Sprint plan with story-point ownership |
| 4 | [../ingestion/consumers/bronze_writer.py](../ingestion/consumers/bronze_writer.py) | Core consumer with 3 modes |
| 5 | [../ingestion/producers/seed_producer.py](../ingestion/producers/seed_producer.py) | CSV → Kafka producer |
| 6 | [../ingestion/config/settings.py](../ingestion/config/settings.py) | Centralized env-aware config |
| 7 | [../ingestion/schemas/bronze_ddl.sql](../ingestion/schemas/bronze_ddl.sql) | Bronze table DDL |
| 8 | [../dags/energy_ingestion_dag.py](../dags/energy_ingestion_dag.py) | Airflow DAG (env-awareness TODO) |

---

## Resume command

```bash
cd poc-data-eng
source .venv/bin/activate              # or use `uv run` for one-shots
source envs/.env.dev
uv run pytest                          # confirm baseline still green
```
