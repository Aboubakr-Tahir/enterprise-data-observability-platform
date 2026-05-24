#!/usr/bin/env python3
"""Script to copy data from Postgres to BigQuery bronze dataset.

Usage: python database/pg_to_bq.py 2026-05-23

This script extracts transactions for a specific date and all dimension tables,
then loads them into BigQuery dataset `bronze`.
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


def extract_transactions(conn):
    query = (
        "SELECT transaction_id, account_id, device_id, merchant_id, transaction_amount, transaction_date, "
        "transaction_type, transaction_duration, account_balance, channel, location, ip_address, login_attempts "
        "FROM core_banking.transactions"
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


def load_to_bq(df, project, dataset_id, table_name, truncate=False):
    client = bigquery.Client()
    table_id = f"{project}.{dataset_id}.{table_name}"
    job_config = bigquery.LoadJobConfig()
    if truncate:
        job_config.write_disposition = "WRITE_TRUNCATE"
    job = client.load_table_from_dataframe(df, table_id, job_config=job_config)
    job.result()
    print(f"Loaded {len(df)} rows into {table_id}")


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

    # Extract and load transactions and dimension tables
    conn = connect_postgres()
    try:
        df = extract_transactions(conn)
        if not df.empty:
            load_to_bq(df, project, dataset, 'transactions', truncate=True)
        else:
            print("No transactions found in Postgres")
        
        # Extract dimension tables (full refresh each run)
        accounts_df = extract_accounts(conn)
        devices_df = extract_devices(conn)
        merchants_df = extract_merchants(conn)
    finally:
        conn.close()

    # Load dimension tables with truncate=True to refresh them
    if not accounts_df.empty:
        load_to_bq(accounts_df, project, dataset, 'accounts', truncate=True)
    if not devices_df.empty:
        load_to_bq(devices_df, project, dataset, 'devices', truncate=True)
    if not merchants_df.empty:
        load_to_bq(merchants_df, project, dataset, 'merchants', truncate=True)


if __name__ == '__main__':
    main()
