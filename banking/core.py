"""Core banking module: SQLite persistence, accounts, transfers, interest.

Standard library only. Demo only: no real people, no real money, and no
real account numbers. Account numbers are generated locally, are unique
within this database, and are prefixed ``DEMO-`` so they are never
mistaken for real account numbers.

Money handling
--------------
Amounts passed to the public API are decimal dollars (e.g. ``100.50``).
They are stored internally as integer cents to avoid floating-point
rounding errors, and returned to callers as floats rounded to 2 places.

Public API (``banking.core.Bank``)
---------------------------------
- ``create_customer(name, email)``
- ``create_account(customer_id, account_type, initial_balance=0)``
- ``deposit(account_id, amount, description="")``
- ``withdraw(account_id, amount, description="")``
- ``transfer(from_id, to_id, amount, description="")``
- ``get_balance(account_id)``
- ``get_account(account_id)``
- ``transaction_history(account_id, limit=None)``
- ``accrue_interest(account_id=None)``
- ``monthly_statement(account_id, year, month)``

Errors: missing customers/accounts raise ``LookupError``; invalid
amounts, invalid account types, insufficient funds, transfers to the
same account, interest on a non-savings account, and operations on a
closed account raise ``ValueError``.

Transaction types recorded: ``opening``, ``deposit``, ``withdrawal``,
``transfer_in``, ``transfer_out``, ``interest``. Credits (in) are
``opening``, ``deposit``, ``transfer_in`` and ``interest``; debits
(out) are ``withdrawal`` and ``transfer_out``.

``transaction_history`` returns transactions in chronological order.
When ``limit`` is given it returns the most recent ``limit``
transactions, still in chronological order.

``accrue_interest`` always returns a list of the interest transaction
dicts it recorded (empty when nothing was due). With no ``account_id``
it accrues for every open savings account; with an ``account_id`` it
accrues for that account only, which must be an open savings account.
The monthly amount is ``balance * annual_rate / 12``, rounded to the
nearest cent; no transaction is recorded when the result is zero.
"""

from __future__ import annotations

import secrets
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

__all__ = ["Bank"]

ACCOUNT_TYPES = ("checking", "savings")
_CREDIT_TYPES = ("opening", "deposit", "transfer_in", "interest")
_DEBIT_TYPES = ("withdrawal", "transfer_out")
_CENT = Decimal("0.01")


def _to_cents(amount) -> int:
    """Convert a dollar amount to integer cents, rejecting bad input."""
    if isinstance(amount, bool) or amount is None:
        raise ValueError("amount must be a positive number")
    try:
        value = Decimal(str(amount))
    except Exception as exc:  # non-numeric input, e.g. a string of text
        raise ValueError("amount must be a positive number") from exc
    if not value.is_finite() or value <= 0:
        raise ValueError("amount must be positive")
    return int((value.quantize(_CENT, rounding=ROUND_HALF_UP)) * 100)


def _to_dollars(cents: int) -> float:
    return round(cents / 100, 2)


