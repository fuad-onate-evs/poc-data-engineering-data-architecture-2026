"""
DAG: energy_kafka_bronze_ingestion
===================================
1. Generate seed data (Chile + FF)
2. Create Kafka topics
3. Publish seeds → Kafka topics
4. Consume Kafka → Databricks Bronze (Delta)
5. Validate Bronze row counts

Schedule: @once for POC, @hourly for production SCADA
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from airflow.utils.task_group import TaskGroup

default_args = {
    "owner": "data-eng",
    "retries": 2,
    "retry_delay": timedelta(minutes=2),
    "execution_timeout": timedelta(minutes=30),
}

PROJECT_DIR = "/opt/airflow/poc-data-arch"
BOOTSTRAP = "kafka:9092"

with DAG(
    dag_id="energy_kafka_bronze_ingestion",
    default_args=default_args,
    description="Kafka → Databricks Bronze ingestion for energy grid data",
    schedule="@once",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["ingestion", "kafka", "bronze", "energy"],
    doc_md="""
    ### Energy Kafka → Bronze Pipeline
    Generates seed data for 12 Chilean grid nodes + 12 FF nodes,
    publishes to Kafka, and consumes into Databricks Delta Bronze tables.
    """,
) as dag:
    # ─── Step 1: Generate seeds ──────────────────────────────
    generate_seeds = BashOperator(
        task_id="generate_seeds",
        bash_command=(
            f"cd {PROJECT_DIR} && python write/generate_seeds_unified.py --mode both --days 7"
        ),
    )

    # ─── Step 2: Create Kafka topics ─────────────────────────
    create_topics = BashOperator(
        task_id="create_kafka_topics",
        bash_command=(
            f"cd {PROJECT_DIR} && "
            f"python -m write.producers.seed_producer --bootstrap {BOOTSTRAP} --create-topics"
        ),
    )

    # ─── Step 3: Publish to Kafka ────────────────────────────
    with TaskGroup("publish_to_kafka") as publish_group:
        publish_chile = BashOperator(
            task_id="publish_chile",
            bash_command=(
                f"cd {PROJECT_DIR} && "
                f"python -m write.producers.seed_producer "
                f"--bootstrap {BOOTSTRAP} --dataset chile"
            ),
        )
        publish_ff = BashOperator(
            task_id="publish_ff",
            bash_command=(
                f"cd {PROJECT_DIR} && "
                f"python -m write.producers.seed_producer "
                f"--bootstrap {BOOTSTRAP} --dataset ff"
            ),
        )

    # ─── Step 4: Consume → Bronze ────────────────────────────
    consume_to_bronze = BashOperator(
        task_id="consume_to_bronze",
        bash_command=(
            f"cd {PROJECT_DIR} && "
            f"python -m write.consumers.bronze_writer "
            f"--bootstrap {BOOTSTRAP} --mode databricks-sql "
            f"--batch-size 500 --timeout 60"
        ),
    )

    # ─── Step 5: Validate Bronze ─────────────────────────────
    def validate_bronze(**kwargs):
        """Check Bronze tables have expected row counts."""
        import os

        from databricks import sql as dbsql

        conn = dbsql.connect(
            server_hostname=os.getenv("DATABRICKS_HOST"),
            http_path=os.getenv("DATABRICKS_HTTP_PATH"),
            access_token=os.getenv("DATABRICKS_TOKEN"),
        )
        cursor = conn.cursor()

        tables = ["scada_telemetry", "weather", "demand", "grid_dispatch", "plants"]
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM energy_catalog.bronze.{table}")
            count = cursor.fetchone()[0]
            expected_min = 100  # at least some data
            status = "✅" if count >= expected_min else "❌"
            print(f"  {status} {table}: {count} rows")
            if count < expected_min:
                raise ValueError(f"{table} has {count} rows, expected >= {expected_min}")

        # Check DLQ
        cursor.execute("SELECT COUNT(*) FROM energy_catalog.bronze.dead_letter_queue")
        dlq_count = cursor.fetchone()[0]
        print(f"  ⚠️  DLQ: {dlq_count} failed messages")

        cursor.close()
        conn.close()

    validate = PythonOperator(
        task_id="validate_bronze_counts",
        python_callable=validate_bronze,
    )

    # ─── DAG Flow ────────────────────────────────────────────
    generate_seeds >> create_topics >> publish_group >> consume_to_bronze >> validate
