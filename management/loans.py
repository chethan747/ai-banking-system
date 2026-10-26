"""Loan applications with a manager-approval workflow.

DEMONSTRATION / EDUCATIONAL ONLY -- not production lending, no real
money, no real credit decisions, not PCI-DSS / SOC 2 compliant.

Lifecycle: pending -> approved | rejected (terminal). An approved or
rejected loan cannot be re-reviewed (``ValueError``). Review is
allowed only for manager/admin roles: ``review_loan`` takes the
reviewer *user dict* (``{"username": ..., "role": ...}``) and raises
``PermissionError`` for any other role, including teller and customer.
The reviewer username, decision note and timestamp are recorded.
"""

import sqlite3
from datetime import datetime, timezone

from .auth import has_permission

_DEFAULT_DB = "management.db"
_DECISIONS = {"approve": "approved", "approved": "approved",
              "reject": "rejected", "rejected": "rejected"}


def _now():
    return datetime.now(timezone.utc).isoformat()


class LoanStore:
    """SQLite-backed loan store (see auth.AuthStore for db_path)."""

    def __init__(self, db_path=_DEFAULT_DB):
        if isinstance(db_path, sqlite3.Connection):
            self.conn = db_path
        else:
            self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS loans (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   customer_id INTEGER NOT NULL,
                   amount REAL NOT NULL,
                   purpose TEXT NOT NULL,
                   term_months INTEGER NOT NULL,
                   credit_score INTEGER,
                   status TEXT NOT NULL DEFAULT 'pending',
                   reviewer TEXT,
                   note TEXT,
                   created_at TEXT NOT NULL,
                   reviewed_at TEXT
               )"""
        )
        self.conn.commit()

    def apply_loan(self, customer_id, amount, purpose, term_months, credit_score=None):
        if amount is None or float(amount) <= 0:
            raise ValueError("loan amount must be positive")
        if term_months is None or int(term_months) <= 0:
            raise ValueError("term_months must be positive")
        if credit_score is not None and not (300 <= int(credit_score) <= 850):
            raise ValueError("credit_score must be between 300 and 850")
        if not purpose:
            raise ValueError("purpose is required")
        cur = self.conn.execute(
            "INSERT INTO loans (customer_id, amount, purpose, term_months,"
            " credit_score, status, created_at) VALUES (?, ?, ?, ?, ?, 'pending', ?)",
            (customer_id, float(amount), purpose, int(term_months),
             None if credit_score is None else int(credit_score), _now()),
        )
        self.conn.commit()
        return self.get_loan(cur.lastrowid)

    def review_loan(self, loan_id, reviewer, decision, note=None):
        """Review a pending loan. ``reviewer`` is a user dict.

        Raises PermissionError for non-manager/admin reviewers and
        ValueError for unknown loans, unknown decisions, or loans that
        are no longer pending (double review).
        """
        if not isinstance(reviewer, dict) or not has_permission(reviewer, "review_loan"):
            role = reviewer.get("role") if isinstance(reviewer, dict) else None
            raise PermissionError(
                "role %r may not review loans (manager/admin only)" % role
            )
        key = str(decision).lower()
        if key not in _DECISIONS:
            raise ValueError("decision must be 'approve' or 'reject', got %r" % (decision,))
        loan = self.get_loan(loan_id)
        if loan is None:
            raise ValueError("no such loan: %r" % (loan_id,))
        if loan["status"] != "pending":
            raise ValueError(
                "loan %r is already %s and cannot be re-reviewed" % (loan_id, loan["status"])
            )
        self.conn.execute(
            "UPDATE loans SET status = ?, reviewer = ?, note = ?, reviewed_at = ?"
            " WHERE id = ?",
            (_DECISIONS[key], reviewer.get("username"), note, _now(), loan_id),
        )
        self.conn.commit()
        return self.get_loan(loan_id)

    def get_loan(self, loan_id):
        row = self.conn.execute(
            "SELECT * FROM loans WHERE id = ?", (loan_id,)
        ).fetchone()
        return dict(row) if row is not None else None

    def list_loans(self, status=None):
        if status is None:
            rows = self.conn.execute("SELECT * FROM loans ORDER BY id").fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM loans WHERE status = ? ORDER BY id", (status,)
            ).fetchall()
        return [dict(r) for r in rows]


def _store(db_path, store):
    if store is not None:
        return store
    return LoanStore(db_path if db_path is not None else _DEFAULT_DB)


def apply_loan(customer_id, amount, purpose, term_months, credit_score=None,
               db_path=None, store=None):
    return _store(db_path, store).apply_loan(
        customer_id, amount, purpose, term_months, credit_score)


def review_loan(loan_id, reviewer, decision, note=None, db_path=None, store=None):
    return _store(db_path, store).review_loan(loan_id, reviewer, decision, note)


def get_loan(loan_id, db_path=None, store=None):
    return _store(db_path, store).get_loan(loan_id)


def list_loans(status=None, db_path=None, store=None):
    return _store(db_path, store).list_loans(status=status)