def _now_iso() -> str:
    # UTC, second precision; ordering ties are broken by transaction id.
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Bank:
    """A small demo bank backed by SQLite.

    Parameters
    ----------
    db_path:
        Path to the SQLite file, or ``":memory:"`` for an in-memory
        database (used by the tests). Defaults to ``"bank.db"``.
    annual_savings_rate:
        Annual interest rate for savings accounts, as a fraction
        (``0.02`` means 2% per year). Monthly accrual divides by 12.
    """

    def __init__(self, db_path: str = "bank.db", annual_savings_rate: float = 0.02):
        if annual_savings_rate is None or float(annual_savings_rate) < 0:
            raise ValueError("annual_savings_rate must be non-negative")
        self.db_path = db_path
        self.annual_savings_rate = float(annual_savings_rate)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._create_tables()

    # -- schema ---------------------------------------------------------
    def _create_tables(self) -> None:
        with self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS customers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_id INTEGER NOT NULL REFERENCES customers(id),
                    account_type TEXT NOT NULL,
                    account_number TEXT NOT NULL UNIQUE,
                    balance_cents INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'open',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id INTEGER NOT NULL REFERENCES accounts(id),
                    type TEXT NOT NULL,
                    amount_cents INTEGER NOT NULL,
                    balance_after_cents INTEGER NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    timestamp TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_transactions_account
                    ON transactions(account_id, timestamp, id);
                """
            )

    # -- helpers --------------------------------------------------------
    def _get_account_row(self, account_id: int) -> sqlite3.Row:
        row = self._conn.execute(
            "SELECT * FROM accounts WHERE id = ?", (account_id,)
        ).fetchone()
        if row is None:
            raise LookupError(f"account not found: {account_id!r}")
        return row

    @staticmethod
    def _require_open(row: sqlite3.Row) -> None:
        if row["status"] != "open":
            raise ValueError(f"account {row['id']} is closed")

    def _record(self, account_id: int, txn_type: str, amount_cents: int,
                balance_cents: int, description: str) -> dict:
        cur = self._conn.execute(
            """
            INSERT INTO transactions
                (account_id, type, amount_cents, balance_after_cents,
                 description, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (account_id, txn_type, amount_cents, balance_cents,
             description, _now_iso()),
        )
        return self._txn_dict(self._conn.execute(
            "SELECT * FROM transactions WHERE id = ?", (cur.lastrowid,)
        ).fetchone())

    @staticmethod
    def _txn_dict(row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "account_id": row["account_id"],
            "type": row["type"],
            "amount": _to_dollars(row["amount_cents"]),
            "balance_after": _to_dollars(row["balance_after_cents"]),
            "description": row["description"],
            "timestamp": row["timestamp"],
        }

    @staticmethod
    def _account_dict(row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "customer_id": row["customer_id"],
            "account_type": row["account_type"],
            "account_number": row["account_number"],
            "balance": _to_dollars(row["balance_cents"]),
            "status": row["status"],
            "created_at": row["created_at"],
        }

    def _generate_account_number(self) -> str:
        # Demo-only identifier: DEMO- + 10 random digits, unique in this DB.
        for _ in range(100):
            number = f"DEMO-{secrets.randbelow(10 ** 10):010d}"
            exists = self._conn.execute(
                "SELECT 1 FROM accounts WHERE account_number = ?", (number,)
            ).fetchone()
            if exists is None:
                return number
        raise RuntimeError("could not generate a unique demo account number")

    # -- customers ------------------------------------------------------
    def create_customer(self, name: str, email: str) -> dict:
        if not name or not str(name).strip():
            raise ValueError("customer name must not be empty")
        if not email or not str(email).strip():
            raise ValueError("customer email must not be empty")
        with self._conn:
            cur = self._conn.execute(
                "INSERT INTO customers (name, email, created_at) VALUES (?, ?, ?)",
                (str(name).strip(), str(email).strip(), _now_iso()),
            )
            row = self._conn.execute(
                "SELECT * FROM customers WHERE id = ?", (cur.lastrowid,)
            ).fetchone()
        return {"id": row["id"], "name": row["name"], "email": row["email"],
                "created_at": row["created_at"]}

    # -- accounts -------------------------------------------------------
    def create_account(self, customer_id: int, account_type: str,
                       initial_balance=0) -> dict:
        if account_type not in ACCOUNT_TYPES:
            raise ValueError(
                f"account_type must be one of {ACCOUNT_TYPES}, got {account_type!r}")
        if self._conn.execute(
                "SELECT 1 FROM customers WHERE id = ?", (customer_id,)
        ).fetchone() is None:
            raise LookupError(f"customer not found: {customer_id!r}")
        if isinstance(initial_balance, bool) or initial_balance is None:
            raise ValueError("initial_balance must be a non-negative number")
        try:
            initial = Decimal(str(initial_balance))
        except Exception as exc:
            raise ValueError("initial_balance must be a non-negative number") from exc
        if not initial.is_finite() or initial < 0:
            raise ValueError("initial_balance must be non-negative")
        initial_cents = int(
            (initial.quantize(_CENT, rounding=ROUND_HALF_UP)) * 100)
        with self._conn:
            cur = self._conn.execute(
                """
                INSERT INTO accounts
                    (customer_id, account_type, account_number,
                     balance_cents, status, created_at)
                VALUES (?, ?, ?, ?, 'open', ?)
                """,
                (customer_id, account_type, self._generate_account_number(),
                 initial_cents, _now_iso()),
            )
            account_id = cur.lastrowid
            if initial_cents > 0:
                self._record(account_id, "opening", initial_cents,
                             initial_cents, "Opening balance")
            row = self._conn.execute(
                "SELECT * FROM accounts WHERE id = ?", (account_id,)
            ).fetchone()
        return self._account_dict(row)

    def get_account(self, account_id: int) -> dict:
        return self._account_dict(self._get_account_row(account_id))

    def get_balance(self, account_id: int) -> float:
        return _to_dollars(self._get_account_row(account_id)["balance_cents"])

    def close_account(self, account_id: int) -> dict:
        """Close an account (extra helper; closed accounts reject operations)."""
        row = self._get_account_row(account_id)
        self._require_open(row)
        with self._conn:
            self._conn.execute(
                "UPDATE accounts SET status = 'closed' WHERE id = ?",
                (account_id,))
        return self.get_account(account_id)

    # -- operations -----------------------------------------------------
    def deposit(self, account_id: int, amount, description: str = "") -> dict:
        cents = _to_cents(amount)
        row = self._get_account_row(account_id)
        self._require_open(row)
        new_balance = row["balance_cents"] + cents
        with self._conn:
            self._conn.execute(
                "UPDATE accounts SET balance_cents = ? WHERE id = ?",
                (new_balance, account_id))
            return self._record(account_id, "deposit", cents, new_balance,
                                description or "")

    def withdraw(self, account_id: int, amount, description: str = "") -> dict:
        cents = _to_cents(amount)
        row = self._get_account_row(account_id)
        self._require_open(row)
        if cents > row["balance_cents"]:
            raise ValueError("insufficient funds")
        new_balance = row["balance_cents"] - cents
        with self._conn:
            self._conn.execute(
                "UPDATE accounts SET balance_cents = ? WHERE id = ?",
                (new_balance, account_id))
            return self._record(account_id, "withdrawal", cents, new_balance,
                                description or "")

    def transfer(self, from_id: int, to_id: int, amount,
                 description: str = "") -> dict:
        """Move money between two accounts atomically.

        Returns ``{"from": <transfer_out txn>, "to": <transfer_in txn>}``.
        Any failure rolls the whole transfer back, so neither balance
        changes.
        """
        if from_id == to_id:
            raise ValueError("cannot transfer to the same account")
        cents = _to_cents(amount)
        source = self._get_account_row(from_id)
        dest = self._get_account_row(to_id)
        self._require_open(source)
        self._require_open(dest)
        if cents > source["balance_cents"]:
            raise ValueError("insufficient funds")
        new_source = source["balance_cents"] - cents
        new_dest = dest["balance_cents"] + cents
        # One sqlite transaction: both updates and both records commit
        # together, or all roll back on any error.
        with self._conn:
            self._conn.execute(
                "UPDATE accounts SET balance_cents = ? WHERE id = ?",
                (new_source, from_id))
            self._conn.execute(
                "UPDATE accounts SET balance_cents = ? WHERE id = ?",
                (new_dest, to_id))
            out_txn = self._record(from_id, "transfer_out", cents, new_source,
                                   description or "")
            in_txn = self._record(to_id, "transfer_in", cents, new_dest,
                                  description or "")
        return {"from": out_txn, "to": in_txn}

    # -- history / interest / statements --------------------------------
    def transaction_history(self, account_id: int, limit=None) -> list:
        self._get_account_row(account_id)  # raises LookupError if missing
        if limit is not None:
            if isinstance(limit, bool) or int(limit) <= 0:
                raise ValueError("limit must be a positive integer")
            rows = self._conn.execute(
                """
                SELECT * FROM transactions WHERE account_id = ?
                ORDER BY timestamp DESC, id DESC LIMIT ?
                """,
                (account_id, int(limit))).fetchall()
            rows = list(reversed(rows))  # most recent N, chronological order
        else:
            rows = self._conn.execute(
                """
                SELECT * FROM transactions WHERE account_id = ?
                ORDER BY timestamp ASC, id ASC
                """,
                (account_id,)).fetchall()
        return [self._txn_dict(row) for row in rows]

    def accrue_interest(self, account_id=None) -> list:
        """Apply one month of savings interest; returns interest txns recorded."""
        if account_id is not None:
            row = self._get_account_row(account_id)
            self._require_open(row)
            if row["account_type"] != "savings":
                raise ValueError("interest applies only to savings accounts")
            targets = [row]
        else:
            targets = self._conn.execute(
                "SELECT * FROM accounts WHERE account_type = 'savings' "
                "AND status = 'open' AND balance_cents > 0"
            ).fetchall()
        recorded = []
        for target in targets:
            interest_cents = int(
                (Decimal(target["balance_cents"])
                 * Decimal(str(self.annual_savings_rate)) / Decimal(12)
                 ).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            if interest_cents <= 0:
                continue
            new_balance = target["balance_cents"] + interest_cents
            with self._conn:
                self._conn.execute(
                    "UPDATE accounts SET balance_cents = ? WHERE id = ?",
                    (new_balance, target["id"]))
                recorded.append(self._record(
                    target["id"], "interest", interest_cents, new_balance,
                    "Monthly savings interest"))
        return recorded

    def monthly_statement(self, account_id: int, year: int, month: int) -> dict:
        account = self._get_account_row(account_id)
        if not 1 <= int(month) <= 12:
            raise ValueError("month must be between 1 and 12")
        year, month = int(year), int(month)
        start = f"{year:04d}-{month:02d}-01T00:00:00"
        # Exclusive upper bound: first instant of the next month.
        if month == 12:
            end = f"{year + 1:04d}-01-01T00:00:00"
        else:
            end = f"{year:04d}-{month + 1:02d}-01T00:00:00"
        before = self._conn.execute(
            """
            SELECT balance_after_cents FROM transactions
            WHERE account_id = ? AND timestamp < ?
            ORDER BY timestamp DESC, id DESC LIMIT 1
            """,
            (account_id, start)).fetchone()
        opening_cents = before["balance_after_cents"] if before else 0
        rows = self._conn.execute(
            """
            SELECT * FROM transactions WHERE account_id = ?
            AND timestamp >= ? AND timestamp < ?
            ORDER BY timestamp ASC, id ASC
            """,
            (account_id, start, end)).fetchall()
        txns = [self._txn_dict(row) for row in rows]
        total_in = sum(row["amount_cents"] for row in rows
                       if row["type"] in _CREDIT_TYPES)
        total_out = sum(row["amount_cents"] for row in rows
                        if row["type"] in _DEBIT_TYPES)
        closing_cents = (rows[-1]["balance_after_cents"] if rows
                         else opening_cents)
        return {
            "account_id": account_id,
            "account_number": account["account_number"],
            "account_type": account["account_type"],
            "year": year,
            "month": month,
            "opening_balance": _to_dollars(opening_cents),
            "closing_balance": _to_dollars(closing_cents),
            "transactions": txns,
            "total_in": _to_dollars(total_in),
            "total_out": _to_dollars(total_out),
            "transaction_count": len(txns),
        }

    # -- lifecycle ------------------------------------------------------
    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Bank":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
