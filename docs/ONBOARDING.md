# Onboarding Guide

> Renewable Energy Data Platform — POC for Evalueserve
> Target reader: new data engineer joining the team mid-Sprint.

## 1. Welcome

This POC builds an end-to-end data engineering pipeline for renewable-energy grid telemetry. The team is **3 Data Engineers + 1 PM**:

| Role | Focus |
|---|---|
| DE1 (Lead) | Architecture, CI/CD, data modeling |
| DE2 | Ingestion, Bronze + Silver pipelines |
| DE3 | Transformation, Gold layer, testing |
| PM | Planning, stakeholders, UAT |

The 10-week plan is in [poc-agile-plan-energy.md](poc-agile-plan-energy.md). The original POC brief (cost model, schedule, justification) is in [poc-overview.md](poc-overview.md). Architecture and conventions live in [../AGENTS.md](../AGENTS.md).

## 2. Prerequisites

| Tool | Required version | How to install |
|---|---|---|
| OS | WSL2 Ubuntu 22.04+, native Linux, or macOS | — |
| Python | 3.12+ | managed by `uv` |
| `uv` | latest | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Git | 2.30+ | `apt install git` (Ubuntu) |
| Docker | optional (only for local Kafka) | follow Docker docs |

You also need access to:
- The GitHub repo: <https://github.com/fuad-onate-evs/poc-data-engineering-data-architecture-2026>
- The Databricks **dev** workspace (ask DE1 for an invite)
- Kafka cluster credentials for **qa** and **prd** (ask DE2)
- The Trello/board with the sprint backlog (ask PM)

Configure your global git identity once:
```bash
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
```

## 3. First-time setup

```bash
# Clone and enter
git clone https://github.com/fuad-onate-evs/poc-data-engineering-data-architecture-2026.git
cd poc-data-engineering-data-architecture-2026   # or wherever you cloned to

# Create venv pinned to Python 3.12
uv venv --python 3.12

# Install runtime + dev deps
uv sync
uv sync --group dev

# Copy env template (edit with your secrets, or source envs/.env.dev)
cp .env.example .env

# Install pre-commit hooks (lint + commit-message format)
uv run pre-commit install
uv run pre-commit install --hook-type commit-msg

# Verify everything works
uv run pytest
uv run ruff check .
```

If `uv sync` fails on Airflow due to dependency conflicts, use Airflow's official constraints file (ask DE1).

## 4. Running the pipeline locally (no Databricks needed)

The `bronze_writer.py` consumer has a `local-delta` mode that writes Parquet to local files instead of Databricks — useful for offline development.

```bash
# 1. Generate seeds (Chile + FF, 3 days of hourly data)
uv run python ingestion/generate_seeds_unified.py --mode both --days 3

# 2. Start a local Kafka (optional — only if you want full produce/consume)
docker run -d --name kafka -p 9092:9092 \
  -e KAFKA_NODE_ID=1 \
  -e KAFKA_PROCESS_ROLES=broker,controller \
  -e KAFKA_LISTENERS=PLAINTEXT://0.0.0.0:9092,CONTROLLER://0.0.0.0:9093 \
  -e KAFKA_ADVERTISED_LISTENERS=PLAINTEXT://localhost:9092 \
  -e KAFKA_CONTROLLER_QUORUM_VOTERS=1@localhost:9093 \
  -e KAFKA_CONTROLLER_LISTENER_NAMES=CONTROLLER \
  -e KAFKA_LISTENER_SECURITY_PROTOCOL_MAP=PLAINTEXT:PLAINTEXT,CONTROLLER:PLAINTEXT \
  -e KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR=1 \
  -e CLUSTER_ID=poc-kafka-cluster-001 \
  confluentinc/cp-kafka:7.7.0

# 3. Create topics + publish seeds
uv run python -m ingestion.producers.seed_producer --create-topics --dataset chile
uv run python -m ingestion.producers.seed_producer --dataset ff

# 4. Consume → local Delta (writes Parquet under data/bronze/)
uv run python -m ingestion.consumers.bronze_writer --mode local-delta --timeout 30

# 5. Inspect output
ls data/bronze/
```

## 5. Running against QA / PRD

```bash
# Source the right env file before any pipeline command
source envs/.env.qa   # or envs/.env.prd

# Then publish + consume normally — bronze_writer picks databricks-sql mode
uv run python -m ingestion.producers.seed_producer --dataset chile
uv run python -m ingestion.consumers.bronze_writer --mode databricks-sql --timeout 60
```

