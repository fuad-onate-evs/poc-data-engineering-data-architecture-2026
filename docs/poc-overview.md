# POC: Data Engineering & Architecture Platform

> Canonical project brief. Original source: Evalueserve POC document, April 2026.

## Description

Create a Data Engineer process that facilitates the implementation of common use case scenarios of data processing and orchestration of workflows using **Airflow**, also implementing Continuous Integration and Continuous Delivery using **GitHub Actions**, **Databricks Asset Bundles**, and storage in **AWS Photon Databricks**.

## Advantages

- **Airflow** is an open-source solution that does not require any payment.
- **GitHub Actions** is easy to use, compatible with any shell command, and has multiple marketplace tools.
- **Databricks Photon** engine handles petabytes easily. Delta Lake provides "Time Travel" and ACID transactions to prevent data corruption.

## Disadvantages

- **Airflow** requires a medium-to-large learning curve.
- **Databricks** can become expensive quickly if clusters are left running. Requires Unity Catalog for the best governance experience.
- Using **GitHub** free-tier CI/CD minutes are limited and can be consumed quickly by heavy testing.

## Cost

The financial model is consumption-based — pay-as-you-go scalability with low entry barriers. The integration between **GitHub**, **Airflow**, and **Databricks** avoids heavy upfront CapEx in favor of operational flexibility (OpEx). Primary cost drivers are compute hours and data throughput; expenses align directly with the value generated during transformation and storage.

| Item | Monthly cost |
|---|---|
| Data Migration | $100 – $200 |
| Data Storage | $5 – $15 (per 100 GB Delta Lake) |
| ETL Implementation | $100 – $400 (small multi-node cluster) |
| Query Analytics | $100 – $200 (serverless SQL ad-hoc) |
| BI Processing | $100 (BI tools connect free; compute covered above) |
| **TOTAL** | **$400 – $1,000** |

## Compatibility with other tools

This stack is built on open standards (**SQL**, **Python**, **Delta Lake**), ensuring serverless and seamless integration across the data ecosystem. It supports high-volume ingestion via **Lakeflow Connect**, maintains storage compatibility with engines like **Postgres** and **Redshift**, and provides high-speed connectors for major BI platforms like **Power BI** and **Tableau**. It also integrates enterprise governance through **Databricks Unity Catalog** and the **Photon engine**.

## Schedule

### Phase 1 — Discovery (W1–W2)

- **W1** — Inventory & Requirements: identify source systems (files/DBs), define target schema in Databricks. Environment setup: provision Databricks workspaces, GitHub repos.
- **W2** — Architecture Design: map Medallion layers (Bronze, Silver, Gold), define data pipeline standardization.

### Phase 2 — Implementation (W3–W8)

- **W3** — Ingestion & Storage: configure Python scripts to extract data and load it into Databricks Delta tables (Bronze layer).
- **W4–W7** — Transformation & Modeling: develop Lakeflow jobs and pipelines models to clean and aggregate data into Silver and Gold layers using Databricks SQL/Spark.
- **W8** — Orchestration & CI/CD: define GitHub Actions infrastructure as code and CI/CD implementation.

### Phase 3 — Testing & Validation (W9–W10)

- **W9** — QA & Data Integrity: validate the test pyramid implementation with high coverage.
- **W10** — UAT & Final Report: conduct UAT with BI tools (Power BI / Tableau) and document POC results, performance, and final cost analysis.

## Conclusion

The proposed architecture, integrating **Airflow**, **Databricks**, and **GitHub**, demonstrates a high-performance, asset-centric data platform. By shifting from task-based orchestration to software-defined assets, the POC ensures superior data observability and lineage. The cost of effort is optimized through a pay-as-you-go model, with an estimated initial operational budget of **$400–$1,000 USD** and a **ten-week** implementation timeline. This stack offers exceptional compatibility, utilizing open standards like Delta Lake and SQL to ensure zero vendor lock-in and seamless integration with major BI tools. The availability of this solution is enterprise-grade, leveraging Databricks' multi-cloud scalability and GitHub's robust CI/CD pipelines to provide a reliable, automated, and production-ready environment for data-driven decision-making.

## Related

- Sprint plan: [poc-agile-plan-energy.md](poc-agile-plan-energy.md)
- Onboarding: [ONBOARDING.md](ONBOARDING.md)
- Architecture: [../CONTEXT.md](../CONTEXT.md)
- GitHub: <https://github.com/fuad-onate-evs/poc-data-engineering-data-architecture-2026>
