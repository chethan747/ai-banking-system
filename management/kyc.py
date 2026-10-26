"""Customer / KYC records.

DEMONSTRATION / EDUCATIONAL ONLY -- not production KYC, not
PCI-DSS / SOC 2 compliant. Demo seed data only: no real people and no
real government ID numbers.

The raw ID number is NEVER stored. ``create_customer_record`` accepts
the ``id_number_hash`` argument as specified; if the caller passes a
raw demo ID value it is hashed with SHA-256 before storage, and if the
caller already passes a 64-hex-char SHA-256 hash it is stored as-is.
Either way the stored value is a hash, never a raw ID number, and the
returned record contains no raw ID field. Use ``hash_id_number()`` to
hash an ID value explicitly.

Statuses: pending -> verified / rejected. ``reviewed_by`` may be a
username string or a user dict (``{"username": ..., "role": ...}``);
a dict reviewer must hold the ``update_kyc`` permission, otherwise
``PermissionError`` is raised.
"""

import hashlib
import re
import sqlite3
from datetime import datetime, timezone

from .auth import has_permission

KYC_STATUSES = ("pending", "verified", "rejected")
_DEFAULT_DB = "management.db"
_HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")


def hash_id_number(id_number):
    """SHA-256 hex digest of an ID value (demo data only)."""
    return hashlib.sha256(str(id_number).encode("utf-8")).hexdigest()


def _store_id_value(value):
    value = str(value)
    if _HEX64.match(value):
        return value.lower()
    return hash_id_number(value)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _reviewer_name(reviewed_by):
    if isinstance(reviewed_by, dict):
        if not has_permission(reviewed_by, "update_kyc"):
            raise PermissionError(
                "role %r may not review KYC records" % reviewed_by.get("role")
            )
        return reviewed_by.get("username")
    return reviewed_by


class CustomerStore:
    """SQLite-backed customer/KYC store (see auth.AuthStore for db_path)."""

    def __init__(self, db_path=_DEFAULT_DB):
        if isinstance(db_path, sqlite3.Connection):
            self.conn = db_path
        else:
            self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS customers (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   name TEXT NOT NULL,
                   email TEXT NOT NULL,
                   dob TEXT NOT NULL,
                   address TEXT NOT NULL,
                   id_type TEXT NOT NULL,
                   id_number_hash TEXT NOT NULL,
                   kyc_status TEXT NOT NULL DEFAULT 'pending',
                   reviewed_by TEXT,
                   reviewed_at TEXT,
                   created_at TEXT NOT NULL
               )"""
        )
        self.conn.commit()

    def create_customer_record(self, name, email, dob, address, id_type, id_number_hash):
        if not all([name, email, dob, address, id_type, id_number_hash]):
            raise ValueError("all customer fields are required")
        cur = self.conn.execute(
            "INSERT INTO customers (name, email, dob, address, id_type,"
            " id_number_hash, kyc_status, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)",
            (name, email, dob, address, id_type, _store_id_value(id_number_hash), _now()),
        )
        self.conn.commit()
        return self.get_customer_record(cur.lastrowid)

    def get_customer_record(self, customer_id):
        row = self.conn.execute(
            "SELECT * FROM customers WHERE id = ?", (customer_id,)
        ).fetchone()
        return dict(row) if row is not None else None

    def update_kyc_status(self, customer_id, status, reviewed_by):
        if status not in KYC_STATUSES:
            raise ValueError("unknown KYC status: %r (expected one of %r)" % (status, KYC_STATUSES))
        reviewer = _reviewer_name(reviewed_by)
        cur = self.conn.execute(
            "UPDATE customers SET kyc_status = ?, reviewed_by = ?, reviewed_at = ?"
            " WHERE id = ?",
            (status, reviewer, _now(), customer_id),
        )
        self.conn.commit()
        if cur.rowcount == 0:
            raise ValueError("no such customer: %r" % (customer_id,))
        return self.get_customer_record(customer_id)

    def list_customer_records(self, status=None):
        if status is not None and status not in KYC_STATUSES:
            raise ValueError("unknown KYC status: %r" % (status,))
        if status is None:
            rows = self.conn.execute("SELECT * FROM customers ORDER BY id").fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM customers WHERE kyc_status = ? ORDER BY id", (status,)
            ).fetchall()
        return [dict(r) for r in rows]

    # Alias matching the task wording ("listing by status").
    def list_by_status(self, status):
        return self.list_customer_records(status=status)


def _store(db_path, store):
    if store is not None:
        return store
    return CustomerStore(db_path if db_path is not None else _DEFAULT_DB)


def create_customer_record(name, email, dob, address, id_type, id_number_hash,
                           db_path=None, store=None):
    return _store(db_path, store).create_customer_record(
        name, email, dob, address, id_type, id_number_hash)


def get_customer_record(customer_id, db_path=None, store=None):
    return _store(db_path, store).get_customer_record(customer_id)


def update_kyc_status(customer_id, status, reviewed_by, db_path=None, store=None):
    return _store(db_path, store).update_kyc_status(customer_id, status, reviewed_by)


def list_customer_records(status=None, db_path=None, store=None):
    return _store(db_path, store).list_customer_records(status=status)
