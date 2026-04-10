-- ═══════════════════════════════════════════════════════════
-- Bronze Layer DDL — Databricks Unity Catalog
-- Landing zone: raw data as-is from Kafka topics
-- Convention: _meta columns for lineage + idempotency
-- ═══════════════════════════════════════════════════════════

-- Catalog + Schema
CREATE CATALOG IF NOT EXISTS energy_catalog;
USE CATALOG energy_catalog;
CREATE SCHEMA IF NOT EXISTS bronze COMMENT 'Raw landing zone from Kafka topics';
USE SCHEMA bronze;

-- ─── SCADA Telemetry ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS scada_telemetry (
    timestamp TIMESTAMP NOT NULL COMMENT 'UTC measurement timestamp',
    node_id STRING NOT NULL COMMENT 'Grid node identifier (CL01-CL12 or FF)',
    solar_mw DOUBLE COMMENT 'Solar generation in MW',
    wind_mw DOUBLE COMMENT 'Wind generation in MW',
    hydro_mw DOUBLE COMMENT 'Hydro generation in MW',
    geothermal_mw DOUBLE COMMENT 'Geothermal generation in MW',
    tidal_mw DOUBLE COMMENT 'Tidal generation in MW',
    total_generation_mw DOUBLE COMMENT 'Sum of all generation sources',
    -- Meta columns (populated by consumer)
    _loaded_at TIMESTAMP NOT NULL COMMENT 'UTC timestamp when row was written to Bronze',
    _source STRING NOT NULL COMMENT 'Origin: kafka topic name',
    _batch_id STRING NOT NULL COMMENT 'Kafka consumer batch UUID',
    _kafka_partition INT COMMENT 'Kafka partition number',
    _kafka_offset BIGINT COMMENT 'Kafka offset for idempotency',
    _dataset STRING NOT NULL COMMENT 'chile or ff'
)
USING DELTA
PARTITIONED BY (node_id, DATE (timestamp))
COMMENT 'Raw SCADA telemetry from renewable energy plants'
    TBLPROPERTIES (
        'delta.autoOptimize.optimizeWrite' = 'true',
        'delta.autoOptimize.autoCompact' = 'true',
        'quality' = 'bronze'
    );

-- ─── Weather ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS weather (
    timestamp TIMESTAMP NOT NULL,
    node_id STRING NOT NULL,
    climate STRING COMMENT 'Climate zone classification',
    solar_irradiance_wm2 DOUBLE COMMENT 'Solar irradiance W/m²',
    wind_speed_ms DOUBLE COMMENT 'Wind speed m/s',
    temperature_c DOUBLE COMMENT 'Temperature °C',
    humidity_pct DOUBLE COMMENT 'Relative humidity %',
    _loaded_at TIMESTAMP NOT NULL,
    _source STRING NOT NULL,
    _batch_id STRING NOT NULL,
    _kafka_partition INT,
    _kafka_offset BIGINT,
    _dataset STRING NOT NULL
)
USING DELTA
PARTITIONED BY (node_id, DATE (timestamp))
COMMENT 'Weather observations per grid node'
    TBLPROPERTIES (
        'delta.autoOptimize.optimizeWrite' = 'true',
        'delta.autoOptimize.autoCompact' = 'true',
        'quality' = 'bronze'
    );

-- ─── Demand ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS demand (
    timestamp TIMESTAMP NOT NULL,
    node_id STRING NOT NULL,
    demand_mw DOUBLE NOT NULL COMMENT 'Total demand in MW',
    residential_pct DOUBLE COMMENT '% residential sector',
    industrial_pct DOUBLE COMMENT '% industrial sector',
    commercial_pct DOUBLE COMMENT '% commercial sector',
    _loaded_at TIMESTAMP NOT NULL,
    _source STRING NOT NULL,
    _batch_id STRING NOT NULL,
    _kafka_partition INT,
    _kafka_offset BIGINT,
    _dataset STRING NOT NULL
)
USING DELTA
PARTITIONED BY (node_id, DATE (timestamp))
COMMENT 'Electricity demand per grid node by sector'
    TBLPROPERTIES (
        'delta.autoOptimize.optimizeWrite' = 'true',
        'delta.autoOptimize.autoCompact' = 'true',
        'quality' = 'bronze'
    );

-- ─── Grid Dispatch ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS grid_dispatch (
    timestamp TIMESTAMP NOT NULL,
    node_id STRING NOT NULL,
    total_generation_mw DOUBLE,
    total_demand_mw DOUBLE,
    balance_mw DOUBLE COMMENT 'Generation - Demand',
    curtailment_mw DOUBLE COMMENT 'Curtailed renewable energy',
    spot_price DOUBLE COMMENT 'Spot price (USD or Gil)/MWh',
    ppa_price DOUBLE COMMENT 'PPA contract price/MWh',
    revenue DOUBLE COMMENT 'Generation × PPA price',
    curtailment_cost DOUBLE COMMENT 'Curtailment × PPA price',
    carbon_offset_tco2e DOUBLE COMMENT 'Avoided CO₂ tonnes',
    _loaded_at TIMESTAMP NOT NULL,
    _source STRING NOT NULL,
    _batch_id STRING NOT NULL,
    _kafka_partition INT,
    _kafka_offset BIGINT,
    _dataset STRING NOT NULL
)
USING DELTA
PARTITIONED BY (node_id, DATE (timestamp))
COMMENT 'Grid dispatch: generation vs demand balance, pricing, carbon'
    TBLPROPERTIES (
        'delta.autoOptimize.optimizeWrite' = 'true',
        'delta.autoOptimize.autoCompact' = 'true',
        'quality' = 'bronze'
    );

-- ─── Plants (Slowly Changing Dimension in Bronze) ───────────
CREATE TABLE IF NOT EXISTS plants (
    plant_id STRING NOT NULL COMMENT 'Unique plant identifier',
    node_id STRING NOT NULL,
    node_name STRING,
    region STRING,
    source_type STRING NOT NULL COMMENT 'solar/wind/hydro/geothermal/tidal',
    capacity_mw DOUBLE NOT NULL,
    climate STRING,
    ppa_price_mwh DOUBLE,
    lat DOUBLE COMMENT 'Latitude (Chile only)',
    lon DOUBLE COMMENT 'Longitude (Chile only)',
    cen_barra STRING COMMENT 'CEN grid bus reference (Chile only)',
    _loaded_at TIMESTAMP NOT NULL,
    _source STRING NOT NULL,
    _batch_id STRING NOT NULL,
    _dataset STRING NOT NULL
)
USING DELTA
COMMENT 'Plant/asset registry — SCD source for Silver'
    TBLPROPERTIES (
        'delta.autoOptimize.optimizeWrite' = 'true',
        'quality' = 'bronze'
    );

-- ─── Dead Letter Queue ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS dead_letter_queue (
    received_at TIMESTAMP NOT NULL,
    topic STRING NOT NULL,
    partition_id INT,
    offset_id BIGINT,
    key STRING,
    value STRING COMMENT 'Raw message payload',
    error_message STRING COMMENT 'Parse/validation error',
    _batch_id STRING NOT NULL
)
USING DELTA
COMMENT 'Failed messages for reprocessing'
    TBLPROPERTIES ('quality' = 'bronze');
