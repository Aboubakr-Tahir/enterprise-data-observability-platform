
  
    

    create or replace table `gen-lang-client-0635762262`.`gold`.`gold_fact_transactions`
      
    
    

    OPTIONS()
    as (
      

/*
    Flux Business Purifié :
    Garantit des KPI financiers exacts en excluant toutes les anomalies détectées par l'IA.

    Materialization: TABLE (full rebuild each run).
    BigQuery Free Tier forbids MERGE DML, so we use full rebuild instead of incremental.
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
FROM `gen-lang-client-0635762262`.`silver`.`silver_scored_transactions` s
JOIN `gen-lang-client-0635762262`.`silver`.`silver_enriched_transactions` t
  ON s.transaction_id = t.transaction_id
WHERE s.is_anomaly = 0
    );
  