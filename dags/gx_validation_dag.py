from __future__ import annotations

import os
from datetime import datetime, timedelta

import great_expectations as gx
from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from openlineage.client.run import Dataset


REPO_ROOT = "/opt/airflow"
GX_CONTEXT_DIR = f"{REPO_ROOT}/great_expectations"
GX_CHECKPOINT_NAME = "sample_checkpoint"
AIRFLOW_GX_DB_CONN = "postgresql+psycopg2://airflow:airflow@postgres/airflow"

gx_transactions_dataset = Dataset(
    namespace="postgres://postgres:5432",
    name="airflow.core_banking.transactions",
)


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
        raise RuntimeError("Great Expectations checkpoint failed")


default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}


with DAG(
    dag_id="data_ingestion_and_quality",
    default_args=default_args,
    description="Generate daily bank transactions and validate them with Great Expectations",
    schedule="@daily",
    start_date=datetime(2026, 5, 22),
    catchup=False,
    max_active_runs=1,
    tags=["dataops", "ingestion", "great-expectations"],
) as dag:
    generate_daily_transactions = BashOperator(
        task_id="generate_daily_transactions",
        bash_command=f"python3 {REPO_ROOT}/database/faker_generation.py --date {{{{ ds }}}}",
        outlets=[gx_transactions_dataset],
    )

    validate_transactions = PythonOperator(
        task_id="validate_transactions",
        python_callable=run_gx_checkpoint,
        inlets=[gx_transactions_dataset],
    )

    generate_daily_transactions >> validate_transactions
