create schema if not exists core_banking;

CREATE TABLE accounts (
    account_id VARCHAR(50) PRIMARY KEY,
    customer_name VARCHAR(100) NOT NULL,
    customer_age INT NOT NULL,
    customer_occupation VARCHAR(100),
    account_status VARCHAR(20) DEFAULT 'ACTIVE' -- ACTIVE, SUSPENDED, FROZEN
);

CREATE TABLE devices (
    device_id VARCHAR(50) PRIMARY KEY,
    device_name VARCHAR(100),
    device_type VARCHAR(50),                   -- Mobile, Desktop, Tablet
    os VARCHAR(50)                             -- Android, iOS, Windows
);

CREATE TABLE merchants (
    merchant_id VARCHAR(50) PRIMARY KEY,
    merchant_name VARCHAR(100) NOT NULL,
    category VARCHAR(100),                     -- Retail, Electronics, Food, etc.
    merchant_city VARCHAR(100)
);

CREATE TABLE transactions (
    transaction_id VARCHAR(50) PRIMARY KEY,
    account_id VARCHAR(50) NOT NULL,
    device_id VARCHAR(50),                     -- Peut être NULL si retrait ATM physique par exemple
    merchant_id VARCHAR(50),                   -- Applicable uniquement pour les paiements / transferts marchands
    transaction_amount NUMERIC(15, 2) NOT NULL,
    transaction_date TIMESTAMP NOT NULL,
    transaction_type VARCHAR(50) NOT NULL,     -- withdrawal, deposit, transfer, payment
    transaction_duration INT,                  -- Durée en secondes ou millisecondes
    account_balance NUMERIC(15, 2) NOT NULL,    -- Le solde historique APRÈS l'événement
    channel VARCHAR(50),                       -- ATM, mobile banking, online banking
    location VARCHAR(100),
    ip_address VARCHAR(45),                    -- VARCHAR(45) pour supporter pleinement l'IPv6
    login_attempts INT DEFAULT 1,

    CONSTRAINT fk_transactions_account 
        FOREIGN KEY (account_id) REFERENCES accounts(account_id) 
        ON DELETE RESTRICT ON UPDATE CASCADE,
        
    CONSTRAINT fk_transactions_device 
        FOREIGN KEY (device_id) REFERENCES devices(device_id) 
        ON DELETE SET NULL ON UPDATE CASCADE,
        
    CONSTRAINT fk_transactions_merchant 
        FOREIGN KEY (merchant_id) REFERENCES merchants(merchant_id) 
        ON DELETE RESTRICT ON UPDATE CASCADE
);

SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'core_banking' 
  AND table_type = 'BASE TABLE';


CREATE INDEX idx_transactions_account_date 
ON transactions (account_id, transaction_date DESC);