PRD has stricter DQ thresholds (`DQ_FAIL_ON_WARN=true`). Confirm with DE1 before running anything against `energy_catalog` (the prd Unity Catalog).

## 6. Code conventions

- **Python 3.12+** with type hints on all public functions
- **Formatting:** ruff format (line length 100, double quotes)
- **Linting:** `uv run ruff check .` — must be clean
- **SQL:** sqlfluff (Databricks dialect) — `uv run sqlfluff lint transform/`
- **Naming:** `snake_case` everywhere. Tables: `seed_scada`, `stg_scada`, `fact_generation`
- **Kafka topics:** `energy.bronze.{table}` (6 partitions, snappy compression)
- **Delta tables:** partitioned by `(node_id, DATE(timestamp))`, autoOptimize enabled
- **Meta columns:** every Bronze row gets `_loaded_at`, `_source`, `_batch_id`, `_kafka_partition`, `_kafka_offset`, `_dataset`
- **Currency:** USD for Chile, Gil for FF — normalized to generic columns in Bronze (`spot_price`, `revenue`)
- **Conventional commits:** required (enforced by pre-commit hook). Format: `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`, `ci:`, `build:`, `perf:`
- **Env handling:** never hardcode secrets. Always source `envs/.env.{dev,qa,prd}` or use GitHub secrets for CI.

## 7. Testing & DQ

```bash
uv run pytest                                  # smoke tests (real suite Sprint 5)
uv run ruff check .                            # lint
uv run ruff format --check .                   # format
uv run sqlfluff lint transform/                # SQL lint (when dbt models land)
uv run pre-commit run --all-files              # everything pre-commit checks
```

## 8. Project structure tour

```
poc-data-eng/
├── ingestion/
│   ├── generate_seeds_unified.py    # Chile (real SEN) + FF (mapped) seeds
│   ├── config/settings.py            # KafkaConfig + DatabricksConfig + AppConfig
│   ├── producers/seed_producer.py    # CSV → Kafka topics
│   ├── consumers/bronze_writer.py    # Kafka → Bronze (3 modes)
│   └── schemas/bronze_ddl.sql        # Unity Catalog DDL
├── dags/energy_ingestion_dag.py     # Airflow DAG (full pipeline)
├── transform/                        # dbt project lands here (Sprint 2-3)
├── tests/test_smoke.py               # ast.parse smoke tests
├── envs/                             # env templates per stage
├── .github/workflows/                # CI/CD skeletons
└── docs/                             # this doc + brief + agile plan + widgets
```

## 9. Where to find what

| What | Where |
|---|---|
| Architecture & conventions | [../AGENTS.md](../AGENTS.md) |
| Sprint plan | [poc-agile-plan-energy.md](poc-agile-plan-energy.md) |
| Original POC brief | [poc-overview.md](poc-overview.md) |
| Visual widgets | [widgets/](widgets/) |
| Sprint board snapshots | [pm/](pm/) |
| Last-session handoff notes | [../SESSION_UPDATE.md](../SESSION_UPDATE.md) |

## 10. Common troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `uv sync` fails on Airflow | Conflicting transitive deps | Use Airflow's `constraints-3.12.txt` file; ask DE1 |
| `KafkaError: connection refused` | No local Kafka running | `docker start kafka` or check broker host in env file |
| `databricks.sql.exc.OperationalError: invalid token` | Expired DATABRICKS_TOKEN | Regenerate in workspace settings, update env file |
| Pre-commit rejects commit message | Not in conventional format | Prefix with `feat:`, `fix:`, `chore:`, etc. |
| `ruff check` fails on extracted file | Style drift | Run `uv run ruff check . --fix` then `uv run ruff format .` |
| `local-delta` mode writes Parquet not Delta | Known: name is misleading | Functional for dev; real Delta in databricks-sql mode |

## 11. Who to ask

| Question about | Ask |
|---|---|
| Architecture, CI/CD, data modeling, dbt | DE1 (lead) |
| Ingestion, Kafka, Bronze pipeline | DE2 |
| Silver/Gold transformations, tests | DE3 |
| Process, sprint scope, stakeholder ask | PM |

## 12. Sprint status

Currently in **Sprint 1 — Discovery & Architecture (W1–W2)**. See the Trello/board for live status. Next sprint kicks off when DE1 closes US-1.2 (Medallion architecture design).
