

  create or replace view `gen-lang-client-0635762262`.`analytics`.`stg_merchants`
  OPTIONS()
  as 

SELECT
    CAST(merchant_id AS STRING) AS merchant_id,
    CAST(merchant_name AS STRING) AS merchant_name,
    CAST(category AS STRING) AS category,
    CAST(merchant_city AS STRING) AS merchant_city
FROM `gen-lang-client-0635762262`.`bronze`.`merchants`;

