{{ config(
    materialized='incremental',
    unique_key='transaction_id',
    schema='gold'
) }}

/*
    Flux Business Purifié :
    Garantit des KPI financiers exacts en excluant toutes les anomalies détectées par l'IA.
*/

SELECT 
    s.transaction_id,
    s.account_id,
    s.merchant_id,
    t.transaction_amount,
    s.transaction_date,
    t.transaction_type,
    t.channel,
    t.location
FROM {{ source('ml_results', 'silver_scored_transactions') }} s
JOIN {{ ref('silver_enriched_transactions') }} t
  ON s.transaction_id = t.transaction_id
WHERE s.is_anomaly = 0

{% if is_incremental() %}
  AND s.transaction_date > (SELECT MAX(transaction_date) FROM {{ this }})
{% endif %}
