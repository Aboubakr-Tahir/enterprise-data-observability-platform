
  
    

    create or replace table `gen-lang-client-0635762262`.`gold`.`gold_quarantine_transactions`
      
    
    

    OPTIONS()
    as (
      

/*
    Flux de Quarantaine :
    Isole uniquement les transactions signalées par l'Ensemble ML pour investigation.

    Materialization: TABLE (full rebuild each run).
    BigQuery Free Tier forbids MERGE DML, so we use full rebuild instead of incremental.
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
FROM `gen-lang-client-0635762262`.`silver`.`silver_scored_transactions` s
JOIN `gen-lang-client-0635762262`.`silver`.`silver_enriched_transactions` t
  ON s.transaction_id = t.transaction_id
WHERE s.is_anomaly = 1
    );
  