
  
    

    create or replace table `gen-lang-client-0635762262`.`silver`.`silver_enriched_transactions`
      
    
    

    OPTIONS()
    as (
      

/*
    Silver Enriched Transactions
    ============================
    Joins staging tables and computes behavioral velocity features.
    Text columns (transaction_type, location, channel, customer_occupation)
    are passed through RAW — encoding is handled by predict.py at inference time.

    Velocity features mirror the pandas rolling logic from the training notebook:
      - account_tx_count_24h  : # transactions per account in the preceding 24 hours
      - account_avg_amount_7d : avg transaction amount per account over 7 preceding days
      - merchant_tx_count_1h  : # transactions per merchant in the preceding 1 hour
      - amount_vs_avg_ratio   : current amount / (7-day avg + 0.1)
*/

WITH base AS (
    SELECT
        t.transaction_id,
        t.account_id,
        t.device_id,
        t.merchant_id,
        t.ip_address,
        t.transaction_amount,
        t.transaction_date,
        t.transaction_type,
        t.transaction_duration,
        t.account_balance,
        t.login_attempts,
        t.channel,
        t.location,

        -- Joined from accounts
        a.customer_age,
        a.customer_occupation,

        -- Temporal features
        EXTRACT(HOUR FROM t.transaction_date)    AS tx_hour,
        EXTRACT(DAYOFWEEK FROM t.transaction_date) - 1 AS tx_day_of_week  -- 0=Sun … 6=Sat

    FROM `gen-lang-client-0635762262`.`analytics`.`stg_transactions` AS t
    LEFT JOIN `gen-lang-client-0635762262`.`analytics`.`stg_accounts` AS a
        ON t.account_id = a.account_id
),

-- Velocity: count of transactions per account in the preceding 24 hours
account_velocity AS (
    SELECT
        transaction_id,
        COUNT(*) OVER (
            PARTITION BY account_id
            ORDER BY UNIX_SECONDS(CAST(transaction_date AS TIMESTAMP))
            RANGE BETWEEN 86400 PRECEDING AND CURRENT ROW
        ) AS account_tx_count_24h,

        AVG(transaction_amount) OVER (
            PARTITION BY account_id
            ORDER BY UNIX_SECONDS(CAST(transaction_date AS TIMESTAMP))
            RANGE BETWEEN 604800 PRECEDING AND CURRENT ROW
        ) AS account_avg_amount_7d

    FROM base
),

-- Velocity: count of transactions per merchant in the preceding 1 hour
merchant_velocity AS (
    SELECT
        transaction_id,
        COUNT(*) OVER (
            PARTITION BY merchant_id
            ORDER BY UNIX_SECONDS(CAST(transaction_date AS TIMESTAMP))
            RANGE BETWEEN 3600 PRECEDING AND CURRENT ROW
        ) AS merchant_tx_count_1h

    FROM base
)

SELECT
    b.transaction_id,
    b.account_id,
    b.device_id,
    b.merchant_id,
    b.ip_address,
    b.transaction_amount,
    b.transaction_date,
    b.transaction_type,
    b.transaction_duration,
    b.account_balance,
    b.login_attempts,
    b.channel,
    b.location,
    b.customer_age,
    b.customer_occupation,
    b.tx_hour,
    b.tx_day_of_week,

    av.account_tx_count_24h,
    av.account_avg_amount_7d,
    mv.merchant_tx_count_1h,

    -- Ratio: current amount vs 7-day average (add 0.1 to avoid division by zero)
    SAFE_DIVIDE(b.transaction_amount, av.account_avg_amount_7d + 0.1) AS amount_vs_avg_ratio

FROM base AS b
LEFT JOIN account_velocity AS av ON b.transaction_id = av.transaction_id
LEFT JOIN merchant_velocity AS mv ON b.transaction_id = mv.transaction_id
    );
  