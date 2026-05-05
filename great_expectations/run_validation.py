import great_expectations as gx

context = gx.get_context()

checkpoint_name = "sample_checkpoint"

# Define the checkpoint configuration
checkpoint_config = {
    "name": checkpoint_name,
    "config_version": 1.0,
    "class_name": "Checkpoint",
    "run_name_template": "%Y%m%d-%H%M%S-sample-run",
    "expectation_suite_name": "sample_suite",
    "action_list": [
        {
            "name": "store_validation_result",
            "action": {"class_name": "StoreValidationResultAction"},
        },
        {
            "name": "update_data_docs",
            "action": {"class_name": "UpdateDataDocsAction"},
        },
    ],
    "validations": [
        {
            "batch_request": {
                "datasource_name": "my_postgres_datasource",
                "data_connector_name": "default_inferred_data_connector_name",
                "data_asset_name": "public.sample_data",
            },
        }
    ],
}

context.add_or_update_checkpoint(**checkpoint_config)
print(f"Checkpoint '{checkpoint_name}' created.")

# Run the checkpoint
results = context.run_checkpoint(checkpoint_name=checkpoint_name)

if results.success:
    print("Validation succeeded!")
else:
    print("Validation failed!")

for validation_result in results.run_results.values():
    print(f"Statistics: {validation_result['validation_result']['statistics']}")
