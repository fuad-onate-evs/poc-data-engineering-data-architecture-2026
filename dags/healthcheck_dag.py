"""
DAG: healthcheck
================

Tiny liveness probe for the Airflow environment. One `BashOperator` that
prints an OK marker — if the DAG can be scheduled, parsed, and executed
end-to-end, the scheduler + executor + worker chain is wired correctly.

Closes the acceptance criterion "UI running, health-check DAG green" of
US-1.1 (`docs/sprints/plan.yaml`).

Schedule: `@daily`. Zero retries — a healthcheck that retries hides
scheduling problems instead of surfacing them.

Usage:
    airflow dags test healthcheck 2026-04-14
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator

default_args = {
    "owner": "DE3",
    "retries": 0,
    "execution_timeout": timedelta(minutes=2),
}

with DAG(
    dag_id="healthcheck",
    default_args=default_args,
    description="Airflow liveness probe — prints OK if scheduler + worker are healthy",
    schedule="@daily",
    start_date=datetime(2026, 4, 14),
    catchup=False,
    tags=["meta", "healthcheck"],
    doc_md=__doc__,
) as dag:
    ping = BashOperator(
        task_id="ping",
        bash_command="echo 'airflow-healthcheck OK' && date -u +%FT%TZ",
    )
