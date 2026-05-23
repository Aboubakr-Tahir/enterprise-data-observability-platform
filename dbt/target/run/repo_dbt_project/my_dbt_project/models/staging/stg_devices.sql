

  create or replace view `gen-lang-client-0635762262`.`analytics`.`stg_devices`
  OPTIONS()
  as 

SELECT
    CAST(device_id AS STRING) AS device_id,
    CAST(device_name AS STRING) AS device_name,
    CAST(device_type AS STRING) AS device_type,
    CAST(os AS STRING) AS os
FROM `gen-lang-client-0635762262`.`bronze`.`devices`;

