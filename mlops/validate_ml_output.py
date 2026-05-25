#!/usr/bin/env python3
"""
Great Expectations Validation Script for Machine Learning Output (GX 1.x Fluent API)
===================================================================================

This script reads the anomaly detection scored output table from BigQuery,
converts it to a Great Expectations batch, and runs key expectations
to guarantee the format, schema, and boundaries of our unsupervised AI predictions:
  1. Ensure anomaly_score is not null/NaN.
  2. Validate that anomaly_score is strictly between 0 and 1.
  3. Verify that transaction_id is present (not null) and unique.
  4. Validate that is_anomaly is strictly in [0, 1].

Exits with code 0 on success, or code 1 if validations fail.
"""

import os
import sys
from pathlib import Path
import pandas as pd
from google.cloud import bigquery
import great_expectations as gx
from great_expectations.expectations import (
    ExpectColumnValuesToNotBeNull,
    ExpectColumnValuesToBeBetween,
    ExpectColumnValuesToBeUnique,
    ExpectColumnValuesToBeInSet,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
GCP_KEYFILE = REPO_ROOT / "gcp-key.json"
BQ_PROJECT = os.environ.get("GCP_PROJECT_ID", "gen-lang-client-0635762262")
BQ_SCORED_TABLE = f"{BQ_PROJECT}.silver.silver_scored_transactions"


def read_scored_from_bigquery():
    """Read the scored transactions table from BigQuery."""
    # Use mounted environment keyfile in Docker container, otherwise fallback to local keyfile
    if 'GOOGLE_APPLICATION_CREDENTIALS' not in os.environ or not os.path.exists(os.environ['GOOGLE_APPLICATION_CREDENTIALS']):
        if GCP_KEYFILE.exists():
            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = str(GCP_KEYFILE)
            
    client = bigquery.Client(project=BQ_PROJECT)
    query = f"SELECT * FROM `{BQ_SCORED_TABLE}`"
    df = client.query(query).to_dataframe()
    print(f"Loaded {len(df)} scored rows from BigQuery table: {BQ_SCORED_TABLE}")
    return df


def main():
    print("---------------------------------------------------------------------------")
    print("      Great Expectations - ML Output Validation (GX 1.17.2)")
    print("---------------------------------------------------------------------------")

    # 1. Load data
    try:
        df = read_scored_from_bigquery()
    except Exception as e:
        print(f"❌ Error loading data from BigQuery: {e}")
        sys.exit(1)

    if df.empty:
        print("❌ Scored table is empty! Validation failed.")
        sys.exit(1)

    # 2. Initialize Ephemeral Data Context and fluent datasource
    context = gx.get_context(mode="ephemeral")
    ds = context.data_sources.add_pandas("ml_pandas_datasource")
    asset = ds.add_dataframe_asset("ml_scored_asset")
    batch_definition = asset.add_batch_definition_whole_dataframe("whole_dataframe_batch")
    
    # 3. Create Expectation Suite
    suite = context.suites.add(gx.ExpectationSuite(name="ml_output_expectation_suite"))

    # 4. Add Expectations
    print("Configuring expectations...")
    suite.add_expectation(ExpectColumnValuesToNotBeNull(column="transaction_id"))
    suite.add_expectation(ExpectColumnValuesToBeUnique(column="transaction_id"))
    suite.add_expectation(ExpectColumnValuesToNotBeNull(column="anomaly_score"))
    suite.add_expectation(ExpectColumnValuesToBeBetween(column="anomaly_score", min_value=0.0, max_value=1.0))
    suite.add_expectation(ExpectColumnValuesToBeInSet(column="is_anomaly", value_set=[0, 1]))

    # 5. Build Validation Definition
    validation_definition = context.validation_definitions.add(
        gx.ValidationDefinition(
            name="ml_output_validation_definition",
            data=batch_definition,
            suite=suite,
        )
    )

    # 6. Run Validation
    print("Running validations...")
    run_result = validation_definition.run(batch_parameters={"dataframe": df})

    # 7. Print results & determine final status
    success = run_result.success
    print("\n---------------------------------------------------------------------------")
    print(f"{'EXPECTATION TYPE':<32} | {'COLUMN':<16} | {'STATUS':<7} | {'SUCCESS RATE':<12}")
    print("---------------------------------------------------------------------------")
    
    for res in run_result.results:
        exp_type = res.expectation_config._type
        col_name = res.expectation_config._kwargs.get("column", "N/A")
        status_str = "SUCCESS" if res.success else "FAILED"
        
        # Calculate success percentage
        if res.success:
            success_rate = 100.0
        else:
            unexpected_pct = res.result.get("unexpected_percent")
            if unexpected_pct is not None:
                success_rate = 100.0 - unexpected_pct
            else:
                success_rate = 0.0
                
        print(f"{exp_type:<32} | {col_name:<16} | {status_str:<7} | {success_rate:>10.2f}%")

    print("---------------------------------------------------------------------------")

    if success:
        print("\n✓ ALL ML OUTPUT VALIDATIONS PASSED SUCCESSFULY! 🎉")
        sys.exit(0)
    else:
        print("\n❌ SOME EXPECTATIONS FAILED! Please inspect model outputs above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
