# Data Quality Monitoring Framework

## 📌 Project Context

### The Problem

A company's Data & Analytics department (DSI) manages a data warehouse that feeds critical business decisions (reporting, customer dashboards, ML models). Without automated quality controls, data issues propagate silently:

- **Missing values** → incorrect KPIs
- **Duplicate records** → inflated metrics
- **Stale data** → outdated decisions
- **Format violations** → broken downstream applications

### The Solution

Build a **Data Observability framework** that continuously monitors data health, computes quality scores, traces data lineage, and provides real-time dashboards with alerts and basic self-healing capabilities.

---

## 🎯 Project Objectives

1. **Automated Testing** – Execute quality checks (nulls, uniqueness, patterns, freshness) using Great Expectations
2. **Quality Scoring** – Compute a daily health score (0–100%) per table/dataset
3. **Lineage Tracking** – Trace data origins and transformations using OpenLineage + Marquez
4. **Real-time Visualization** – Dashboard (Superset) with live metrics and alerts
5. **Advanced Features** – Anomaly detection on quality metrics + simple auto-remediation

---

## 🧱 Technology Stack

| Component           | Technology              | Purpose                                         |
| ------------------- | ----------------------- | ----------------------------------------------- |
| Orchestration       | Apache Airflow          | Schedule & coordinate data pipelines            |
| Data Transformation | dbt (Data Build Tool)   | Transform raw data into analytics-ready models  |
| Data Quality        | Great Expectations (GX) | Define & execute data quality expectations      |
| Lineage             | OpenLineage + Marquez   | Capture & visualize data lineage                |
| Visualization       | Apache Superset         | Dashboard + real-time alerts                    |
| Metadata Storage    | PostgreSQL              | Store quality scores & lineage metadata         |
| Anomaly Detection   | Python (scipy/pandas)   | Statistical detection of quality drops          |
| Auto-remediation    | Airflow branching       | Simple corrective actions (reject batch, retry) |

---

## 🏗️ Architecture Overview

┌─────────────────────────────────────────────────────────────────┐
│ DATA SOURCES                                                    │
│ (Faker → PostgreSQL core_banking schema)                        │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│ AIRFLOW DAG: bank_dataops_pipeline (single end-to-end DAG)      │
│                                                                 │
│ ┌──────────────┐   ┌──────────────┐   ┌─────────────────────┐   │
│ │ 1. Faker     │──▶│ 2. GX Core   │──▶│ 3. Postgres → BQ    │   │
│ │ (generate)   │   │ (validate)   │   │ (bronze load)       │   │
│ └──────────────┘   └──────────────┘   └──────────┬──────────┘   │
│                                                  │              │
│                                                  ▼              │
│ ┌──────────────┐   ┌──────────────┐   ┌─────────────────────┐   │
│ │ 6. dbt test  │◀──│ 5. dbt Silver│◀──│ 4. dbt Staging      │   │
│ │ (integrity)  │   │ (behavioral) │   │ (views)             │   │
│ └──────┬───────┘   └──────────────┘   └─────────────────────┘   │
│        │                                                        │
│        │  If any upstream task fails: stops                     │
│        ▼  → UPSTREAM_FAILED status on subsequent tasks          │
│ ┌──────────────┐                                                │
│ │ 7. ML Predict│                                                │
│ │ (inference)  │                                                │
│ └──────────────┘                                                │
│        │                                                        │
│        ▼                                                        │
│  [OpenLineage events → Marquez Lineage UI]                      │
└─────────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│ DATA WAREHOUSE (BigQuery)                                       │
│ ┌────────────┐ ┌────────────┐ ┌──────────────┐                  │
│ │   bronze   │→│  analytics │→│ silver_enrich│                  │
│ │ (raw load) │ │ (stg_*)    │ │ (enriched)   │                  │
│ └────────────┘ └────────────┘ └──────────────┘                  │
└─────────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│ SUPERSET DASHBOARD & ML SCORING                                 │
│ - Quality score trends   - Lineage graph (from Marquez)         │
│ - anomaly_score output   - Slack/email alerts                   │
└─────────────────────────────────────────────────────────────────┘

