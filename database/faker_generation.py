#!/usr/bin/env python3
"""
Generate synthetic transactions for a given date and load into Postgres.

Usage:
  python database/faker_generation.py --date 2026-05-22

Behavior:
- Idempotent for a given date (deterministic generation based on date seed).
- Ensures dimension tables (accounts, devices, merchants) contain a fixed pool (~100 each).
- Computes running balances per account using prior latest balance (before the date) as starting point.
- All generated transactions have timestamps strictly on the given date.

Chaos Injection Strategy (for observability demonstration):
───────────────────────────────────────────────────────────
• EVEN days: ~5% structural corruptions (negative amounts, unknown channels)
  → Triggers GX Core failures → DAG blocked → Marquez lineage shows RED
• ODD days:  ~10% behavioral fraud patterns (brute force, skimming, laundering)
  → GX passes → ML ensemble detects and quarantines → Gold dashboard shows alerts
"""
import argparse
import random
from datetime import datetime, timedelta, date as datecls
import decimal
import os
import sys
import uuid

from faker import Faker
import psycopg2
import psycopg2.extras


DEFAULT_DSNS = [
    os.environ.get("DATABASE_URL"),
    "postgresql://airflow:airflow@postgres/airflow",
    "postgresql://airflow:airflow@localhost:5432/airflow",
]


def parse_args():
    p = argparse.ArgumentParser()
    today_str = datetime.today().strftime("%Y-%m-%d")
    p.add_argument(
        "--date",
        default=today_str,
        help=f"Target date in YYYY-MM-DD format (all transactions on this date). Defaults to {today_str}",
    )
    p.add_argument("--min", type=int, default=100, help="Minimum number of transactions to generate")
    p.add_argument("--max", type=int, default=200, help="Maximum number of transactions to generate")
    return p.parse_args()


def connect():
    last_error = None
    for dsn in DEFAULT_DSNS:
        if not dsn:
            continue
        try:
            return psycopg2.connect(dsn)
        except Exception as exc:
            last_error = exc
    raise last_error


def ensure_schema_and_tables(conn):
    # Assumes schema and tables definitions exist (your SQL file). Create schema if missing.
    with conn.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS core_banking")
    conn.commit()


def seed_pools(faker, pool_size=100):
    # deterministic generation of pools using the faker instance seed
    accounts = []
    devices = []
    merchants = []

    for i in range(pool_size):
        account_id = f"ACCT-{i:04d}"
        accounts.append({
            "account_id": account_id,
            "customer_name": faker.name(),
            "customer_age": faker.random_int(min=18, max=85),
            "customer_occupation": faker.job(),
            "account_status": random.choice(["ACTIVE", "SUSPENDED", "FROZEN"]),
        })

        device_id = f"DEV-{i:04d}"
        devices.append({
            "device_id": device_id,
            "device_name": faker.word().title(),
            "device_type": random.choice(["Mobile", "Desktop", "Tablet"]),
            "os": random.choice(["Android", "iOS", "Windows", "Linux"]),
        })

        merchant_id = f"MER-{i:04d}"
        merchants.append({
            "merchant_id": merchant_id,
            "merchant_name": faker.company(),
            "category": random.choice(["Retail", "Electronics", "Food", "Travel", "Services"]),
            "merchant_city": faker.city(),
        })

    return accounts, devices, merchants


def upsert_dimensions(conn, accounts, devices, merchants):
    # Insert or ignore using ON CONFLICT DO NOTHING for idempotency
    with conn.cursor() as cur:
        acct_q = """
            INSERT INTO core_banking.accounts (account_id, customer_name, customer_age, customer_occupation, account_status)
            VALUES (%s,%s,%s,%s,%s) ON CONFLICT (account_id) DO NOTHING
        """
        dev_q = """
            INSERT INTO core_banking.devices (device_id, device_name, device_type, os)
            VALUES (%s,%s,%s,%s) ON CONFLICT (device_id) DO NOTHING
        """
        merch_q = """
            INSERT INTO core_banking.merchants (merchant_id, merchant_name, category, merchant_city)
            VALUES (%s,%s,%s,%s) ON CONFLICT (merchant_id) DO NOTHING
        """

        psycopg2.extras.execute_batch(cur, acct_q, [(a['account_id'], a['customer_name'], a['customer_age'], a['customer_occupation'], a['account_status']) for a in accounts])
        psycopg2.extras.execute_batch(cur, dev_q, [(d['device_id'], d['device_name'], d['device_type'], d['os']) for d in devices])
        psycopg2.extras.execute_batch(cur, merch_q, [(m['merchant_id'], m['merchant_name'], m['category'], m['merchant_city']) for m in merchants])
    conn.commit()


