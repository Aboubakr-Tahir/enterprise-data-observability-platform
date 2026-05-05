import great_expectations as gx

context = gx.get_context()

suite_name = "sample_suite"
context.add_or_update_expectation_suite(expectation_suite_name=suite_name)

datasource = context.get_datasource("my_postgres_datasource")

# Define expectations
suite = context.get_expectation_suite(suite_name)

from great_expectations.core.expectation_configuration import ExpectationConfiguration

# 1. Expect 'id' to be unique and not null
suite.add_expectation(ExpectationConfiguration(
    expectation_type="expect_column_values_to_not_be_null",
    kwargs={"column": "id"}
))
suite.add_expectation(ExpectationConfiguration(
    expectation_type="expect_column_values_to_be_unique",
    kwargs={"column": "id"}
))

# 2. Expect 'age' to be between 0 and 120
suite.add_expectation(ExpectationConfiguration(
    expectation_type="expect_column_values_to_be_between",
    kwargs={"column": "age", "min_value": 0, "max_value": 120}
))

# 3. Expect 'email' to match a regex
suite.add_expectation(ExpectationConfiguration(
    expectation_type="expect_column_values_to_match_regex",
    kwargs={"column": "email", "regex": r"^[^@]+@[^@]+\.[^@]+$"}
))

context.save_expectation_suite(suite)
print(f"Expectation suite '{suite_name}' created and saved.")