---

## 📊 Quality Checks Definition

### 1. Null Checks

- **Expectation**: `expect_column_values_to_not_be_null`
- **Example**: Customer email should never be NULL
- **Threshold**: < 1% nulls for critical columns

### 2. Uniqueness Checks

- **Expectation**: `expect_column_values_to_be_unique`
- **Example**: Order ID must be unique
- **Threshold**: 100% uniqueness for primary keys

### 3. Pattern Checks (Regex)

- **Expectation**: `expect_column_values_to_match_regex`
- **Example**: Email format → `^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$`
- **Threshold**: > 99% compliance

### 4. Freshness Checks

- **Expectation**: `expect_column_max_to_be_between`
- **Example**: Last order date should be within last 24 hours
- **Threshold**: Max date >= CURRENT_DATE - 1 day

---

## 📈 Quality Score Formula

**Example weights**:

- Critical tables (Customer, Order): weight = 3
- Important tables (Product, Inventory): weight = 2
- Secondary tables (Logs, History): weight = 1

---

## 🔍 Anomaly Detection Strategy

### Method: Moving Average + Standard Deviation

````python
# 30-day rolling window
rolling_mean = score_history.rolling(30).mean()
rolling_std = score_history.rolling(30).std()

# Anomaly if score < mean - 2*std
if current_score < rolling_mean - 2 * rolling_std:
    trigger_alert()
    trigger_remediation()

---

## Quick Start (consolidated docs)

To start the whole platform (Airflow, Superset, Marquez, PostgreSQL) with one command:

```bash
docker compose up --build
````

Wait ~2–3 minutes for all services to become healthy. Key endpoints:

- Airflow Web UI: http://localhost:8080
- Superset UI: http://localhost:8088
- Marquez API: http://localhost:5000
- Marquez UI: http://localhost:3001

Minimal troubleshooting tips:

- Check service status: `docker compose ps`
- View logs: `docker compose logs -f <service>`
- Rebuild if dependencies change: `docker compose build --no-cache`

### Recent Platform Updates (May 2026)

- **Airflow Environment Upgrade**: Updated the Airflow base image to Python 3.10 to fix compatibility issues with Great Expectations 1.17.2 and MLflow.
- **Unified End-to-End Orchestration**: Consolidated raw data generation, PostgreSQL validation (GX Core), BigQuery ingestion, staging views, Silver transformation tables, integrity validation, and ML inference scoring into a single linear pipeline DAG (`dags/bank_dataops_pipeline.py`).
- **BigQuery Sandbox Workaround (Idempotency)**: Refactored `database/pg_to_bq.py` to use bulk `WRITE_TRUNCATE` uploads rather than `APPEND` + `DELETE` DML queries, completely bypassing the BigQuery Sandbox free tier DML billing restrictions. This provides perfect, zero-duplicate idempotency!
- **dbt Medallion Architecture & Custom Schema Routing**:
  - `staging` models are written to the default target `analytics` dataset.
  - Silver enriched model calculates behavioral velocities (window functions for transaction frequency, temporal seasonals) and routes to a dedicated **`silver`** dataset.
  - Implemented a custom `generate_schema_name.sql` macro to bypass target prefixing in BigQuery, ensuring clean isolation of layers.
- **dbt Integrity Tests (Defense in Depth)**: Configured dbt tests (`unique` + `not_null` constraints on `transaction_id`) inside `models/staging/schema.yml` to protect data warehouse load from duplicate rows or corruption.
- **Self-Contained Containerized ML Execution**:
  - **Volume Mounts**: Mapped `./mlops`, `./csv_denormalisation`, and the host-absolute `${PWD}/mlruns` as volumes in `docker-compose.yml` for all Airflow scheduler/webserver containers.
  - **Docker ML Stack**: Integrated `scikit-learn`, `tensorflow-cpu`, `joblib`, and `keras>=3.0.0` inside `requirements.txt` to run ML models natively inside Docker containers.
  - **Dynamic Environment Detection**: Modified `predict.py` and `train.py` to dynamically switch the MLflow tracking URI (`http://mlflow:5050` in Docker vs. `http://localhost:5050` on host) and BQ Credentials (`/secrets/gcp-key.json` inside container vs. local fallback).
  - **Keras Serialization Version Alignment**: Aligned Keras versions between training and inference by running `train.py` inside the container using the container's native `Keras 3.12.2` package. This resolves all serialization model deserialization errors (`quantization_config` Dense layer errors) while ensuring host Keras (`3.14.1`) remains backward-compatible to inspect the models locally.
  - **BigQuery Closed-Loop Storage**: Configured `predict.py` to upload the final scored transactions (`anomaly_score` and `is_anomaly`) directly back to BigQuery as `silver.silver_scored_transactions` using an idempotent `WRITE_TRUNCATE` load job, completing the missing link for final Superset BI reporting.
