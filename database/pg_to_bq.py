#!/usr/bin/env python3
"""Script to copy data from Postgres to BigQuery bronze dataset.

Usage: python database/pg_to_bq.py 2026-05-23

Free-Tier-Compatible Incremental Strategy:
===========================================
BigQuery Free Tier forbids DML queries (DELETE/UPDATE/MERGE).
Instead, we rely on Postgres as the cumulative source of truth:

  - faker_generation.py APPENDS new transactions into Postgres each day.
  - This script extracts the FULL accumulated history from Postgres
    and WRITE_TRUNCATE it into BigQuery bronze.transactions.
  - Each successive Airflow catchup run adds one more day to Postgres,
    so the TRUNCATE+LOAD progressively builds up the timeline.

After the complete catchup (May 1 → May 24), BigQuery will contain
all 24 days of transaction history — no DML needed.

Dimension tables (accounts, devices, merchants) are small reference data
and are refreshed in full (WRITE_TRUNCATE) each run.
"""
import os
import sys
from datetime import datetime

import pandas as pd
import psycopg2
from google.cloud import bigquery
from google.api_core.exceptions import Conflict


def connect_postgres():
    dsn = os.environ.get('DATABASE_URL') or 'postgresql://airflow:airflow@postgres/airflow'
    return psycopg2.connect(dsn)


def extract_all_transactions(conn):
    """Extract ALL accumulated transactions from Postgres.

    Postgres is the cumulative source of truth: faker_generation.py
    adds transactions day by day (idempotent per date), so this table
    grows with each catchup run.  We extract everything and load into
    BigQuery with WRITE_TRUNCATE — each run captures the full history.
    """
    query = (
        "SELECT transaction_id, account_id, device_id, merchant_id, "
        "transaction_amount, transaction_date, transaction_type, "
        "transaction_duration, account_balance, channel, location, "
        "ip_address, login_attempts "
        "FROM core_banking.transactions "
        "ORDER BY transaction_date"
    )
    df = pd.read_sql(query, conn)
    return df


def extract_accounts(conn):
    """Extract all accounts from Postgres"""
    query = "SELECT * FROM core_banking.accounts"
    df = pd.read_sql(query, conn)
    return df


def extract_devices(conn):
    """Extract all devices from Postgres"""
    query = "SELECT * FROM core_banking.devices"
    df = pd.read_sql(query, conn)
    return df


def extract_merchants(conn):
    """Extract all merchants from Postgres"""
    query = "SELECT * FROM core_banking.merchants"
    df = pd.read_sql(query, conn)
    return df


def ensure_dataset(client, dataset_id, project):
    dataset_ref = bigquery.Dataset(f"{project}.{dataset_id}")
    try:
        client.create_dataset(dataset_ref)
        print(f"Created dataset {project}.{dataset_id}")
    except Conflict:
        pass  # already exists


def load_to_bq(df, project, dataset_id, table_name):
    """Load a dataframe into BigQuery with WRITE_TRUNCATE.

    Free-Tier friendly: WRITE_TRUNCATE is a load-job disposition,
    NOT a DML query — it is allowed on the free tier.
    """
    client = bigquery.Client()
    table_id = f"{project}.{dataset_id}.{table_name}"
    job_config = bigquery.LoadJobConfig(
        write_disposition="WRITE_TRUNCATE",
    )
    job = client.load_table_from_dataframe(df, table_id, job_config=job_config)
    job.result()
    print(f"[TRUNCATE+LOAD] Loaded {len(df)} rows into {table_id}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python pg_to_bq.py YYYY-MM-DD")
        sys.exit(2)

    target_date = sys.argv[1]
    # validate date
    try:
        _ = datetime.strptime(target_date, "%Y-%m-%d").date()
    except Exception:
        print("Invalid date format, expected YYYY-MM-DD")
        sys.exit(2)

    project = os.environ.get('GCP_PROJECT') or os.environ.get('GOOGLE_CLOUD_PROJECT') or None
    if not project:
        client = bigquery.Client()
        project = client.project

    dataset = os.environ.get('BIGQUERY_DATASET', 'bronze')

    # Initialize BigQuery client and ensure dataset exists
    bq_client = bigquery.Client()
    ensure_dataset(bq_client, dataset, project)

    # ------------------------------------------------------------------
    # Extract all data from Postgres and load to BigQuery
    # ------------------------------------------------------------------
    conn = connect_postgres()
    try:
        # FACT TABLE — full extract + WRITE_TRUNCATE
        # Postgres accumulates data across catchup runs, so this progressively
        # builds up the full timeline in BigQuery.
        df = extract_all_transactions(conn)
        if not df.empty:
            # Log the date range being loaded for observability
            min_date = df['transaction_date'].min()
            max_date = df['transaction_date'].max()
            n_days = df['transaction_date'].dt.date.nunique()
            print(f"Postgres contains {len(df)} transactions spanning {n_days} days ({min_date} → {max_date})")
            load_to_bq(df, project, dataset, 'transactions')
        else:
            print(f"No transactions found in Postgres (target_date={target_date})")

        # DIMENSION TABLES — full refresh (small reference data)
        accounts_df = extract_accounts(conn)
        devices_df = extract_devices(conn)
        merchants_df = extract_merchants(conn)
    finally:
        conn.close()

    if not accounts_df.empty:
        load_to_bq(accounts_df, project, dataset, 'accounts')
    if not devices_df.empty:
        load_to_bq(devices_df, project, dataset, 'devices')
    if not merchants_df.empty:
        load_to_bq(merchants_df, project, dataset, 'merchants')


if __name__ == '__main__':
    main()

