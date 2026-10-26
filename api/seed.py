"""Demo seed data for Module 4.

DEMO / EDUCATIONAL ONLY: all customers, accounts and transactions are
fictitious. No real people, no real money, no real account numbers.
Passwords are created only through management.auth (PBKDF2 hashing);
they are never stored or returned in plaintext.

Seed runs only when the bank database has no accounts yet (see run.py).
It is idempotent in that sense: calling it on a non-empty database is
a no-op returning False.
"""

from __future__ import annotations

import time


def list_bank_accounts(bank):
    """Read accounts straight from the bank SQLite file (read-only)."""
    import sqlite3

    conn = sqlite3.connect(bank.db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT id, customer_id, account_type, account_number,"
            " balance_cents, status, created_at FROM accounts ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def seed_data(state):
    """Seed demo data into an empty state. Returns True if seeded."""
    bank = state.bank
    if list_bank_accounts(bank):
        return False

    # --- Fictitious demo customers -----------------------------------
    ava = bank.create_customer("Ava Demo", "ava.demo@example.test")
    ben = bank.create_customer("Ben Demo", "ben.demo@example.test")
    cara = bank.create_customer("Cara Demo", "cara.demo@example.test")

    # --- Accounts -----------------------------------------------------
    ava_checking = bank.create_account(ava["id"], "checking", 1000)
    ava_savings = bank.create_account(ava["id"], "savings", 4800)
    ben_checking = bank.create_account(ben["id"], "checking", 850)
    ben_savings = bank.create_account(ben["id"], "savings", 1200)
    cara_checking = bank.create_account(cara["id"], "checking", 600)

    # --- Ava checking: ordinary history, then one large unusual txn --
    # The large withdrawal is flagged by fraud review: it is many times
    # Ava's typical amount AND follows 10+ transactions within an hour
    # (seed transactions all happen within minutes of each other).
    bank.deposit(ava_checking["id"], 3500, "Salary payroll")
    bank.deposit(ava_checking["id"], 6000, "Demo project bonus")
    for amount, desc in [
        (45, "Supermarket groceries"),
        (6, "Starbucks coffee"),
        (15, "Netflix streaming"),
        (22, "Uber ride"),
        (80, "Supermarket groceries weekly"),
        (120, "Electric bill utilities"),
        (35, "Restaurant dining"),
        (60, "Supermarket groceries"),
        (18, "Coffee cafe"),
        (25, "Bus fare transport"),
        (40, "Cinema entertainment"),
    ]:
        # Bank timestamps have second precision and the velocity rule
        # only counts prior transactions with a >0 gap, so space each
        # seed transaction by just over a second. This keeps the demo
        # deterministic: the large withdrawal below then scores
        # large-amount (45) + high velocity (35) = 80, i.e. flagged.
        time.sleep(1.1)
        bank.withdraw(ava_checking["id"], amount, desc)
    time.sleep(1.1)
    bank.withdraw(ava_checking["id"], 8500, "Unusual large withdrawal")

    # --- Ben / Cara: ordinary history --------------------------------
    bank.deposit(ben_checking["id"], 1800, "Salary payroll")
    bank.withdraw(ben_checking["id"], 55, "Supermarket groceries")
    bank.withdraw(ben_checking["id"], 12, "Coffee cafe")
    bank.withdraw(ben_checking["id"], 30, "Uber ride")
    bank.deposit(cara_checking["id"], 900, "Salary payroll")
    bank.withdraw(cara_checking["id"], 70, "Supermarket groceries")
    bank.withdraw(cara_checking["id"], 20, "Restaurant dining")
    bank.transfer(ava_savings["id"], ben_savings["id"], 200, "Demo savings transfer")

    # --- Demo users (PBKDF2 via management.auth, never plaintext) ----
    state.auth.create_user("admin", "admin123", "admin")
    manager = state.auth.create_user("manager", "manager123", "manager")
    state.auth.create_user("teller", "teller123", "teller")
    state.auth.create_user("customer", "customer123", "customer",
                           customer_id=ava["id"])

    # --- KYC records (raw demo IDs are SHA-256 hashed by the store) --
    ava_kyc = state.kyc.create_customer_record(
        "Ava Demo", "ava.demo@example.test", "1990-05-01",
        "1 Demo Street, Demo City", "passport", "DEMO-ID-AVA-001")
    state.kyc.update_kyc_status(ava_kyc["id"], "verified", "manager")
    state.kyc.create_customer_record(
        "Ben Demo", "ben.demo@example.test", "1992-08-14",
        "2 Demo Street, Demo City", "passport", "DEMO-ID-BEN-002")

    # --- Loans: one approved, two pending ----------------------------
    approved = state.loans.apply_loan(ava["id"], 12000, "Demo home repair",
                                      36, credit_score=710)
    state.loans.review_loan(approved["id"], manager, "approve",
                            "Demo approval by manager")
    state.loans.apply_loan(ben["id"], 8000, "Demo home repair", 36,
                           credit_score=710)
    state.loans.apply_loan(cara["id"], 3000, "Demo car repair", 24,
                           credit_score=680)

    state.audit.append_event("system", "demo_seed",
                             {"customers": 3, "accounts": 5, "loans": 3})
    return True
