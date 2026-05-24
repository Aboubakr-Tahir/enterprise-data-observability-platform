{{ config(
    materialized='incremental',
    unique_key='transaction_id',
    schema='gold'
) }}

/*
    Flux de Quarantaine :
    Isole uniquement les transactions signalées par l'Ensemble ML pour investigation.
*/

SELECT 
    s.transaction_id,
    s.account_id,
    t.transaction_amount,
    s.transaction_date,
    s.anomaly_score,
    s.threshold_used,
    s.ip_address,
    s.device_id
FROM {{ source('ml_results', 'silver_scored_transactions') }} s
JOIN {{ ref('silver_enriched_transactions') }} t
  ON s.transaction_id = t.transaction_id
WHERE s.is_anomaly = 1

{% if is_incremental() %}
  AND s.transaction_date > (SELECT MAX(transaction_date) FROM {{ this }})
{% endif %}
