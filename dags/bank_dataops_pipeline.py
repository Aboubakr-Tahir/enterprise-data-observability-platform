"""
Unified Bank DataOps Pipeline
==============================

Single end-to-end DAG that chains every phase of the data platform:

  [generate_faker_data] → [validate_with_gx] → [extract_postgres_to_bq]
       → [run_dbt_staging] → [run_dbt_silver] → [run_dbt_test] → [run_ml_prediction]

Design rationale:
  • Data-Quality-First: If GX Core detects corrupt data in Postgres the pipeline
    stops immediately — downstream tasks receive UPSTREAM_FAILED status,
    guaranteeing that BigQuery never ingests invalid data.
  • Defense in Depth: dbt tests validate data integrity after transport to BigQuery
    (unique + not_null on transaction_id), complementing GX validation in Postgres.
  • Unified Marquez Lineage: All tasks share inlets/outlets within a single DAG,
    producing one continuous dependency graph in the Marquez UI.
  • Automated dbt + ML: dbt staging → Silver → tests → ML prediction, all
    orchestrated without manual intervention.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

import great_expectations as gx
from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from openlineage.client.run import Dataset

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
REPO_ROOT = "/opt/airflow"
GX_CONTEXT_DIR = f"{REPO_ROOT}/great_expectations"
GX_CHECKPOINT_NAME = "sample_checkpoint"
AIRFLOW_GX_DB_CONN = "postgresql+psycopg2://airflow:airflow@postgres/airflow"

# ---------------------------------------------------------------------------
# OpenLineage dataset declarations (used for Marquez lineage tracking)
# ---------------------------------------------------------------------------
postgres_transactions_ds = Dataset(
    namespace="postgres://postgres:5432",
    name="airflow.core_banking.transactions",
)

bigquery_bronze_ds = Dataset(
    namespace="bigquery",
    name="gen-lang-client-0635762262.bronze.transactions",
)

bigquery_analytics_ds = Dataset(
    namespace="bigquery",
    name="gen-lang-client-0635762262.analytics.stg_transactions",
)

bigquery_silver_ds = Dataset(
    namespace="bigquery",
    name="gen-lang-client-0635762262.analytics.silver_enriched_transactions",
)


# ---------------------------------------------------------------------------
# Python callable — Great Expectations checkpoint
# ---------------------------------------------------------------------------
def run_gx_checkpoint() -> None:
    """Run the persisted GX checkpoint against core_banking.transactions."""
    os.environ["GX_DB_CONN"] = AIRFLOW_GX_DB_CONN
    os.chdir(GX_CONTEXT_DIR)

    context = gx.get_context()
    checkpoint = context.checkpoints.get(GX_CHECKPOINT_NAME)
    result = checkpoint.run()

    print(f"Checkpoint success: {result.success}")
    for validation_key, validation_result in result.run_results.items():
        print(f"Validation key: {validation_key}")
        print(f"Suite: {validation_result.suite_name}")
        print(f"Success: {validation_result.success}")
        print(
            f"Evaluated expectations: {validation_result.statistics['evaluated_expectations']}"
        )
        print(
            f"Successful expectations: {validation_result.statistics['successful_expectations']}"
        )

    if not result.success:
        raise RuntimeError(
            "Great Expectations checkpoint failed — aborting pipeline to protect BigQuery."
        )


# ---------------------------------------------------------------------------
# DAG definition
# ---------------------------------------------------------------------------
default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="bank_dataops_pipeline",
    default_args=default_args,
    description=(
        "End-to-end DataOps pipeline: Faker → GX → BQ bronze → "
        "dbt staging → Silver → dbt test → ML prediction"
    ),
    schedule="@daily",
    start_date=datetime(2026, 5, 22),
    catchup=False,
    max_active_runs=1,
    tags=["dataops", "ingestion", "great-expectations", "bigquery", "dbt", "mlops"],
) as dag:

    # Task 1 — Generate synthetic banking transactions with Faker
    generate_faker_data = BashOperator(
        task_id="generate_faker_data",
        bash_command=(
            f"python3 {REPO_ROOT}/database/faker_generation.py "
            "--date {{ ds }}"
        ),
        outlets=[postgres_transactions_ds],
    )

    # Task 2 — Validate data quality with Great Expectations
    validate_with_gx = PythonOperator(
        task_id="validate_with_gx",
        python_callable=run_gx_checkpoint,
        inlets=[postgres_transactions_ds],
        outlets=[postgres_transactions_ds],
    )

    # Task 3 — Extract validated data from Postgres → BigQuery bronze
    extract_postgres_to_bq = BashOperator(
        task_id="extract_postgres_to_bq",
        bash_command=(
            f"python3 {REPO_ROOT}/database/pg_to_bq.py "
            "{{ ds }}"
        ),
        inlets=[postgres_transactions_ds],
        outlets=[bigquery_bronze_ds],
    )

    # Task 4 — Run dbt staging models (bronze → analytics.stg_*)
    run_dbt_staging = BashOperator(
        task_id="run_dbt_staging",
        bash_command=(
            "dbt run --select staging "
            f"--project-dir {REPO_ROOT}/dbt "
            f"--profiles-dir {REPO_ROOT}/dbt "
            "--target prod"
        ),
        inlets=[bigquery_bronze_ds],
        outlets=[bigquery_analytics_ds],
    )

    # Task 5 — Run dbt Silver model (staging → analytics.silver_enriched_transactions)
    run_dbt_silver = BashOperator(
        task_id="run_dbt_silver",
        bash_command=(
            "dbt run --select silver_enriched_transactions "
            f"--project-dir {REPO_ROOT}/dbt "
            f"--profiles-dir {REPO_ROOT}/dbt "
            "--target prod"
        ),
        inlets=[bigquery_analytics_ds],
        outlets=[bigquery_silver_ds],
    )

    # Task 6 — dbt test: validate integrity after BigQuery transport
    run_dbt_test = BashOperator(
        task_id="run_dbt_test",
        bash_command=(
            "dbt test --select stg_transactions "
            f"--project-dir {REPO_ROOT}/dbt "
            f"--profiles-dir {REPO_ROOT}/dbt "
            "--target prod"
        ),
        inlets=[bigquery_analytics_ds],
    )

    # Task 7 — ML Prediction: score transactions from Silver table
    # Runs on the host .venv (TensorFlow + scikit-learn are too heavy for Docker)
    run_ml_prediction = BashOperator(
        task_id="run_ml_prediction",
        bash_command=(
            "/home/aboubakr/Desktop/enterprise-data-observability-platform/"
            ".venv/bin/python "
            "/home/aboubakr/Desktop/enterprise-data-observability-platform/"
            "mlops/predict.py"
        ),
        inlets=[bigquery_silver_ds],
    )

    # Linear dependency chain — if any task fails, downstream stops
    (
        generate_faker_data
        >> validate_with_gx
        >> extract_postgres_to_bq
        >> run_dbt_staging
        >> run_dbt_silver
        >> run_dbt_test
        >> run_ml_prediction
    )
