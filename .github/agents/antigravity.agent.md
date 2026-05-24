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

## Recent Modifications & Current State (May 23, 2026)

- **Log Permissions Issue Fixed**: Fixed a crash loop mapping issue where `airflow-scheduler` couldn't create logs in the mounted `/opt/airflow/logs` volume by setting `AIRFLOW_UID=1000` in the `.env` file and restarting the services.
- **Lineage Integration**: OpenLineage integration in the Airflow container points successfully to `http://marquez:5000` and `marquez-web` explicitly has `WEB_PORT=3000` set to prevent UI container side-crashing.
- **Unified DAG Consolidation**: Single end-to-end DAG `bank_dataops_pipeline` in `dags/bank_dataops_pipeline.py`. The 7-task linear chain: `generate_faker_data → validate_with_gx → extract_postgres_to_bq → run_dbt_staging → run_dbt_silver → run_dbt_test → run_ml_prediction`. If any task fails, downstream tasks receive UPSTREAM_FAILED.
- **BigQuery Bronze Load Verified**: Populated `bronze.transactions`, `bronze.accounts`, `bronze.devices`, and `bronze.merchants` successfully.
- **dbt Staging Models**: `analytics.stg_accounts`, `analytics.stg_devices`, `analytics.stg_merchants`, `analytics.stg_transactions` (views over bronze).
- **dbt Integrity Tests (Defense in Depth)**: Added `schema.yml` with `unique` + `not_null` tests on `stg_transactions.transaction_id`. Validates that `pg_to_bq.py` didn't corrupt/duplicate data during Postgres → BigQuery transport. Complements GX validation in Postgres.
- **dbt Silver Model**: Created `analytics.silver_enriched_transactions` (materialized table) that JOINs transactions with accounts and computes behavioral velocity features in BigQuery SQL (`account_tx_count_24h`, `account_avg_amount_7d`, `merchant_tx_count_1h`, `amount_vs_avg_ratio`, `tx_hour`, `tx_day_of_week`). Text columns (location, channel, occupation) stay raw — encoding deferred to predict.py.
- **predict.py Refactored**: Now reads from BigQuery Silver table instead of static CSVs. Applies one-hot encoding at inference time, aligns columns to the training feature order (loaded from `training_columns.json` MLflow artifact), scales with MinMaxScaler, and scores with the Isolation Forest + Autoencoder ensemble.
- **train.py Updated**: Now persists `training_columns.json` (feature order) and `training_scaler.joblib` as MLflow artifacts for predict.py to consume.
- **Dependency Fix Applied**: Updated `requirements.txt` to `pandas==2.1.4` and `apache-airflow-providers-google==10.22.0`. Updated `mlops/requirements-mlops.txt` with `google-cloud-bigquery`, `pandas-gbq`, `joblib`.
- **dbt Local Execution Fixed**: Installed `dbt-bigquery==1.11.1` in the local `.venv`. Added a `dev` target in `dbt/profiles.yml` pointing to the repo-root `gcp-key.json` for local runs, keeping `prod` target for Docker.

## Agent Guidelines

- **Continuous Update Task**: For each fundamental codebase change, architecture change, or debugging milestone you complete, **you MUST prompt the user or edit this file directly** to update the "Recent Modifications & Current State" section.
- **Docker Centric**: Keep in mind that mostly all operations (Airflow CLI commands, Postgres queries) need to be executed inside their respective Docker Compose containers via `docker compose exec`.
- Do not make assumptions when creating new Airflow DAGs; always refer to the existing `bank_dataops_pipeline.py` format + OpenLineage injectors.
