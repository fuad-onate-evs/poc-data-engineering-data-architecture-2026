"""
Kafka Consumer → Databricks Bronze (Delta Lake)
================================================
Consumes from energy.bronze.* topics and writes to Delta tables
in Databricks Unity Catalog (energy_catalog.bronze.*).

Two write modes:
  1. databricks-sql: Uses Databricks SQL Connector (serverless/warehouse)
  2. spark: Uses Databricks Connect / PySpark (cluster)

Usage:
    python -m write.consumers.bronze_writer --mode databricks-sql
    python -m write.consumers.bronze_writer --mode spark
    python -m write.consumers.bronze_writer --mode local-delta  # local testing
"""

import argparse
import contextlib
import json
import logging
import os
import uuid
from datetime import UTC, datetime

from confluent_kafka import Consumer, KafkaError

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# Topic → Bronze table mapping
TOPIC_TABLE_MAP = {
    "energy.bronze.scada": "scada_telemetry",
    "energy.bronze.weather": "weather",
    "energy.bronze.demand": "demand",
    "energy.bronze.dispatch": "grid_dispatch",
    "energy.bronze.plants": "plants",
}

# Topic → columns to extract (order matters for INSERT)
TOPIC_COLUMNS = {
    "energy.bronze.scada": [
        "timestamp",
        "node_id",
        "solar_mw",
        "wind_mw",
        "hydro_mw",
        "geothermal_mw",
        "tidal_mw",
        "total_generation_mw",
    ],
    "energy.bronze.weather": [
        "timestamp",
        "node_id",
        "climate",
        "solar_irradiance_wm2",
        "wind_speed_ms",
        "temperature_c",
        "humidity_pct",
    ],
    "energy.bronze.demand": [
        "timestamp",
        "node_id",
        "demand_mw",
        "residential_pct",
        "industrial_pct",
        "commercial_pct",
    ],
    "energy.bronze.dispatch": [
        "timestamp",
        "node_id",
        "total_generation_mw",
        "total_demand_mw",
        "balance_mw",
        "curtailment_mw",
        "spot_price",
        "ppa_price",
        "revenue",
        "curtailment_cost",
        "carbon_offset_tco2e",
    ],
    "energy.bronze.plants": [
        "plant_id",
        "node_id",
        "node_name",
        "region",
        "source_type",
        "capacity_mw",
        "climate",
        "ppa_price_mwh",
        "lat",
        "lon",
        "cen_barra",
    ],
}


class BronzeWriter:
    """Base class for writing Kafka messages to Bronze Delta tables."""

    def __init__(self, catalog: str = "energy_catalog", schema: str = "bronze"):
        self.catalog = catalog
        self.schema = schema
        self.batch_id = str(uuid.uuid4())[:8]
        self._written = 0
        self._errors = 0

    def _full_table(self, table: str) -> str:
        return f"{self.catalog}.{self.schema}.{table}"

    def _enrich_row(self, row: dict, topic: str, partition: int, offset: int) -> dict:
        """Add meta columns for lineage."""
        row["_loaded_at"] = datetime.now(UTC).isoformat()
        row["_source"] = topic
        row["_batch_id"] = self.batch_id
        row["_kafka_partition"] = partition
        row["_kafka_offset"] = offset
        row["_dataset"] = row.get("_dataset", "unknown")
        return row

    def _normalize_dispatch_cols(self, row: dict) -> dict:
        """Normalize currency-specific column names to generic ones."""
        for currency in ("usd", "gil"):
            for src, dst in [
                (f"spot_price_{currency}", "spot_price"),
                (f"ppa_price_{currency}", "ppa_price"),
                (f"revenue_{currency}", "revenue"),
                (f"curtailment_cost_{currency}", "curtailment_cost"),
            ]:
                if src in row:
                    row[dst] = row.pop(src)
        # Also handle ppa_price_mwh variants
        for k in list(row.keys()):
            if k.startswith("ppa_price_") and k != "ppa_price":
                row["ppa_price_mwh"] = row.pop(k)
        return row

    def write_batch(self, topic: str, messages: list[dict]):
        raise NotImplementedError

    def write_dlq(self, topic: str, raw: bytes, error: str, partition: int, offset: int):
        raise NotImplementedError