def get_latest_balances(conn, account_ids, target_date):
    # For each account, get the most recent balance before the target_date
    balances = {}
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        q = """
        SELECT account_id, account_balance
        FROM core_banking.transactions
        WHERE account_id = ANY(%s) AND transaction_date < %s
        ORDER BY account_id, transaction_date DESC
        """
        cur.execute(q, (account_ids, target_date))
        rows = cur.fetchall()

    # rows are ordered by account then date desc; pick first occurrence per account
    seen = set()
    for r in rows:
        aid = r['account_id']
        if aid not in seen:
            balances[aid] = float(r['account_balance'])
            seen.add(aid)

    return balances


def generate_transactions_for_date(faker, accounts, devices, merchants, balances, target_date, n_tx):
    """Generate transactions with controlled chaos injection.

    Chaos Strategy (date-driven, deterministic):
    ─────────────────────────────────────────────
    • EVEN days (2, 4, 6, …): ~5% STRUCTURAL corruptions
      → Negative/zero amounts, unknown channels
      → GX Core MUST fail → DAG stops → Marquez shows RED

    • ODD days (1, 3, 5, …): ~10% BEHAVIORAL fraud patterns
      → Structure is valid (GX passes GREEN)
      → ML (Autoencoder + Isolation Forest) detects anomalies
      → Quarantined in Gold layer
    """
    tx_rows = []
    # Realistic channel distribution (not uniform)
    channels = ["Online", "Mobile", "ATM", "POS"]
    channel_weights = [0.50, 0.30, 0.12, 0.08]
    tx_types = ["withdrawal", "deposit", "transfer", "payment"]

    account_ids = [a['account_id'] for a in accounts]
    device_ids = [d['device_id'] for d in devices]
    merchant_ids = [m['merchant_id'] for m in merchants]

    is_even_day = target_date.day % 2 == 0
    n_corrupted = 0
    n_fraud = 0

    for i in range(n_tx):
        account_id = random.choice(account_ids)
        device_id = random.choice(device_ids)
        tx_type = random.choices(tx_types, weights=[0.4, 0.2, 0.1, 0.3])[0]

        merchant_id = None
        if tx_type in ("payment", "transfer"):
            merchant_id = random.choice(merchant_ids)

        amount = round(random.uniform(1.0, 2000.0), 2)

        # transaction timestamp on the target date
        seconds = random.randint(0, 86399)
        tx_time = datetime.combine(target_date, datetime.min.time()) + timedelta(seconds=seconds)

        duration = random.randint(1, 300)  # seconds

        ip_address = faker.ipv4_public()
        channel = random.choices(channels, weights=channel_weights)[0]
        location = faker.city()
        login_attempts = random.choices([1, 1, 1, 2, 3], weights=[0.6, 0.6, 0.6, 0.15, 0.05])[0]

        # ── EVEN DAYS: Inject structural corruptions (5%) ──────────
        # These MUST trigger GX Core failures:
        #   - expect_column_values_to_be_between(transaction_amount, min=0, strict_min=True)
        #   - expect_column_values_to_be_in_set(channel, [ATM, Mobile, Online, Branch, POS])
        if is_even_day:
            roll = random.random()
            if roll < 0.02:
                # Corruption Type 1: Negative amount → violates GX rule 4
                amount = random.choice([-150.00, -500.00, -1200.00])
                n_corrupted += 1
            elif roll < 0.035:
                # Corruption Type 2: Zero amount → violates GX strict_min > 0
                amount = 0.00
                n_corrupted += 1
            elif roll < 0.05:
                # Corruption Type 3: Unknown channel → violates GX rule 6
                channel = random.choice(["UNKNOWN_API_GATEWAY", "INTERNAL_TEST", "DEPRECATED_LEGACY"])
                n_corrupted += 1

        # ── ODD DAYS: Inject behavioral fraud patterns (10%) ───────
        # Structure stays VALID (GX passes), but features are anomalous
        # enough for the ML ensemble to flag them.
        if not is_even_day:
            roll = random.random()
            if roll < 0.04:
                # Fraud Type 1: Account Takeover / Brute Force Attack
                # Huge amount + many login attempts + ultra-fast (bot speed)
                # + forced to nighttime hours (2-5 AM)
                amount = round(random.uniform(15000, 30000), 2)
                login_attempts = random.randint(4, 7)
                duration = random.randint(1, 5)
                seconds = random.randint(7200, 18000)  # 2:00 AM – 5:00 AM
                tx_time = datetime.combine(target_date, datetime.min.time()) + timedelta(seconds=seconds)
                n_fraud += 1
            elif roll < 0.07:
                # Fraud Type 2: Rapid micro-transactions (Card Skimming)
                # Many tiny amounts in very short duration
                amount = round(random.uniform(0.01, 5.00), 2)
                duration = random.randint(1, 3)
                login_attempts = 1
                n_fraud += 1
            elif roll < 0.10:
                # Fraud Type 3: Velocity abuse (Money Laundering pattern)
                # Large amount + abnormally long duration + ATM channel
                amount = round(random.uniform(8000, 20000), 2)
                duration = random.randint(1, 2)
                channel = "ATM"
                login_attempts = random.randint(3, 5)
                n_fraud += 1

        # compute new balance
        cur_balance = balances.get(account_id, None)
        if cur_balance is None:
            cur_balance = round(random.uniform(100.0, 10000.0), 2)
            balances[account_id] = cur_balance

        if tx_type in ("withdrawal", "payment", "transfer"):
            new_balance = round(cur_balance - amount, 2)
        else:  # deposit
            new_balance = round(cur_balance + amount, 2)

        balances[account_id] = new_balance

        tx_id = f"{target_date.isoformat()}-{i:04d}-{uuid.uuid5(uuid.NAMESPACE_URL, account_id + str(i)).hex[:8]}"

        tx_rows.append({
            'transaction_id': tx_id,
            'account_id': account_id,
            'device_id': device_id,
            'merchant_id': merchant_id,
            'transaction_amount': decimal.Decimal(str(amount)),
            'transaction_date': tx_time,
            'transaction_type': tx_type,
            'transaction_duration': duration,
            'account_balance': decimal.Decimal(str(new_balance)),
            'channel': channel,
            'location': location,
            'ip_address': ip_address,
            'login_attempts': login_attempts,
        })

    # Log chaos injection results
    if is_even_day:
        print(f"  🔴 CHAOS MODE (even day {target_date.day}): {n_corrupted}/{n_tx} structural corruptions injected")
        print(f"     → GX Core SHOULD FAIL and block the pipeline")
    else:
        print(f"  🟢 FRAUD MODE (odd day {target_date.day}): {n_fraud}/{n_tx} behavioral fraud patterns injected")
        print(f"     → GX Core should PASS, ML should detect anomalies")

    tx_rows.sort(key=lambda r: r['transaction_date'])
    return tx_rows