- **Great Expectations ML Output Validation**: Created a specialized script (`mlops/validate_ml_output.py`) using the modern GX 1.17.2 fluent API to validate our ML anomaly scores directly in BigQuery. The task `validate_ml_output_with_gx` acts as a quality gate right after the prediction phase, verifying:
  - **Schema integrity**: `transaction_id` remains present and unique.
  - **Boundary checks**: `anomaly_score` is strictly between `0` and `1`.
  - **Format checks**: `anomaly_score` does not contain NaN/nulls, and `is_anomaly` is strictly `0` or `1`.
- **dbt Gold Layer (Business & Quarantine)**:
  - Created two final BigQuery views in the `gold` dataset: `gold_fact_transactions` (clean business reporting) and `gold_quarantine_transactions` (alerts and security).
  - Used BigQuery `JOIN` operations inside dbt models to fetch original features from `silver_enriched_transactions` using the `transaction_id`, keeping the ML prediction python script highly optimized and lightweight.
- **OpenLineage & Marquez Integration**:
  - Configured `AIRFLOW__OPENLINEAGE__TRANSPORT` and `AIRFLOW__OPENLINEAGE__NAMESPACE` inside `docker-compose.yml`.
  - Declared `inlets` and `outlets` leveraging the OpenLineage provider (`openlineage.client.run.Dataset`) to map lineage across the full pipeline.
  - Added the `marquez-web` service to `docker-compose.yml` to expose the Marquez Lineage UI at port `3000`.

Notes: I consolidated the extra markdown files into this README to keep the repo tidy. If you need the detailed docs back, they are available in the Git history.

## BigQuery (dbt) setup

If you want dbt to run against BigQuery from inside the Airflow containers, add your GCP service account JSON to the repo root as `gcp-key.json` (keep it out of version control).

- The Compose setup mounts `./dbt` into `/opt/airflow/dbt` and the service account into `/secrets/gcp-key.json`.
- `requirements.txt` includes `dbt-core`, `dbt-postgres` and `dbt-bigquery` so the adapter will be installed when images are built.
- The `dbt` profile in `dbt/profiles.yml` is preconfigured to use `/secrets/gcp-key.json`.

Steps to run (after placing `gcp-key.json` in repo root):

```bash
docker compose up --build -d
# wait for services to become healthy (2-3 minutes)

# run a dbt debug inside the Airflow webserver container
docker compose exec airflow-webserver dbt debug --project-dir /opt/airflow/dbt --profiles-dir /opt/airflow/dbt
```

If you prefer not to mount a keyfile, set `GOOGLE_APPLICATION_CREDENTIALS` in your environment and update `dbt/profiles.yml` accordingly.

If you run into adapter errors (e.g. "Could not find adapter type bigquery"), rebuild the images to ensure `requirements.txt` changes are applied:

```bash
docker compose build --no-cache
docker compose up -d
```
