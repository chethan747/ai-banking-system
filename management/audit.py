"""Append-only audit log with hash-chaining.

DEMONSTRATION / EDUCATIONAL ONLY -- not a production audit/compliance
system, not PCI-DSS / SOC 2 compliant. Hash-chaining makes *tampering
detectable* (``verify_chain`` fails), it does not make the log
tamper-proof: anyone with write access to the SQLite file can rewrite
the whole chain. A production system would need append-only storage,
signing, and independent retention.

Each entry stores ``previous_hash`` and its own SHA-256 ``hash`` over
``prev_hash + actor + action + details + timestamp`` (details are
serialised deterministically: dicts as sorted-key JSON, anything else
as ``str()``). The genesis entry's previous hash is 64 zeroes.
No update/delete API is provided on purpose.

``verify_chain()`` returns ``(True, None)`` when every entry's stored
hash matches a recomputation and every ``previous_hash`` links to the
prior entry's hash; otherwise ``(False, first_bad_index)`` where the
index is the 0-based position in chronological (id) order.
"""

import hashlib
import json
import sqlite3
from datetime import datetime, timezone

_DEFAULT_DB = "management.db"
_GENESIS = "0" * 64


def _serialise_details(details):
    if isinstance(details, dict):
        return json.dumps(details, sort_keys=True, default=str)
    return str(details)


def _entry_hash(prev_hash, actor, action, details_text, timestamp):
    payload = prev_hash + str(actor) + str(action) + details_text + timestamp
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _now():
    return datetime.now(timezone.utc).isoformat()


class AuditLog:
    """SQLite-backed audit log (see auth.AuthStore for db_path).

    ``append_event`` / ``verify_chain`` / ``list_events`` are the
    primary API; the module-level functions below wrap a file-backed
    log for convenience.
    """

    def __init__(self, db_path=_DEFAULT_DB):
        if isinstance(db_path, sqlite3.Connection):
            self.conn = db_path
        else:
            self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS audit_log (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   actor TEXT NOT NULL,
                   action TEXT NOT NULL,
                   details TEXT NOT NULL,
                   timestamp TEXT NOT NULL,
                   previous_hash TEXT NOT NULL,
                   hash TEXT NOT NULL
               )"""
        )
        self.conn.commit()

    def append_event(self, actor, action, details):
        details_text = _serialise_details(details)
        last = self.conn.execute(
            "SELECT hash FROM audit_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
        prev_hash = last["hash"] if last is not None else _GENESIS
        timestamp = _now()
        entry_hash = _entry_hash(prev_hash, actor, action, details_text, timestamp)
        cur = self.conn.execute(
            "INSERT INTO audit_log (actor, action, details, timestamp,"
            " previous_hash, hash) VALUES (?, ?, ?, ?, ?, ?)",
            (actor, action, details_text, timestamp, prev_hash, entry_hash),
        )
        self.conn.commit()
        return self._entry(cur.lastrowid)

    def list_events(self):
        rows = self.conn.execute("SELECT * FROM audit_log ORDER BY id").fetchall()
        return [dict(r) for r in rows]

    def verify_chain(self):
        """Return (ok, first_bad_index_or_None), 0-based in id order."""
        entries = self.list_events()
        expected_prev = _GENESIS
        for index, entry in enumerate(entries):
            if entry["previous_hash"] != expected_prev:
                return (False, index)
            recomputed = _entry_hash(
                entry["previous_hash"], entry["actor"], entry["action"],
                entry["details"], entry["timestamp"],
            )
            if recomputed != entry["hash"]:
                return (False, index)
            expected_prev = entry["hash"]
        return (True, None)

    def _entry(self, entry_id):
        row = self.conn.execute(
            "SELECT * FROM audit_log WHERE id = ?", (entry_id,)
        ).fetchone()
        return dict(row) if row is not None else None


def _log(db_path, store):
    if store is not None:
        return store
    return AuditLog(db_path if db_path is not None else _DEFAULT_DB)


def append_event(actor, action, details, db_path=None, store=None):
    return _log(db_path, store).append_event(actor, action, details)


def verify_chain(db_path=None, store=None):
    return _log(db_path, store).verify_chain()
