# Agile Work Plan — POC Data Engineering Platform
# Plan de Trabajo Agile — POC Plataforma de Ingeniería de Datos

> **Business context / Contexto de negocio:** Renewable energy electricity provision / Provisión de electricidad desde energías renovables
> **Stack:** Airflow · Databricks Photon · GitHub Actions · Delta Lake
> **Duration / Duración:** 10 weeks / 10 semanas (5 Sprints × 2 weeks)
> **Team / Equipo:** 3 Data Engineers (DE1, DE2, DE3) + 1 Project Manager (PM)
> **Velocity / Velocidad:** ~30 SP/sprint | **Total:** 148 SP

---

## Business Domain / Dominio de Negocio

### Data sources / Fuentes de datos

| Source / Fuente | Type / Tipo | Frequency / Frecuencia | Description / Descripción |
|-----------------|-------------|:----------------------:|--------------------------|
| SCADA / IoT sensors | Streaming/Batch | Real-time / 5-min intervals | Turbine, solar panel, inverter telemetry / Telemetría de turbinas, paneles, inversores |
| Weather APIs | API REST | Hourly / Cada hora | Solar irradiance, wind speed, temperature / Irradiancia, velocidad de viento, temperatura |
| Grid operator (ISO/TSO) | SFTP/API | 15-min intervals | Dispatch signals, curtailment, grid frequency / Señales de despacho, curtailment, frecuencia |
| Energy trading | DB/API | Near real-time | Spot prices, PPA contracts, settlements / Precios spot, contratos PPA, liquidaciones |
| Asset registry | ERP/DB | Daily | Plant metadata, maintenance logs, warranties / Metadata de plantas, logs de mantención |
| Metering (AMI) | SFTP/DB | Hourly | Customer consumption, net metering / Consumo de clientes, net metering |

### Medallion layers / Capas Medallion

