from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta
import great_expectations as gx

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': datetime(2026, 5, 5),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

def run_gx_validation():
    context = gx.get_context()
    checkpoint_name = "sample_checkpoint"
    results = context.run_checkpoint(checkpoint_name=checkpoint_name)
    
    if not results.success:
        # In a real scenario, you might want to raise an exception to fail the task
        # raise Exception("Great Expectations validation failed!")
        print("Validation failed, but continuing DAG for demonstration.")
    else:
        print("Validation succeeded!")

with DAG(
    'data_quality_check',
    default_args=default_args,
    description='A simple DAG to run Great Expectations validation',
    schedule_interval=timedelta(days=1),
    catchup=False,
) as dag:

    validate_data = PythonOperator(
        task_id='run_great_expectations_validation',
        python_callable=run_gx_validation,
    )

    validate_data
