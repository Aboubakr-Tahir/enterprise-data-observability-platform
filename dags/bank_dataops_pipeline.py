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
from airflow.datasets import Dataset

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
REPO_ROOT = "/opt/airflow"
GX_CONTEXT_DIR = f"{REPO_ROOT}/great_expectations"
GX_CHECKPOINT_NAME = "sample_checkpoint"
AIRFLOW_GX_DB_CONN = "postgresql+psycopg2://airflow:airflow@postgres/airflow"
GCP_PROJECT = os.environ.get("GCP_PROJECT_ID", "gen-lang-client-0635762262")

# ---------------------------------------------------------------------------
# Airflow dataset declarations (Airflow native, AIP-60 / OpenLineage compliant)
# ---------------------------------------------------------------------------
postgres_transactions_ds = Dataset("postgres://postgres:5432/airflow/core_banking/transactions")
bigquery_bronze_ds = Dataset(f"bigquery://{GCP_PROJECT}/bronze/transactions")
bigquery_analytics_ds = Dataset(f"bigquery://{GCP_PROJECT}/analytics/stg_transactions")
bigquery_silver_ds = Dataset(f"bigquery://{GCP_PROJECT}/silver/silver_enriched_transactions")
bigquery_scored_ds = Dataset(f"bigquery://{GCP_PROJECT}/silver/silver_scored_transactions")
bigquery_gold_fact_ds = Dataset(f"bigquery://{GCP_PROJECT}/gold/gold_fact_transactions")
bigquery_gold_quarantine_ds = Dataset(f"bigquery://{GCP_PROJECT}/gold/gold_quarantine_transactions")

# ---------------------------------------------------------------------------
# Custom Operators for Guaranteed OpenLineage Extraction (Direct HTTP)
# ---------------------------------------------------------------------------
import urllib.request
import json
import uuid

def emit_direct_lineage(task_id, inlets, outlets):
    """Directly forces OpenLineage metadata into Marquez via HTTP API."""
    # Marquez runs locally on port 5000 inside the Docker network
    url = "http://marquez:5000/api/v1/lineage"
    
    def parse_dataset(ds):
        if not hasattr(ds, "uri"): return None
        parts = ds.uri.split("://")
        if len(parts) < 2: return None
        protocol = parts[0]
        rest = parts[1]
        
        # We force all datasets into 'my_data_stack' namespace so they 
        # appear immediately in the Marquez UI alongside the jobs.
        if protocol == "postgres":
            name_parts = rest.split("/")
            name = "postgres." + (".".join(name_parts[1:]) if len(name_parts) > 1 else rest)
            return {"namespace": "my_data_stack", "name": name}
        elif protocol == "bigquery":
            name = "bigquery." + rest.replace("/", ".")
            return {"namespace": "my_data_stack", "name": name}
        return None

    inputs = [parse_dataset(ds) for ds in inlets]
    inputs = [ds for ds in inputs if ds is not None]
    
    outputs = [parse_dataset(ds) for ds in outlets]
    outputs = [ds for ds in outputs if ds is not None]

    if not inputs and not outputs:
        return

    event = {
        "eventTime": datetime.now().isoformat() + "Z",
        "eventType": "COMPLETE",
        "run": {"runId": str(uuid.uuid4())},
        "job": {
            "namespace": "my_data_stack",
            "name": f"bank_dataops_pipeline.{task_id}"
        },
        "inputs": inputs,
        "outputs": outputs,
        "producer": "custom-airflow-emitter"
    }

    try:
        req = urllib.request.Request(
            url, 
            data=json.dumps(event).encode('utf-8'), 
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=3) as response:
            print(f"Successfully pushed lineage to Marquez for {task_id}.")
    except Exception as e:
        print(f"Failed to emit lineage for {task_id}: {e}")

class LineageBashOperator(BashOperator):
    def execute(self, context):
        res = super().execute(context)
        inlets = getattr(self, "inlets", [])
        outlets = getattr(self, "outlets", [])
        emit_direct_lineage(self.task_id, inlets, outlets)
        return res

class LineagePythonOperator(PythonOperator):
    def execute(self, context):
        res = super().execute(context)
        inlets = getattr(self, "inlets", [])
        outlets = getattr(self, "outlets", [])
        emit_direct_lineage(self.task_id, inlets, outlets)
        return res

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
    "retry_delay": timedelta(seconds=5),
}

with DAG(
    dag_id="bank_dataops_pipeline",
    default_args=default_args,
    description=(
        "End-to-end DataOps pipeline: Faker → GX → BQ bronze → "
        "dbt staging → Silver → dbt test → ML prediction"
    ),
    schedule="@daily",
    start_date=datetime(2026, 5, 1),
    catchup=True,
    max_active_runs=1,
    tags=["dataops", "ingestion", "great-expectations", "bigquery", "dbt", "mlops"],
) as dag:

    # Task 1 — Generate synthetic banking transactions with Faker
    generate_faker_data = LineageBashOperator(
        task_id="generate_faker_data",
        bash_command=(
            f"python3 {REPO_ROOT}/database/faker_generation.py "
            "--date {{ ds }}"
        ),
        outlets=[postgres_transactions_ds],
    )

    # Task 2 — Validate data quality with Great Expectations
    validate_with_gx = LineagePythonOperator(
        task_id="validate_with_gx",
        python_callable=run_gx_checkpoint,
        inlets=[postgres_transactions_ds],
        outlets=[postgres_transactions_ds],
    )

    # Task 3 — Extract validated data from Postgres → BigQuery bronze
    extract_postgres_to_bq = LineageBashOperator(
        task_id="extract_postgres_to_bq",
        bash_command=(
            f"python3 {REPO_ROOT}/database/pg_to_bq.py "
            "{{ ds }}"
        ),
        inlets=[postgres_transactions_ds],
        outlets=[bigquery_bronze_ds],
    )

    # Task 4 — Run dbt staging models (bronze → analytics.stg_*)
    run_dbt_staging = LineageBashOperator(
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
    run_dbt_silver = LineageBashOperator(
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
    run_dbt_test = LineageBashOperator(
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
    # Runs natively inside the Airflow Docker container
    run_ml_prediction = LineageBashOperator(
        task_id="run_ml_prediction",
        bash_command=(
            "python /opt/airflow/mlops/predict.py"
        ),
        inlets=[bigquery_silver_ds],
        outlets=[bigquery_scored_ds],
    )

    # Task 8 — Great Expectations ML Output Validation
    # Runs natively inside the Airflow Docker container, validating format, bounds, and identity schemas
    validate_ml_output_with_gx = LineageBashOperator(
        task_id="validate_ml_output_with_gx",
        bash_command=(
            "python /opt/airflow/mlops/validate_ml_output.py"
        ),
        inlets=[bigquery_scored_ds],
        outlets=[bigquery_scored_ds],
    )

    # Task 9 — dbt Gold: materialize final business and quarantine data products
    run_dbt_gold = LineageBashOperator(
        task_id="run_dbt_gold_layer",
        bash_command=(
            "dbt run --select gold "
            f"--project-dir {REPO_ROOT}/dbt "
            f"--profiles-dir {REPO_ROOT}/dbt "
            "--target prod"
        ),
        inlets=[bigquery_scored_ds, bigquery_silver_ds],
        outlets=[bigquery_gold_fact_ds, bigquery_gold_quarantine_ds],
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
        >> validate_ml_output_with_gx
        >> run_dbt_gold
    )