```
┌─────────────────────────────────────────────────────────────────┐
│  Gold — Business KPIs / KPIs de Negocio                        │
│  ┌──────────┐ ┌───────────┐ ┌───────────┐ ┌────────────────┐   │
│  │Generation│ │  Revenue  │ │Grid Perf. │ │  Carbon &      │   │
│  │Forecast  │ │& Billing  │ │& Dispatch │ │  Compliance    │   │
│  └──────────┘ └───────────┘ └───────────┘ └────────────────┘   │
├─────────────────────────────────────────────────────────────────┤
│  Silver — Clean & Enriched / Limpio y Enriquecido              │
│  Aligned timestamps, weather-generation joins, asset health    │
│  scores, normalized pricing, validated meter reads             │
├─────────────────────────────────────────────────────────────────┤
│  Bronze — Raw Ingestion / Ingesta Cruda                        │
│  SCADA dumps, weather API JSONs, ISO CSVs, trading feeds,      │
│  ERP extracts, AMI meter files                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Key metrics / Métricas clave

| KPI | Description / Descripción | Gold Table |
|-----|--------------------------|------------|
| Capacity factor | Actual vs theoretical output / Producción real vs teórica | `fact_generation` |
| LCOE | Levelized cost of energy / Costo nivelado de energía | `fact_financial` |
| Curtailment rate | Energy wasted due to grid limits / Energía no despachada | `fact_dispatch` |
| Revenue per MWh | Blended price across PPAs + spot / Precio combinado | `fact_revenue` |
| Carbon offset | tCO₂e avoided vs baseline / Toneladas CO₂e evitadas | `fact_carbon` |
| Plant availability | Uptime % per asset / % disponibilidad por activo | `fact_asset_health` |

---

## Team Roles / Roles del Equipo

| Role | Focus / Foco |
|------|-------------|
| DE1 (Lead) | Architecture, CI/CD, data modeling / Arquitectura, CI/CD, modelado |
| DE2 | Ingestion, Bronze/Silver pipelines / Ingesta, pipelines Bronze/Silver |
| DE3 | Transformation, Gold layer, testing / Transformación, capa Gold, testing |
| PM | Planning, stakeholders, UAT / Planificación, stakeholders, UAT |

---

## Epic Summary / Resumen de Épicas

| # | Epic | Sprint | SP |
|---|------|:------:|:--:|
| E1 | Discovery & Architecture / Descubrimiento y Arquitectura | 1 | 24 |
| E2 | Ingestion & Bronze / Ingesta y Bronze | 2 | 28 |
| E3 | Transformation Silver & Gold / Transformación Silver y Gold | 2–4 | 38 |
| E4 | Orchestration & CI/CD / Orquestación y CI/CD | 4 | 24 |
| E5 | Testing & Quality / Testing y Calidad | 5 | 18 |
| E6 | UAT & Delivery / UAT y Entrega | 5 | 16 |
| | | **Total** | **148** |

---

## Sprint 1 — Discovery & Architecture (W1–W2)

### US-1.1: Source inventory & env setup / Inventario de fuentes y setup de entorno

| Task | SP | Owner | Acceptance / Aceptación |
|------|----|:-----:|------------------------|
| Map SCADA, weather, grid, trading, metering sources / Relevar fuentes SCADA, clima, grid, trading, medición | 3 | DE1 | Source catalog with schemas, volumes, SLAs / Catálogo con schemas, volúmenes, SLAs |
| Provision Databricks workspace (dev/staging) + S3 buckets for energy data | 3 | DE2 | Workspace accessible, clusters configured / Accesible, clusters configurados |
| Setup GitHub repos + branch strategy (`main`, `develop`, `feature/*`) | 2 | DE1 | Repos with protection rules / Repos con reglas de protección |
| Setup Airflow environment (Docker/K8s) | 3 | DE3 | UI running, health check DAG green / UI corriendo, DAG de salud verde |
| Define RACI + stakeholder map (grid ops, trading, compliance) / Matriz RACI + mapa de stakeholders | 2 | PM | RACI approved / RACI aprobado |

### US-1.2: Medallion architecture for energy domain / Arquitectura Medallion para dominio energético

| Task | SP | Owner | Acceptance / Aceptación |
|------|----|:-----:|------------------------|
| Design Bronze schema: SCADA telemetry, weather JSON, ISO CSVs, meter reads | 3 | DE1 | DDL + diagram / DDL + diagrama |
| Design Silver schema: aligned timeseries, asset-weather joins, normalized prices | 3 | DE1 | DDL + diagram |
| Design Gold schema: fact_generation, fact_revenue, fact_dispatch, fact_carbon, dims | 2 | DE1 | DDL + diagram |
| Document naming conventions (energy domain taxonomy) / Convenciones de nomenclatura | 3 | DE1+PM | Standards doc approved / Documento aprobado |

**Sprint 1: 24 SP** → DE1: 16 · DE2: 3 · DE3: 3 · PM: 2

---

## Sprint 2 — Ingestion & Bronze + Silver Start (W3–W4)

### US-2.1: Energy data ingestion pipeline / Pipeline de ingesta de datos energéticos

| Task | SP | Owner | Acceptance / Aceptación |
|------|----|:-----:|------------------------|
| Build SCADA + IoT extraction (PySpark, 5-min intervals) / Extracción SCADA + IoT | 5 | DE2 | Parameterized per plant/asset / Parametrizable por planta/activo |
| Load to Delta Bronze: telemetry, weather, grid signals + metadata (`_loaded_at`, `_source`, `_plant_id`) | 5 | DE2 | Delta with time-based partitioning / Delta con partición temporal |
| Implement idempotency for meter reads + SCADA (MERGE on timestamp+asset_id) | 3 | DE2 | Re-run won't duplicate / Re-ejecución no duplica |

### US-2.2: Storage & governance setup for energy data

| Task | SP | Owner | Acceptance / Aceptación |
|------|----|:-----:|------------------------|
| Configure Unity Catalog: `energy_catalog` → `bronze` / `silver` / `gold` schemas | 3 | DE1 | Catalog with B/S/G schemas |
| Configure S3 mounts: `s3://energy-raw/`, `s3://energy-curated/` | 2 | DE1 | Mounts functional from notebooks |
| Define retention policies (SCADA: 7y, weather: 3y, trading: 10y) + VACUUM | 2 | DE1 | Policies documented / Documentadas |

### US-3.1 (start): Silver — timeseries alignment & cleansing

| Task | SP | Owner | Acceptance / Aceptación |
|------|----|:-----:|------------------------|
| Align SCADA timestamps (UTC normalize, gap fill, outlier detection) | 5 | DE3 | Clean timeseries, no gaps > threshold / Sin gaps > umbral |
| Join weather data to generation assets (plant_id + geo + timestamp) | 3 | DE3 | Weather-generation pairs validated / Pares clima-generación validados |

**Sprint 2: 28 SP** → DE1: 7 · DE2: 13 · DE3: 8

---

## Sprint 3 — Silver Completion + Gold (W5–W6)

### US-3.1 (cont): Silver completion — energy transformations

| Task | SP | Owner | Acceptance / Aceptación |
|------|----|:-----:|------------------------|
| Implement SCD Type 2 for asset registry (plant upgrades, inverter swaps) | 5 | DE2 | Change history preserved / Historial preservado |
| Unit tests for energy transformations (capacity calc, curtailment logic) | 3 | DE3 | ≥ 80% coverage on core logic |

### US-3.2: Gold layer — energy KPIs & dimensional model

| Task | SP | Owner | Acceptance / Aceptación |
|------|----|:-----:|------------------------|
| Build `fact_generation` (MWh, capacity factor, availability by plant/hour) | 5 | DE3 | Queryable, matches SCADA source / Consultable, coincide con SCADA |
| Build `fact_revenue` (PPA settlements, spot revenue, blended $/MWh) | 3 | DE2 | Financial reconciliation passes / Cuadratura financiera OK |
| Build `dim_plant`, `dim_asset`, `dim_weather_station`, `dim_time` | 3 | DE3 | Dims populated, surrogate keys / Pobladas, surrogate keys |
| Optimize with Z-ORDER on `plant_id` + `event_date` | 3 | DE1 | Query improvement documented / Mejora documentada |

### US-3.3: Lineage & energy data documentation

| Task | SP | Owner | Acceptance / Aceptación |
|------|----|:-----:|------------------------|
| Document lineage: SCADA → Bronze → Silver → Gold (generation + revenue) | 3 | DE1 | Lineage diagram / Diagrama de lineage |
| Add column descriptions: energy units (MWh, MW, $/MWh, tCO₂e) in Unity Catalog | 2 | DE1 | All Gold columns described / Todas columnas Gold descritas |

**Sprint 3: 27 SP** → DE1: 8 · DE2: 8 · DE3: 11

---

## Sprint 4 — Orchestration & CI/CD (W7–W8)

### E3 (close): Energy data dictionary

| Task | SP | Owner | Acceptance / Aceptación |
|------|----|:-----:|------------------------|
| Create data dictionary (energy terms, units, calculation methods) / Diccionario de datos energéticos | 3 | DE1 | Accessible to team / Accesible al equipo |

### US-4.1: Airflow orchestration — energy pipelines

| Task | SP | Owner | Acceptance / Aceptación |
|------|----|:-----:|------------------------|
| Build ingestion DAG: SCADA + weather + grid → Bronze (hourly) | 3 | DE2 | DAG with retries, sensor checks / DAG con retries, sensor checks |
| Build transformation DAG: Silver → Gold (daily rollup + hourly near-RT) | 3 | DE2 | Task dependencies correct / Dependencias correctas |
| Configure failure alerts (email/Slack for missed SCADA windows) | 2 | DE3 | Notifications on error / Notificaciones en error |
| Define schedules: SCADA 5-min, weather hourly, trading EOD, billing monthly | 1 | DE2 | Schedules + SLA alerts active / Activos |

### US-4.2: CI/CD with GitHub Actions + Databricks Asset Bundles

| Task | SP | Owner | Acceptance / Aceptación |
|------|----|:-----:|------------------------|
| CI workflow: lint + unit tests + energy calc validation on PR | 3 | DE1 | Auto-triggered on PR |
| Configure Databricks Asset Bundles (DAB) for energy pipelines | 5 | DE1 | Deployable via `databricks bundle deploy` |
| CD to staging (merge → develop) | 2 | DE1 | Auto-deploy on merge |
| CD to production (merge → main) with approval gate | 2 | DE1 | Requires approval / Requiere aprobación |

**Sprint 4: 24 SP** → DE1: 15 · DE2: 7 · DE3: 2

---

## Sprint 5 — Testing + UAT + Delivery (W9–W10)

### US-5.1: Test pyramid — energy data validation

| Task | SP | Owner | Acceptance / Aceptación |
|------|----|:-----:|------------------------|
| Integration tests — E2E: SCADA → Bronze → Silver → Gold generation + revenue | 5 | DE3 | Full pipeline error-free / Pipeline completo sin errores |
| Data quality suites: capacity factor ∈ [0,1], MWh ≥ 0, no future timestamps, meter balance | 5 | DE2 | Suites passing, data docs generated / Suites pasan |
| Performance benchmarks — Gold queries (generation by plant, revenue by PPA) | 3 | DE3 | Queries < 5s documented |

### US-5.2: Energy pipeline monitoring

| Task | SP | Owner | Acceptance / Aceptación |
|------|----|:-----:|------------------------|
| Pipeline health dashboard: SCADA freshness, ingestion lag, DAG success rate | 3 | DE2 | Dashboard visible in Airflow / Dashboard visible |
| Data freshness alerts: SCADA stale > 15min, weather stale > 2h | 2 | DE3 | Alert triggers on SLA breach / Alerta al exceder SLA |

### US-6.1: UAT — energy stakeholders

| Task | SP | Owner | Acceptance / Aceptación |
|------|----|:-----:|------------------------|
| Prepare UAT env with real plant data (anonymized if needed) | 2 | DE1 | Isolated env with Gold data / Ambiente aislado |
| Execute UAT with grid ops, trading desk, compliance team | 3 | PM | Stakeholder sign-off per domain / Sign-off por dominio |
| Fix P1 defects (generation calc errors, billing mismatches) | 2 | DE2+DE3 | All P1 resolved / Todos P1 resueltos |

### US-6.2: BI & final delivery — energy dashboards

| Task | SP | Owner | Acceptance / Aceptación |
|------|----|:-----:|------------------------|
| Connect Power BI/Tableau → Databricks SQL (energy catalog) | 2 | DE1 | Connection functional / Conexión funcional |
| Build POC dashboard: generation heatmap, revenue by PPA, carbon offset tracker | 3 | DE3 | Dashboard with ≥ 3 energy KPIs / Dashboard con ≥ 3 KPIs energéticos |
| Cost analysis: actual vs $400–$1,000 estimate / Costos: real vs estimado | 2 | PM | Breakdown by service / Desglose por servicio |
| Final POC report + ADRs (architecture decisions for energy domain) | 2 | PM+DE1 | Presentation delivered / Presentación entregada |

**Sprint 5: 34 SP** → DE1: 4 · DE2: 10 · DE3: 11 · PM: 9

---

## Workload Distribution / Distribución de Carga (SP)

| Sprint | DE1 | DE2 | DE3 | PM | Total |
|:------:|:---:|:---:|:---:|:--:|:-----:|
| 1 | 16 | 3 | 3 | 2 | **24** |
| 2 | 7 | 13 | 8 | 0 | **28** |
| 3 | 8 | 8 | 11 | 0 | **27** |
| 4 | 15 | 7 | 2 | 0 | **24** |
| 5 | 4 | 10 | 11 | 9 | **34** |
| **Total** | **50** | **41** | **35** | **11** | **137** |

---

## DoD / Definition of Done

- [ ] PR reviewed + approved (min 1 reviewer) / PR revisado + aprobado
- [ ] CI green (lint + tests + energy calc validation)
- [ ] Docs updated / Documentación actualizada
- [ ] Deployed to staging / Desplegado a staging
- [ ] Data quality checks pass (energy-specific: units, ranges, balances)

## Risks / Riesgos

| Risk / Riesgo | P | I | Mitigation / Mitigación |
|---------------|:-:|:-:|------------------------|
| Databricks cost overrun / Sobrecosto | M | H | Daily CU monitoring, auto-termination, spot instances |
| SCADA data gaps (sensor failures) / Gaps en SCADA | H | H | Gap-fill interpolation in Silver, alerting in Bronze |
| Weather API rate limits / Límites de API de clima | M | M | Cache responses, fallback to historical averages |
| Regulatory schema changes (grid codes) / Cambios regulatorios | L | H | Schema evolution in Iceberg/Delta, version control |
| GitHub Actions minutes exhausted | M | M | Cache deps, optimize workflows |
| Airflow learning curve / Curva de aprendizaje | H | M | DAG templates, pair programming |

## Success Metrics / Métricas de Éxito

| Metric / Métrica | Target |
|-------------------|--------|
| Pipeline success rate | ≥ 95% |
| SCADA ingestion latency / Latencia ingesta SCADA | < 5 min |
| Gold query latency (generation by plant) | < 5s |
| Capacity factor accuracy vs manual reports | ≥ 99% match |
| Test coverage | ≥ 80% |
| Monthly cost / Costo mensual | $400–$1,000 USD |
| Delivery / Entrega | ≤ 10 weeks |