class DatabricksSQLWriter(BronzeWriter):
    """Write to Databricks via SQL Connector (serverless warehouse)."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        from databricks import sql as dbsql

        self.conn = dbsql.connect(
            server_hostname=os.getenv("DATABRICKS_HOST"),
            http_path=os.getenv("DATABRICKS_HTTP_PATH"),
            access_token=os.getenv("DATABRICKS_TOKEN"),
        )
        log.info(f"🔌 Connected to Databricks SQL: {os.getenv('DATABRICKS_HOST')}")

    def write_batch(self, topic: str, messages: list[dict]):
        table = TOPIC_TABLE_MAP[topic]
        full_table = self._full_table(table)
        cols = TOPIC_COLUMNS[topic]
        meta_cols = [
            "_loaded_at",
            "_source",
            "_batch_id",
            "_kafka_partition",
            "_kafka_offset",
            "_dataset",
        ]
        all_cols = cols + meta_cols

        cursor = self.conn.cursor()
        placeholders = ", ".join(["%s"] * len(all_cols))
        col_names = ", ".join(all_cols)
        sql = f"INSERT INTO {full_table} ({col_names}) VALUES ({placeholders})"

        rows = []
        for msg in messages:
            msg = self._normalize_dispatch_cols(msg)
            values = [msg.get(c) for c in all_cols]
            rows.append(values)

        try:
            cursor.executemany(sql, rows)
            self._written += len(rows)
            log.info(f"  ✅ {len(rows)} rows → {full_table}")
        except Exception as e:
            self._errors += len(rows)
            log.error(f"  ❌ Failed writing to {full_table}: {e}")
            raise
        finally:
            cursor.close()

    def write_dlq(self, topic, raw, error, partition, offset):
        cursor = self.conn.cursor()
        cursor.execute(
            f"INSERT INTO {self._full_table('dead_letter_queue')} "
            f"(received_at, topic, partition_id, offset_id, value, error_message, _batch_id) "
            f"VALUES (%s, %s, %s, %s, %s, %s, %s)",
            [
                datetime.now(UTC).isoformat(),
                topic,
                partition,
                offset,
                raw.decode("utf-8", errors="replace"),
                str(error),
                self.batch_id,
            ],
        )
        cursor.close()


class SparkWriter(BronzeWriter):
    """Write to Databricks via PySpark / Databricks Connect."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        from pyspark.sql import SparkSession

        self.spark = (
            SparkSession.builder.appName("energy-bronze-ingestion")
            .config(
                "spark.sql.catalog.energy_catalog",
                "org.apache.spark.sql.delta.catalog.DeltaCatalog",
            )
            .getOrCreate()
        )
        log.info("🔌 SparkSession initialized")

    def write_batch(self, topic: str, messages: list[dict]):
        table = TOPIC_TABLE_MAP[topic]
        full_table = self._full_table(table)

        for msg in messages:
            self._normalize_dispatch_cols(msg)

        df = self.spark.createDataFrame(messages)
        df.write.format("delta").mode("append").saveAsTable(full_table)
        self._written += len(messages)
        log.info(f"  ✅ {len(messages)} rows → {full_table} (Spark)")


class LocalDeltaWriter(BronzeWriter):
    """Write to local Delta Lake files (for testing without Databricks)."""

    def __init__(self, output_dir: str = "data/bronze", **kwargs):
        super().__init__(**kwargs)
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        log.info(f"📁 Local Delta writer: {output_dir}")

    def write_batch(self, topic: str, messages: list[dict]):
        import polars as pl

        table = TOPIC_TABLE_MAP[topic]
        path = os.path.join(self.output_dir, table)
        os.makedirs(path, exist_ok=True)

        for msg in messages:
            self._normalize_dispatch_cols(msg)

        df = pl.DataFrame(messages)
        out_file = os.path.join(path, f"batch_{self.batch_id}_{len(messages)}.parquet")
        df.write_parquet(out_file)
        self._written += len(messages)
        log.info(f"  ✅ {len(messages)} rows → {out_file}")


