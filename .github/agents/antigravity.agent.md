## Project Context & Architecture

- **Objective:** Maintain, troubleshoot, and orchestrate a full local DataOps platform featuring Data Ingestion (Faker -> Postgres), Lineage Tracking, Orchestration, Data Quality Validation, and Data Visualization.
- **Stack & Configurations:**
  - **Apache Airflow 2.10.0** (Orchestrator, unpaused DAGs, customized `AIRFLOW_UID=1000` to fix log permissions)
  - **Marquez & OpenLineage** (Lineage tracking: UI on port 3001, API on 5000)
  - **Great Expectations** (Data Quality metrics & validation, integrates via OpenLineage to Marquez)
  - **dbt** (Data Build Tool — staging views + Silver enriched model in BigQuery `analytics` dataset)
  - **PostgreSQL 14** (Used as Data Warehouse and backend DB for tools)
  - **Superset** (BI Dashboard for observability mapping)
  - **MLflow** (Machine Learning Operations tracking via SQLite, port 5050)
  - **Docker Compose** (Entire data stack containerized and networked via `data_stack`)

## Recent Modifications & Current State (May 24, 2026)

- **Log Permissions Issue Fixed**: Fixed a crash loop mapping issue where `airflow-scheduler` couldn't create logs in the mounted `/opt/airflow/logs` volume by setting `AIRFLOW_UID=1000` in the `.env` file and restarting the services.
- **Lineage Integration**: OpenLineage integration in the Airflow container points successfully to `http://marquez:5000` and `marquez-web` explicitly has `WEB_PORT=3000` set to prevent UI container side-crashing.
- **Unified DAG Consolidation**: Single end-to-end DAG `bank_dataops_pipeline` in `dags/bank_dataops_pipeline.py`. The 7-task linear chain: `generate_faker_data → validate_with_gx → extract_postgres_to_bq → run_dbt_staging → run_dbt_silver → run_dbt_test → run_ml_prediction`. If any task fails, downstream tasks receive UPSTREAM_FAILED.
- **BigQuery Sandbox Workaround**: Refactored `pg_to_bq.py` to use bulk `WRITE_TRUNCATE` instead of `APPEND` + `DELETE` DML queries to bypass free Sandbox tier DML billing restrictions. This achieves perfect, zero-duplicate idempotency!
- **dbt Staging & Silver Routing**:
  - `staging` models are written to `analytics` dataset.
  - Silver enriched model is written to a dedicated `silver` dataset (`silver.silver_enriched_transactions`).
  - Added a custom `generate_schema_name.sql` macro to bypass target prefixing in BigQuery, allowing direct materialization in the `silver` dataset.
- **dbt Integrity Tests (Defense in Depth)**: Added `schema.yml` with `unique` + `not_null` tests on `stg_transactions.transaction_id`. Validates that `pg_to_bq.py` didn't corrupt/duplicate data during Postgres → BigQuery transport. Complements GX validation in Postgres.
- **Self-Contained Containerized ML Inferences**:
  - **Mounts & Directory mapping**: Mapped `./mlops`, `./csv_denormalisation`, and `${PWD}/mlruns` as volumes in `docker-compose.yml` for all Airflow scheduler/webserver containers.
  - **Docker ML Stack**: Added `scikit-learn==1.5.1`, `tensorflow-cpu>=2.15.0,<2.18.0`, `joblib>=1.3.0`, and `keras>=3.0.0` directly to `requirements.txt` to enable ML processing inside Docker.
  - **Dynamic Environment Detection**: Modified `predict.py` and `train.py` to dynamically switch the MLflow tracking URI (`http://mlflow:5050` in Docker vs. `http://localhost:5050` on host) and Google Credentials (`/secrets/gcp-key.json` inside container vs. local fallback).
  - **Keras Serialization Version Alignment**: Aligned Keras versions between training and inference by running `train.py` inside the container using the container's native `Keras 3.12.2` package. This resolves all serialization model deserialization errors (`quantization_config` Dense layer errors) while ensuring host Keras (`3.14.1`) remains backward-compatible to inspect the models locally.
  - **BigQuery Closed-Loop Storage**: Configured `predict.py` to upload the final scored transactions (`anomaly_score` and `is_anomaly`) directly back to BigQuery as `silver.silver_scored_transactions` using an idempotent `WRITE_TRUNCATE` load job, completing the missing link for final Superset BI reporting.
- **Great Expectations ML Output Validation**:
  - **Script**: Created a highly reliable validation script `mlops/validate_ml_output.py` that utilizes the modern Great Expectations `1.17.2` fluent API with ephemeral context (`gx.get_context(mode='ephemeral')`) to validate ML scoring outputs directly from BigQuery.
  - **Expectations**: Checks that `transaction_id` is unique and non-null (schema validation), that `anomaly_score` is strictly between `0` and `1` (boundary validation) and non-null (format validation), and that `is_anomaly` is strictly in `{0, 1}`.
  - **Task**: Added the task `validate_ml_output_with_gx` as the final quality gate at the end of the `bank_dataops_pipeline` Airflow DAG.
- **Dependency Fix Applied**: Updated `requirements.txt` to include Airflow ML dependencies. Updated `mlops/requirements-mlops.txt` with `google-cloud-bigquery`, `pandas-gbq`, `joblib`.
- **dbt Local Execution Fixed**: Installed `dbt-bigquery==1.11.1` in the local `.venv`. Added a `dev` target in `dbt/profiles.yml` pointing to the repo-root `gcp-key.json` for local runs, keeping `prod` target for Docker.


## Agent Guidelines

- **Continuous Update Task**: For each fundamental codebase change, architecture change, or debugging milestone you complete, **you MUST prompt the user or edit this file directly** to update the "Recent Modifications & Current State" section.
- **Docker Centric**: Keep in mind that mostly all operations (Airflow CLI commands, Postgres queries) need to be executed inside their respective Docker Compose containers via `docker compose exec`.
- Do not make assumptions when creating new Airflow DAGs; always refer to the existing `bank_dataops_pipeline.py` format + OpenLineage injectors.