def delete_existing_transactions_for_date(conn, target_date):
    # Idempotency: remove transactions already present on that date before inserting
    start = datetime.combine(target_date, datetime.min.time())
    end = datetime.combine(target_date, datetime.max.time())
    with conn.cursor() as cur:
        cur.execute("DELETE FROM core_banking.transactions WHERE transaction_date >= %s AND transaction_date <= %s", (start, end))
        deleted = cur.rowcount
    conn.commit()
    return deleted


def insert_transactions(conn, tx_rows):
    q = """
    INSERT INTO core_banking.transactions (
        transaction_id, account_id, device_id, merchant_id, transaction_amount,
        transaction_date, transaction_type, transaction_duration, account_balance,
        channel, location, ip_address, login_attempts
    ) VALUES (
        %(transaction_id)s, %(account_id)s, %(device_id)s, %(merchant_id)s, %(transaction_amount)s,
        %(transaction_date)s, %(transaction_type)s, %(transaction_duration)s, %(account_balance)s,
        %(channel)s, %(location)s, %(ip_address)s, %(login_attempts)s
    )
    ON CONFLICT (transaction_id) DO NOTHING
    """
    with conn.cursor() as cur:
        psycopg2.extras.execute_batch(cur, q, tx_rows)
    conn.commit()


def main():
    args = parse_args()
    try:
        target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    except Exception:
        print("--date must be in YYYY-MM-DD format", file=sys.stderr)
        sys.exit(2)

    # seed faker and random with the date so runs are deterministic per date
    seed = int(target_date.strftime("%Y%m%d"))
    random.seed(seed)
    faker = Faker()
    faker.seed_instance(seed)

    pool_size = 100
    accounts_pool, devices_pool, merchants_pool = seed_pools(faker, pool_size=pool_size)

    conn = connect()
    try:
        ensure_schema_and_tables(conn)

        # ensure dimensions exist (idempotent)
        upsert_dimensions(conn, accounts_pool, devices_pool, merchants_pool)

        # compute starting balances from historical data
        account_ids = [a['account_id'] for a in accounts_pool]
        balances = get_latest_balances(conn, account_ids, target_date)

        # idempotency: remove any existing transactions on this date
        deleted = delete_existing_transactions_for_date(conn, target_date)
        print(f"Deleted {deleted} pre-existing transactions for {target_date}")

        # On ODD days: also purge the previous EVEN day's corrupted data
        # so that GX Core validates a clean table and passes.
        # This simulates a production remediation workflow where corrupted
        # batches are rolled back before the next clean batch is ingested.
        is_even_day = target_date.day % 2 == 0
        if not is_even_day:
            from datetime import timedelta as td
            prev_day = target_date - td(days=1)
            if prev_day.day % 2 == 0:  # previous day was even (corrupted)
                purged = delete_existing_transactions_for_date(conn, prev_day)
                print(f"  🧹 Purged {purged} corrupted rows from previous even day ({prev_day})")

        n_tx = random.randint(args.min, args.max)
        tx_rows = generate_transactions_for_date(faker, accounts_pool, devices_pool, merchants_pool, balances, target_date, n_tx)

        insert_transactions(conn, tx_rows)
        print(f"Inserted {len(tx_rows)} transactions for {target_date}")

    finally:
        conn.close()


if __name__ == '__main__':
    main()