class BronzeConsumer:
    """Kafka consumer that writes to Bronze Delta tables."""

    def __init__(
        self,
        writer: BronzeWriter,
        bootstrap_servers: str,
        topics: list[str] | None = None,
        batch_size: int = 500,
    ):
        self.writer = writer
        self.batch_size = batch_size
        self.topics = topics or list(TOPIC_TABLE_MAP.keys())
        self.consumer = Consumer(
            {
                "bootstrap.servers": bootstrap_servers,
                "group.id": "energy-bronze-ingestion",
                "auto.offset.reset": "earliest",
                "enable.auto.commit": False,
            }
        )
        self.consumer.subscribe(self.topics)
        log.info(f"📥 Subscribed to {len(self.topics)} topics")

    def run(self, max_messages: int = 0, timeout: float = 30.0):
        """Consume and write in micro-batches."""
        buffers: dict[str, list[dict]] = {t: [] for t in self.topics}
        total = 0
        empty_polls = 0
        max_empty = int(timeout / 5)

        log.info(f"🚀 Starting consumption (batch_size={self.batch_size}, timeout={timeout}s)")

        try:
            while True:
                msg = self.consumer.poll(timeout=5.0)

                if msg is None:
                    empty_polls += 1
                    if empty_polls >= max_empty:
                        log.info("⏱️  Timeout reached, flushing remaining buffers")
                        break
                    continue

                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    log.error(f"Consumer error: {msg.error()}")
                    continue

                empty_polls = 0
                topic = msg.topic()

                try:
                    row = json.loads(msg.value().decode("utf-8"))
                    row = self.writer._enrich_row(row, topic, msg.partition(), msg.offset())
                    buffers[topic].append(row)
                except Exception as e:
                    log.warning(f"⚠️  Parse error on {topic}[{msg.partition()}]@{msg.offset()}: {e}")
                    with contextlib.suppress(Exception):
                        self.writer.write_dlq(
                            topic, msg.value(), str(e), msg.partition(), msg.offset()
                        )
                    continue

                # Flush buffer when batch_size reached
                if len(buffers[topic]) >= self.batch_size:
                    self.writer.write_batch(topic, buffers[topic])
                    self.consumer.commit()
                    total += len(buffers[topic])
                    buffers[topic] = []

                if max_messages and total >= max_messages:
                    break

            # Flush remaining
            for topic, buf in buffers.items():
                if buf:
                    self.writer.write_batch(topic, buf)
                    total += len(buf)
            self.consumer.commit()

        except KeyboardInterrupt:
            log.info("\n⛔ Interrupted, flushing...")
            for topic, buf in buffers.items():
                if buf:
                    self.writer.write_batch(topic, buf)
            self.consumer.commit()

        finally:
            self.consumer.close()

        log.info(f"\n{'=' * 50}")
        log.info("🔋 Bronze ingestion complete")
        log.info(f"   Written: {self.writer._written} | Errors: {self.writer._errors}")
        log.info(f"   Batch ID: {self.writer.batch_id}")
        log.info(f"{'=' * 50}")


def main():
    parser = argparse.ArgumentParser(description="Consume Kafka → Databricks Bronze")
    parser.add_argument(
        "--mode", choices=["databricks-sql", "spark", "local-delta"], default="local-delta"
    )
    parser.add_argument(
        "--bootstrap", default=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    )
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--max-messages", type=int, default=0, help="0 = consume until timeout")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--topic", nargs="*", help="Specific topics to consume")
    args = parser.parse_args()

    if args.mode == "databricks-sql":
        writer = DatabricksSQLWriter()
    elif args.mode == "spark":
        writer = SparkWriter()
    else:
        writer = LocalDeltaWriter()

    topics = [f"energy.bronze.{t}" for t in args.topic] if args.topic else None
    consumer = BronzeConsumer(writer, args.bootstrap, topics, args.batch_size)
    consumer.run(max_messages=args.max_messages, timeout=args.timeout)


if __name__ == "__main__":
    main()
