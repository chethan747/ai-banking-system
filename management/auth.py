"""Role-based access control with salted PBKDF2 password hashing.

DEMONSTRATION / EDUCATIONAL ONLY -- not a production authentication
system, not PCI-DSS / SOC 2 compliant. No real users, passwords, or
money. Passwords are NEVER stored in plaintext: each user gets a fresh
random salt and a PBKDF2-HMAC-SHA256 hash, stored as
``pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>``.

Roles: customer, teller, manager, admin.

Permission table (enforced by ``has_permission`` and, for loans, at
function level in ``loans.review_loan``):
  - only manager/admin approve (review) loans
  - only admin manage users
  - teller/manager/admin can view/create customers
  - customer can view own records only (never all records, never users)

Persistence: SQLite, parameterised db path (default ``management.db``).
For isolated tests use ``AuthStore(":memory:")`` (one persistent
connection) rather than the module-level functions with ``":memory:"``,
because a fresh ``:memory:`` connection is empty on every open.
The module-level functions accept ``db_path`` and/or ``store`` kwargs
so a file-backed path persists across calls.
"""

import hashlib
import hmac
import os
import sqlite3

ROLES = ("customer", "teller", "manager", "admin")

# Action -> roles allowed. Aliases are included so callers using a
# synonymous action name get the same policy.
PERMISSIONS = {
    "view_own_records": {"customer", "teller", "manager", "admin"},
    "view_customers": {"teller", "manager", "admin"},
    "view_all_records": {"teller", "manager", "admin"},
    "create_customer": {"teller", "manager", "admin"},
    "update_customer": {"teller", "manager", "admin"},
    "update_kyc": {"teller", "manager", "admin"},
    "review_kyc": {"teller", "manager", "admin"},
    "apply_loan": {"customer", "teller", "manager", "admin"},
    "review_loan": {"manager", "admin"},
    "approve_loans": {"manager", "admin"},
    "approve_loan": {"manager", "admin"},
    "manage_users": {"admin"},
    "create_user": {"admin"},
    "view_reports": {"manager", "admin"},
    "view_audit_log": {"manager", "admin"},
}

_DEFAULT_DB = "management.db"
_ITERATIONS = 200_000


def _hash_password(password):
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return "pbkdf2_sha256$%d$%s$%s" % (_ITERATIONS, salt.hex(), digest.hex())


def _check_password(password, stored):
    try:
        _algo, iterations, salt_hex, hash_hex = stored.split("$")
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
        )
        return hmac.compare_digest(digest.hex(), hash_hex)
    except (ValueError, TypeError):
        return False


def _role_of(user):
    """Accept a user dict (``{"role": ...}``) or a bare role string."""
    if isinstance(user, dict):
        return user.get("role")
    return user


def has_permission(user, action):
    """Return True iff ``user``'s role may perform ``action``.

    Unknown users, unknown roles and unknown actions are denied.
    A customer is never granted all-records / user-management actions:
    they may only view their own records.
    """
    allowed = PERMISSIONS.get(action)
    if allowed is None:
        return False
    return _role_of(user) in allowed


class AuthStore:
    """SQLite-backed user store. ``db_path`` may be a file path, a
    ``sqlite3.Connection``, or ``":memory:"`` for isolated tests."""

    def __init__(self, db_path=_DEFAULT_DB):
        if isinstance(db_path, sqlite3.Connection):
            self.conn = db_path
        else:
            self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS users (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   username TEXT UNIQUE NOT NULL,
                   password_hash TEXT NOT NULL,
                   role TEXT NOT NULL,
                   customer_id INTEGER
               )"""
        )
        self.conn.commit()

    def create_user(self, username, password, role, customer_id=None):
        if role not in ROLES:
            raise ValueError("unknown role: %r (expected one of %r)" % (role, ROLES))
        if not username or not password:
            raise ValueError("username and password must be non-empty")
        try:
            cur = self.conn.execute(
                "INSERT INTO users (username, password_hash, role, customer_id)"
                " VALUES (?, ?, ?, ?)",
                (username, _hash_password(password), role, customer_id),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("username already exists: %r" % username) from exc
        self.conn.commit()
        return self._public(cur.lastrowid)

    def verify_user(self, username, password):
        """Return the public user dict on a correct password, else None.

        The returned dict never contains a password or password hash.
        """
        row = self.conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        if row is None or not _check_password(password, row["password_hash"]):
            return None
        return self._public(row["id"])

    def get_user(self, username):
        row = self.conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        return self._public(row["id"]) if row is not None else None

    def _public(self, user_id):
        row = self.conn.execute(
            "SELECT id, username, role, customer_id FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "username": row["username"],
            "role": row["role"],
            "customer_id": row["customer_id"],
        }

    def raw_password_hash(self, username):
        """Test/diagnostic helper: returns the stored hash string.

        Used by tests to prove no plaintext is stored. Not part of the
        public user dict returned by create/verify.
        """
        row = self.conn.execute(
            "SELECT password_hash FROM users WHERE username = ?", (username,)
        ).fetchone()
        return row["password_hash"] if row is not None else None


def _store(db_path, store):
    if store is not None:
        return store
    return AuthStore(db_path if db_path is not None else _DEFAULT_DB)


def create_user(username, password, role, customer_id=None, db_path=None, store=None):
    return _store(db_path, store).create_user(username, password, role, customer_id)


def verify_user(username, password, db_path=None, store=None):
    return _store(db_path, store).verify_user(username, password)
