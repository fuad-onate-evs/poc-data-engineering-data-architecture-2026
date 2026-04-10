"""
Kafka Producer — Reads seed CSVs and publishes to Bronze topics.
Simulates real-time ingestion from SCADA/weather/grid sources.

Usage:
    python -m ingestion.producers.seed_producer --dataset chile
    python -m ingestion.producers.seed_producer --dataset ff --delay 0.01
    python -m ingestion.producers.seed_producer --dataset chile --topic scada
"""

import argparse
import csv
import json
import logging
import os
import time
from pathlib import Path

from confluent_kafka import Producer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# Topic mapping: seed filename → Kafka topic
SEED_TOPIC_MAP = {
    "seed_scada": "energy.bronze.scada",
    "seed_weather": "energy.bronze.weather",
    "seed_demand": "energy.bronze.demand",
    "seed_dispatch": "energy.bronze.dispatch",
    "seed_plants": "energy.bronze.plants",
}


class EnergyProducer:
    """Publishes energy seed data to Kafka topics."""

    def __init__(self, bootstrap_servers: str, dataset: str = "chile"):
        self.dataset = dataset
        self.seeds_dir = (
            Path(__file__).parent.parent.parent
            / "transform"
            / ("seeds" if dataset == "chile" else "seeds_ff")
        )
        self.producer = Producer(
            {
                "bootstrap.servers": bootstrap_servers,
                "acks": "all",
                "retries": 3,
                "linger.ms": 50,
                "batch.size": 32768,
                "compression.type": "snappy",
            }
        )
        self._delivered = 0
        self._failed = 0

    def _delivery_callback(self, err, msg):
        if err:
            self._failed += 1
            log.error(f"❌ Delivery failed [{msg.topic()}]: {err}")
        else:
            self._delivered += 1

    def _read_csv(self, filename: str) -> list[dict]:
        path = self.seeds_dir / f"{filename}.csv"
        if not path.exists():
            log.warning(f"⚠️  {path} not found, skipping")
            return []
        with open(path) as f:
            return list(csv.DictReader(f))

    def publish_topic(self, seed_name: str, topic: str, delay: float = 0.0):
        """Read a seed CSV and publish each row to a Kafka topic."""
        rows = self._read_csv(seed_name)
        if not rows:
            return 0

        log.info(f"📤 Publishing {len(rows)} rows → {topic} (dataset={self.dataset})")

        for i, row in enumerate(rows):
            # Add dataset tag to every message
            row["_dataset"] = self.dataset

            # Use node_id + timestamp as key for partitioning
            key = f"{row.get('node_id', row.get('plant_id', ''))}"
            if "timestamp" in row:
                key += f":{row['timestamp']}"

            value = json.dumps(row, default=str).encode("utf-8")

            self.producer.produce(
                topic=topic,
                key=key.encode("utf-8"),
                value=value,
                callback=self._delivery_callback,
            )

            # Periodic flush to avoid buffer overflow
            if (i + 1) % 1000 == 0:
                self.producer.flush()
                log.info(f"  ... {i + 1}/{len(rows)} sent")

            if delay > 0:
                time.sleep(delay)

        self.producer.flush()
        log.info(f"  ✅ {seed_name} → {topic}: {self._delivered} delivered, {self._failed} failed")
        return len(rows)

    def publish_all(self, delay: float = 0.0, topics: list[str] | None = None):
        """Publish all seed files to their respective topics."""
        total = 0
        for seed_name, topic in SEED_TOPIC_MAP.items():
            if topics and seed_name.replace("seed_", "") not in topics:
                continue
            total += self.publish_topic(seed_name, topic, delay)

        log.info(f"\n🔋 Done: {total} total messages published ({self.dataset})")
        log.info(f"   Delivered: {self._delivered} | Failed: {self._failed}")
        return total


def create_topics(bootstrap_servers: str):
    """Create Kafka topics if they don't exist."""
    from confluent_kafka.admin import AdminClient, NewTopic

    admin = AdminClient({"bootstrap.servers": bootstrap_servers})
    existing = admin.list_topics(timeout=10).topics.keys()

    new_topics = []
    for topic in SEED_TOPIC_MAP.values():
        if topic not in existing:
            new_topics.append(NewTopic(topic, num_partitions=6, replication_factor=1))

    # DLQ topic
    dlq = "energy.bronze.dlq"
    if dlq not in existing:
        new_topics.append(NewTopic(dlq, num_partitions=3, replication_factor=1))

    if new_topics:
        futures = admin.create_topics(new_topics)
        for topic, future in futures.items():
            try:
                future.result()
                log.info(f"  ✅ Created topic: {topic}")
            except Exception as e:
                log.warning(f"  ⚠️  Topic {topic}: {e}")
    else:
        log.info("  All topics already exist")


def main():
    parser = argparse.ArgumentParser(description="Publish energy seed data to Kafka")
    parser.add_argument("--dataset", choices=["chile", "ff"], default="chile")
    parser.add_argument(
        "--bootstrap", default=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    )
    parser.add_argument("--delay", type=float, default=0.0, help="Delay between messages (seconds)")
    parser.add_argument(
        "--topic", nargs="*", help="Specific topics: scada weather demand dispatch plants"
    )
    parser.add_argument("--create-topics", action="store_true", help="Create Kafka topics first")
    args = parser.parse_args()

    if args.create_topics:
        log.info("📋 Creating Kafka topics...")
        create_topics(args.bootstrap)

    producer = EnergyProducer(args.bootstrap, args.dataset)
    producer.publish_all(delay=args.delay, topics=args.topic)


if __name__ == "__main__":
    main()
