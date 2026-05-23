#!/usr/bin/env python3
"""
Create or update a Great Expectations expectation suite named
`transaction_suite` and map it to the existing `sample_checkpoint`.

Usage:
  GX_DB_CONN env var can override the default connection string.
  .venv/bin/python great_expectations/create_transaction_suite.py
"""
import os
import great_expectations as gx
from great_expectations.core.validation_definition import ValidationDefinition
from great_expectations.checkpoint.checkpoint import Checkpoint


def main():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    try:
        context = gx.get_context()
    except Exception as e:
        # If DataContext fails to load (config validation, env, etc.),
        # fall back to filesystem-only changes so the suite and checkpoint
        # files exist for CI / Airflow to consume later.
        context = None
        print(f"Warning: could not load Great Expectations DataContext: {e}")

    # Use env var or default to host-postgres airflow DB (adjust if needed)
    gx_db_conn = os.getenv(
        "GX_DB_CONN",
        "postgresql+psycopg2://airflow:airflow@localhost:5432/airflow",
    )

    datasource_name = "my_postgres_datasource"

    # Ensure datasource points to the desired connection string.
    datasource_config = {
        "name": datasource_name,
        "class_name": "Datasource",
        "execution_engine": {
            "class_name": "SqlAlchemyExecutionEngine",
            "connection_string": gx_db_conn,
        },
        "data_connectors": {
            "default_runtime_data_connector_name": {
                "class_name": "RuntimeDataConnector",
                "batch_identifiers": ["default_identifier_name"],
            },
            "default_inferred_data_connector_name": {
                "class_name": "InferredAssetSqlDataConnector",
                "include_schema_name": True,
            },
        },
    }

    suite_name = "transaction_suite"

    # If we have a working DataContext, register the fluent SQL datasource.
    if context is not None:
        # Add or update a SQL fluent datasource using the modern fluent API
        try:
            # add_or_update_sql will create or update a SQL datasource with the given connection string
            context.data_sources.add_or_update_sql(
                name=datasource_name, connection_string=gx_db_conn
            )
        except Exception as e:
            print(f"Warning: could not add/update fluent SQL datasource: {e}")
    else:
        # Fall back to writing the expectation JSON to the expectations directory
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        expectations_dir = os.path.join(repo_root, "great_expectations", "expectations")
        os.makedirs(expectations_dir, exist_ok=True)
        expectation_file = os.path.join(expectations_dir, f"{suite_name}.json")
        if not os.path.exists(expectation_file):
            import json

            suite = {
                "data_asset_type": None,
                "expectation_suite_name": suite_name,
                "expectations": [
                    {"expectation_type": "expect_column_values_to_not_be_null", "kwargs": {"column": "transaction_id"}, "meta": {}},
                    {"expectation_type": "expect_column_values_to_be_unique", "kwargs": {"column": "transaction_id"}, "meta": {}},
                    {"expectation_type": "expect_column_values_to_not_be_null", "kwargs": {"column": "transaction_amount"}, "meta": {}},
                    {"expectation_type": "expect_column_values_to_be_between", "kwargs": {"column": "transaction_amount", "min_value": 0, "strict_min": True}, "meta": {}},
                    {"expectation_type": "expect_column_values_to_not_be_null", "kwargs": {"column": "account_balance"}, "meta": {}},
                    {"expectation_type": "expect_column_values_to_be_in_set", "kwargs": {"column": "channel", "value_set": ["ATM", "Mobile", "Online", "Branch", "POS"]}, "meta": {}},
                ],
                "ge_cloud_id": None,
                "meta": {"great_expectations_version": "<auto>"},
            }
            with open(expectation_file, "w") as fh:
                json.dump(suite, fh, indent=2)
            print(f"Wrote expectation file: {expectation_file}")
        else:
            print(f"Expectation file already exists: {expectation_file}")

    if context is None:
        print("Warning: skipping checkpoint registration because DataContext could not be loaded.")
        return

    # Ensure the SQL datasource exists and points at the local Postgres instance.
    datasource = context.data_sources.add_or_update_sql(
        name=datasource_name, connection_string=gx_db_conn
    )

    # Create a whole-table batch definition for core_banking.transactions.
    asset_name = "core_banking_transactions"
    try:
        asset = datasource.get_asset(asset_name)
    except LookupError:
        asset = datasource.add_table_asset(
            name=asset_name,
            table_name="transactions",
            schema_name="core_banking",
        )

    try:
        batch_definition = asset.get_batch_definition("whole_table")
    except KeyError:
        batch_definition = asset.add_batch_definition_whole_table(name="whole_table")

    suite = context.suites.get(suite_name)
    validation_name = "transaction_validation_definition"
    validation_definition = ValidationDefinition(
        name=validation_name,
        data=batch_definition,
        suite=suite,
    )
    validation_definition = context.validation_definitions.add_or_update(validation_definition)

    checkpoint = Checkpoint(
        name="sample_checkpoint",
        validation_definitions=[validation_definition],
        actions=[],
    )
    checkpoint = context.checkpoints.add_or_update(checkpoint)
    print(f"Registered checkpoint in store: {checkpoint.name}")

    # Update the sample_checkpoint to point to this suite and table
    checkpoint_name = "sample_checkpoint"

    # Build a validations entry that the existing checkpoint can consume
    validations = [
        {
            "batch_request": {
                "datasource_name": datasource_name,
                "data_connector_name": "default_inferred_data_connector_name",
                "data_asset_name": "core_banking.transactions",
            },
            "expectation_suite_name": suite_name,
        }
    ]

    # Read existing checkpoint file and update minimal fields
    if context is not None:
        checkpoint_path = os.path.join(context.root_directory, "checkpoints", f"{checkpoint_name}.yml")
    else:
        checkpoint_path = os.path.join(repo_root, "great_expectations", "checkpoints", f"{checkpoint_name}.yml")
    try:
        import yaml

        with open(checkpoint_path, "r") as fh:
            cfg = yaml.safe_load(fh) or {}

        cfg["name"] = checkpoint_name
        cfg["expectation_suite_name"] = suite_name
        cfg["validations"] = validations

        with open(checkpoint_path, "w") as fh:
            yaml.safe_dump(cfg, fh, sort_keys=False)

        print(f"Updated checkpoint: {checkpoint_path}")
    except Exception as e:
        print(f"Warning: could not update checkpoint file: {e}")


if __name__ == "__main__":
    main()
