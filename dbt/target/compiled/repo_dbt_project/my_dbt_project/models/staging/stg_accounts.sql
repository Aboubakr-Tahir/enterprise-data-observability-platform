

SELECT
    CAST(account_id AS STRING) AS account_id,
    CAST(customer_name AS STRING) AS customer_name,
    CAST(customer_age AS INT64) AS customer_age,
    CAST(customer_occupation AS STRING) AS customer_occupation,
    CAST(account_status AS STRING) AS account_status
FROM `gen-lang-client-0635762262`.`bronze`.`accounts`