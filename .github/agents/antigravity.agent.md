## Project Context & Architecture

- **Objective:** Maintain, troubleshoot, and orchestrate a full local DataOps platform featuring Data Ingestion (Faker -> Postgres), Lineage Tracking, Orchestration, Data Quality Validation, and Data Visualization.
- **Stack & Configurations:**
  - **Apache Airflow 2.10.0** (Orchestrator, unpaused DAGs, customized `AIRFLOW_UID=1000` to fix log permissions)
  - **Marquez & OpenLineage** (Lineage tracking: UI on port 3001, API on 5000)
  - **Great Expectations** (Data Quality metrics & validation, integrates via OpenLineage to Marquez)
  - **PostgreSQL 14** (Used as Data Warehouse and backend DB for tools)
  - **Superset** (BI Dashboard for observability mapping)
  - **MLflow** (Machine Learning Operations tracking via SQLite)
  - **Docker Compose** (Entire data stack containerized and networked via `data_stack`)

## Recent Modifications & Current State (May 23, 2026)

- **Log Permissions Issue Fixed**: Fixed a crash loop mapping issue where `airflow-scheduler` couldn't create logs in the mounted `/opt/airflow/logs` volume by setting `AIRFLOW_UID=1000` in the `.env` file and restarting the services.
- **DAG Parsing Active**: The `data_ingestion_and_quality` DAG is now correctly compiled, active, unpaused, and visible in the Web UI.
- **Lineage Integration**: OpenLineage integration in the Airflow container points successfully to `http://marquez:5000` and `marquez-web` explicitly has `WEB_PORT=3000` set to prevent UI container side-crashing.

## Agent Guidelines

- **Continuous Update Task**: For each fundamental codebase change, architecture change, or debugging milestone you complete, **you MUST prompt the user or edit this file directly** to update the "Recent Modifications & Current State" section.
- **Docker Centric**: Keep in mind that mostly all operations (Airflow CLI commands, Postgres queries) need to be executed inside their respective Docker Compose containers via `docker compose exec`.
- Do not make assumptions when creating new Airflow DAGs; always refer to the existing `gx_validation_dag.py` format + OpenLineage injectors.
