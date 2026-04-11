"""
Central configuration for Kafka + Databricks Bronze ingestion.
Reads from .env or environment variables.
"""

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


@dataclass
class KafkaConfig:
    bootstrap_servers: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    schema_registry_url: str = os.getenv("SCHEMA_REGISTRY_URL", "http://localhost:8081")
    security_protocol: str = os.getenv("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT")
    sasl_mechanism: str = os.getenv("KAFKA_SASL_MECHANISM", "")
    sasl_username: str = os.getenv("KAFKA_SASL_USERNAME", "")
    sasl_password: str = os.getenv("KAFKA_SASL_PASSWORD", "")

    # Topics
    topic_scada: str = "energy.bronze.scada"
    topic_weather: str = "energy.bronze.weather"
    topic_demand: str = "energy.bronze.demand"
    topic_dispatch: str = "energy.bronze.dispatch"
    topic_plants: str = "energy.bronze.plants"
    topic_dlq: str = "energy.bronze.dlq"  # dead letter queue

    # Producer
    producer_acks: str = "all"
    producer_retries: int = 3
    producer_linger_ms: int = 50
    producer_batch_size: int = 32768

    # Consumer
    consumer_group: str = "energy-bronze-ingestion"
    consumer_auto_offset_reset: str = "earliest"
    consumer_max_poll_records: int = 500
    consumer_poll_timeout: float = 5.0

    @property
    def producer_config(self) -> dict:
        cfg = {
            "bootstrap.servers": self.bootstrap_servers,
            "acks": self.producer_acks,
            "retries": self.producer_retries,
            "linger.ms": self.producer_linger_ms,
            "batch.size": self.producer_batch_size,
        }
        if self.security_protocol != "PLAINTEXT":
            cfg["security.protocol"] = self.security_protocol
            cfg["sasl.mechanism"] = self.sasl_mechanism
            cfg["sasl.username"] = self.sasl_username
            cfg["sasl.password"] = self.sasl_password
        return cfg

    @property
    def consumer_config(self) -> dict:
        cfg = {
            "bootstrap.servers": self.bootstrap_servers,
            "group.id": self.consumer_group,
            "auto.offset.reset": self.consumer_auto_offset_reset,
            "max.poll.records": self.consumer_max_poll_records,
            "enable.auto.commit": False,
        }
        if self.security_protocol != "PLAINTEXT":
            cfg["security.protocol"] = self.security_protocol
            cfg["sasl.mechanism"] = self.sasl_mechanism
            cfg["sasl.username"] = self.sasl_username
            cfg["sasl.password"] = self.sasl_password
        return cfg

    @property
    def all_topics(self) -> list[str]:
        return [
            self.topic_scada,
            self.topic_weather,
            self.topic_demand,
            self.topic_dispatch,
            self.topic_plants,
        ]


@dataclass
class DatabricksConfig:
    host: str = os.getenv("DATABRICKS_HOST", "")
    token: str = os.getenv("DATABRICKS_TOKEN", "")
    http_path: str = os.getenv("DATABRICKS_HTTP_PATH", "")
    catalog: str = os.getenv("DATABRICKS_CATALOG", "energy_catalog")
    schema_bronze: str = os.getenv("DATABRICKS_SCHEMA_BRONZE", "bronze")
    schema_silver: str = os.getenv("DATABRICKS_SCHEMA_SILVER", "silver")
    schema_gold: str = os.getenv("DATABRICKS_SCHEMA_GOLD", "gold")

    # S3/ADLS paths
    landing_path: str = os.getenv("LANDING_PATH", "s3://energy-raw/landing")
    bronze_path: str = os.getenv("BRONZE_PATH", "s3://energy-raw/bronze")

    @property
    def jdbc_url(self) -> str:
        return f"databricks://token:{self.token}@{self.host}?http_path={self.http_path}&catalog={self.catalog}"

    @property
    def sql_connection(self) -> dict:
        return {
            "server_hostname": self.host,
            "http_path": self.http_path,
            "access_token": self.token,
        }


@dataclass
class TrelloConfig:
    """Trello REST API config — used by write.integrations.trello.

    Auth: API key + token. Get them at https://trello.com/app-key.
    Board and list IDs are board-specific; pull them once via the
    `trello list-boards` / `trello list-lists` CLI commands.
    """

    api_key: str = os.getenv("TRELLO_API_KEY", "")
    token: str = os.getenv("TRELLO_TOKEN", "")
    base_url: str = os.getenv("TRELLO_BASE_URL", "https://api.trello.com/1")
    board_id: str = os.getenv("TRELLO_BOARD_ID", "")

    # List IDs for sync targets — fill in after running `trello list-lists`
    list_id_backlog: str = os.getenv("TRELLO_LIST_ID_BACKLOG", "")
    list_id_in_progress: str = os.getenv("TRELLO_LIST_ID_IN_PROGRESS", "")
    list_id_review: str = os.getenv("TRELLO_LIST_ID_REVIEW", "")
    list_id_done: str = os.getenv("TRELLO_LIST_ID_DONE", "")
    list_id_incidents: str = os.getenv("TRELLO_LIST_ID_INCIDENTS", "")
    list_id_assets: str = os.getenv("TRELLO_LIST_ID_ASSETS", "")

    # Operational
    timeout_s: float = float(os.getenv("TRELLO_TIMEOUT_S", "10"))
    max_retries: int = int(os.getenv("TRELLO_MAX_RETRIES", "3"))

    @property
    def is_configured(self) -> bool:
        """True iff api_key + token are set — clients should bail early when False."""
        return bool(self.api_key and self.token)

    @property
    def auth_params(self) -> dict[str, str]:
        """Query params Trello expects on every request."""
        return {"key": self.api_key, "token": self.token}


@dataclass
class AppConfig:
    kafka: KafkaConfig = field(default_factory=KafkaConfig)
    databricks: DatabricksConfig = field(default_factory=DatabricksConfig)
    trello: TrelloConfig = field(default_factory=TrelloConfig)
    dataset: str = os.getenv("DATASET", "chile")  # "chile" or "ff"
    seeds_dir: str = os.getenv("SEEDS_DIR", "transform/seeds")
    batch_size: int = int(os.getenv("BATCH_SIZE", "500"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO")


config = AppConfig()
