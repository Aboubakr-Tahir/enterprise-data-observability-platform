{{ config(
    materialized='view'
) }}

SELECT
    CAST(merchant_id AS STRING) AS merchant_id,
    CAST(merchant_name AS STRING) AS merchant_name,
    CAST(category AS STRING) AS category,
    CAST(merchant_city AS STRING) AS merchant_city
FROM {{ source('postgres_bronze', 'merchants') }}
