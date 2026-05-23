{{ config(
    materialized='view'
) }}

SELECT
    CAST(transaction_id AS STRING) AS transaction_id,
    CAST(account_id AS STRING) AS account_id,
    CAST(device_id AS STRING) AS device_id,
    CAST(merchant_id AS STRING) AS merchant_id,
    CAST(transaction_amount AS NUMERIC) AS transaction_amount,
    CAST(transaction_date AS TIMESTAMP) AS transaction_date,
    CAST(transaction_type AS STRING) AS transaction_type,
    CAST(transaction_duration AS INT64) AS transaction_duration,
    CAST(account_balance AS NUMERIC) AS account_balance,
    CAST(channel AS STRING) AS channel,
    CAST(location AS STRING) AS location,
    CAST(ip_address AS STRING) AS ip_address,
    CAST(login_attempts AS INT64) AS login_attempts
FROM {{ source('postgres_bronze', 'transactions') }}
