"""Module 4 backend API + static frontend server (stdlib only).

DEMO / EDUCATIONAL ONLY: not production banking software, not
PCI-DSS / SOC 2 compliant. AI fraud/credit scores are illustrative
only, not regulated decisions. No real people, no real money.

Local-first: all paths are relative to the project root (the parent
of this file). No absolute paths are hardcoded. Compatible with
Python 3.10+.

Run via run.py at the project root (which seeds demo data first),
or import build_state / make_server for tests.

Audit logging on actions: login, account creation, deposit,
withdrawal, transfer, KYC creation, loan application and loan review
are all appended to the management AuditLog with actor = the
authenticated username and details containing only IDs/amounts
(never passwords or hashes). GET /api/audit returns those events.

Auth: POST /api/login verifies via management.auth (PBKDF2) and
returns a bearer token (secrets.token_hex) held only in server
memory, plus username/role -- never a password or hash. Every other
endpoint requires `Authorization: Bearer <token>`.

The server uses http.server.HTTPServer (single-threaded) on purpose:
the banking SQLite connection is used only from the serving thread,
which keeps the stdlib sqlite connection thread-safe without extra
dependencies.
"""

from __future__ import annotations

import json
import secrets
import sqlite3
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai_engine.assistant import answer_question
from ai_engine.credit import credit_score
from ai_engine.fraud import review_queue, score_transaction
from ai_engine.insights import spending_insights
from banking.core import Bank
from management.audit import AuditLog
from management.auth import AuthStore, has_permission
from management.kyc import CustomerStore
from management.loans import LoanStore
from management.reports import (
    flagged_report,
    loan_pipeline_report,
    totals_report,
)

WEB_DIR = ROOT / "web"
DEMO_BANNER = "DEMO / EDUCATIONAL ONLY - not a real bank"


class AppState:
    """One shared Bank + one set of management stores per server."""

    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.bank = Bank(str(self.data_dir / "bank.db"),
                         annual_savings_rate=0.02)
        mgmt = str(self.data_dir / "management.db")
        self.auth = AuthStore(mgmt)
        self.loans = LoanStore(mgmt)
        self.kyc = CustomerStore(mgmt)
        self.audit = AuditLog(mgmt)
        self.tokens = {}  # token -> public user dict


def build_state(data_dir):
    return AppState(data_dir)


# ---------------------------------------------------------------- helpers
def _all_accounts(state):
    conn = sqlite3.connect(state.bank.db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT a.*, c.name AS customer_name, c.email AS customer_email"
            " FROM accounts a JOIN customers c ON c.id = a.customer_id"
            " ORDER BY a.id"
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["balance"] = round(d.pop("balance_cents") / 100, 2)
            out.append(d)
        return out
    finally:
        conn.close()


def _all_transactions(state, account_ids=None):
    conn = sqlite3.connect(state.bank.db_path)
    conn.row_factory = sqlite3.Row
    try:
        if account_ids is not None:
            if not account_ids:
                return []
            marks = ",".join("?" for _ in account_ids)
            rows = conn.execute(
                "SELECT * FROM transactions WHERE account_id IN (%s)"
                " ORDER BY timestamp ASC, id ASC" % marks,
                tuple(account_ids)).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM transactions ORDER BY timestamp ASC, id ASC"
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["amount"] = round(d.pop("amount_cents") / 100, 2)
            d["balance_after"] = round(d.pop("balance_after_cents") / 100, 2)
            out.append(d)
        return out
    finally:
        conn.close()


def _visible_account_ids(state, user):
    accounts = _all_accounts(state)
    if user["role"] == "customer" and user.get("customer_id") is not None:
        accounts = [a for a in accounts
                    if a["customer_id"] == user["customer_id"]]
    return accounts


def _check_account_visible(state, user, account_id):
    acct = state.bank.get_account(account_id)  # LookupError if missing
    if user["role"] == "customer" and user.get("customer_id") is not None:
        if acct["customer_id"] != user["customer_id"]:
            raise PermissionError("customers may only access their own accounts")
    return acct


def _fraud_review(state, user):
    accounts = _visible_account_ids(state, user)
    ids = [a["id"] for a in accounts]
    txns = _all_transactions(state, ids)
    by_account = {}
    for t in txns:
        by_account.setdefault(t["account_id"], []).append(t)
    flagged = []
    for account_id, account_txns in by_account.items():
        for i, txn in enumerate(account_txns):
            score, is_flagged, reasons = score_transaction(
                txn, account_txns[:i])
            if is_flagged:
                flagged.append({"transaction": txn, "score": score,
                                "flagged": True, "reasons": reasons})
    return flagged


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def _require_manager_or_admin(user):
    if user["role"] not in ("manager", "admin"):
        raise ApiError(403, "manager/admin only")


# ---------------------------------------------------------------- handler
class Handler(BaseHTTPRequestHandler):
    state = None  # set on the server object; accessed via self.server.state

    def log_message(self, *args):  # keep stdout clean
        pass

    # -- plumbing ------------------------------------------------------
    @property
    def _state(self):
        return self.server.state

    def _send_json(self, status, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path, content_type):
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            value = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise ApiError(400, "request body must be valid JSON")
        if not isinstance(value, dict):
            raise ApiError(400, "request body must be a JSON object")
        return value

    def _auth_user(self):
        auth = self.headers.get("Authorization") or ""
        if not auth.startswith("Bearer "):
            raise ApiError(401, "missing or invalid bearer token")
        user = self._state.tokens.get(auth[7:].strip())
        if user is None:
            raise ApiError(401, "missing or invalid bearer token")
        return user

    # -- routing -------------------------------------------------------
    def do_GET(self):
        self._dispatch()

    def do_POST(self):
        self._dispatch()

    def _dispatch(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        try:
            if path == "/" or path.startswith("/app.js") or \
                    path.startswith("/style.css") or path == "/index.html":
                self._serve_static(path)
                return
            if not path.startswith("/api/"):
                raise ApiError(404, "not found")
            if path == "/api/login" and self.command == "POST":
                self._login()
                return
            user = self._auth_user()
            self._route_api(path, query, user)
        except ApiError as exc:
            self._send_json(exc.status, {"error": exc.message})
        except LookupError as exc:
            self._send_json(404, {"error": str(exc)})
        except PermissionError as exc:
            self._send_json(403, {"error": str(exc)})
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
        except Exception as exc:  # never leak a stack trace as HTML
            self._send_json(500, {"error": "internal error: %s" % exc})

    def _serve_static(self, path):
        mapping = {"/": ("index.html", "text/html"),
                   "/index.html": ("index.html", "text/html"),
                   "/app.js": ("app.js", "application/javascript"),
                   "/style.css": ("style.css", "text/css")}
        name, ctype = mapping.get(path, (None, None))
        if name is None:
            raise ApiError(404, "not found")
        target = (WEB_DIR / name).resolve()
        if WEB_DIR.resolve() not in target.parents and target != WEB_DIR.resolve():
            raise ApiError(404, "not found")
        if not target.exists():
            raise ApiError(404, "frontend file not found: %s" % name)
        self._send_file(target, ctype)

    # -- auth ----------------------------------------------------------
    def _login(self):
        body = self._read_json()
        username = body.get("username")
        password = body.get("password")
        if not username or not password:
            raise ApiError(400, "username and password are required")
        user = self._state.auth.verify_user(username, password)
        if user is None:
            raise ApiError(401, "invalid username or password")
        token = secrets.token_hex(32)
        self._state.tokens[token] = user
        self._state.audit.append_event(user["username"], "login",
                                       {"username": user["username"]})
        self._send_json(200, {"token": token, "username": user["username"],
                              "role": user["role"],
                              "customer_id": user.get("customer_id"),
                              "demo_notice": DEMO_BANNER})

    # -- API routes ----------------------------------------------------
    def _route_api(self, path, query, user):
        state = self._state
        method = self.command
        parts = [p for p in path.split("/") if p]

        def q(name, default=None):
            values = query.get(name)
            return values[0] if values else default

        # Accounts
        if parts == ["api", "accounts"] and method == "GET":
            self._send_json(200, {"accounts": _visible_account_ids(state, user)})
            return
        if parts == ["api", "accounts"] and method == "POST":
            body = self._read_json()
            customer_id = body.get("customer_id")
            if user["role"] == "customer":
                if user.get("customer_id") is None:
                    raise ApiError(400, "customer account has no linked customer")
                customer_id = user["customer_id"]
            if customer_id is None:
                raise ApiError(400, "customer_id is required")
            acct = state.bank.create_account(
                int(customer_id), body.get("account_type"),
                body.get("initial_balance", 0))
            state.audit.append_event(user["username"], "account_created",
                                     {"account_id": acct["id"],
                                      "customer_id": acct["customer_id"],
                                      "account_type": acct["account_type"]})
            self._send_json(201, acct)
            return
        if len(parts) == 4 and parts[1] == "accounts" and parts[3] == "deposit" \
                and method == "POST":
            account_id = int(parts[2])
            _check_account_visible(state, user, account_id)
            body = self._read_json()
            txn = state.bank.deposit(account_id, body.get("amount"),
                                     body.get("description", ""))
            state.audit.append_event(user["username"], "deposit",
                                     {"account_id": account_id,
                                      "amount": txn["amount"],
                                      "transaction_id": txn["id"]})
            self._send_json(200, txn)
            return
        if len(parts) == 4 and parts[1] == "accounts" and parts[3] == "withdraw" \
                and method == "POST":
            account_id = int(parts[2])
            _check_account_visible(state, user, account_id)
            body = self._read_json()
            txn = state.bank.withdraw(account_id, body.get("amount"),
                                      body.get("description", ""))
            state.audit.append_event(user["username"], "withdrawal",
                                     {"account_id": account_id,
                                      "amount": txn["amount"],
                                      "transaction_id": txn["id"]})
            self._send_json(200, txn)
            return
        if len(parts) == 4 and parts[1] == "accounts" and parts[3] == "transactions" \
                and method == "GET":
            account_id = int(parts[2])
            _check_account_visible(state, user, account_id)
            limit = q("limit")
            txns = state.bank.transaction_history(
                account_id, limit=int(limit) if limit else None)
            self._send_json(200, {"transactions": txns})
            return
        if len(parts) == 4 and parts[1] == "accounts" and parts[3] == "statement" \
                and method == "GET":
            account_id = int(parts[2])
            _check_account_visible(state, user, account_id)
            now = datetime.now()
            year = int(q("year") or now.year)
            month = int(q("month") or now.month)
            self._send_json(200, state.bank.monthly_statement(
                account_id, year, month))
            return

        # Transfers
        if parts == ["api", "transfers"] and method == "POST":
            body = self._read_json()
            from_id = body.get("from_id", body.get("from_account_id"))
            to_id = body.get("to_id", body.get("to_account_id"))
            if from_id is None or to_id is None:
                raise ApiError(400, "from_id and to_id are required")
            _check_account_visible(state, user, int(from_id))
            result = state.bank.transfer(int(from_id), int(to_id),
                                         body.get("amount"),
                                         body.get("description", ""))
            state.audit.append_event(user["username"], "transfer",
                                     {"from_account_id": int(from_id),
                                      "to_account_id": int(to_id),
                                      "amount": body.get("amount")})
            self._send_json(200, result)
            return

        # Fraud
        if parts == ["api", "fraud", "score"] and method == "POST":
            body = self._read_json()
            txn = body.get("transaction") or body
            history = body.get("history") or []
            score, flagged, reasons = score_transaction(txn, history)
            self._send_json(200, {"score": score, "flagged": flagged,
                                  "reasons": reasons})
            return
        if parts == ["api", "fraud", "review"] and method == "GET":
            flagged = _fraud_review(state, user)
            self._send_json(200, {"flagged": flagged,
                                  "flagged_count": len(flagged)})
            return

        # Credit / insights / assistant
        if parts == ["api", "credit", "score"] and method == "POST":
            body = self._read_json()
            features = body.get("features") or body
            self._send_json(200, credit_score(features))
            return
        if parts == ["api", "insights"] and method == "GET":
            accounts = _visible_account_ids(state, user)
            txns = _all_transactions(state, [a["id"] for a in accounts])
            result = spending_insights(txns)
            result["demo_notice"] = DEMO_BANNER
            self._send_json(200, result)
            return
        if parts == ["api", "assistant", "ask"] and method == "POST":
            body = self._read_json()
            question = body.get("question", "")
            answer, sources = answer_question(question)
            self._send_json(200, {"answer": answer, "sources": sources})
            return

        # KYC
        if parts == ["api", "kyc"] and method == "GET":
            status = q("status")
            self._send_json(200, {"records": state.kyc.list_customer_records(
                status=status)})
            return
        if parts == ["api", "kyc"] and method == "POST":
            body = self._read_json()
            rec = state.kyc.create_customer_record(
                body.get("name"), body.get("email"), body.get("dob"),
                body.get("address"), body.get("id_type"),
                body.get("id_number_hash", body.get("id_number")))
            state.audit.append_event(user["username"], "kyc_created",
                                     {"customer_id": rec["id"]})
            self._send_json(201, rec)
            return

        # Loans
        if parts == ["api", "loans"] and method == "GET":
            status = q("status")
            loans = state.loans.list_loans(status=status)
            if user["role"] == "customer" and user.get("customer_id") is not None:
                loans = [l for l in loans
                         if l["customer_id"] == user["customer_id"]]
            self._send_json(200, {"loans": loans})
            return
        if parts == ["api", "loans"] and method == "POST":
            body = self._read_json()
            customer_id = body.get("customer_id")
            if user["role"] == "customer":
                if user.get("customer_id") is None:
                    raise ApiError(400, "customer account has no linked customer")
                customer_id = user["customer_id"]
            if customer_id is None:
                raise ApiError(400, "customer_id is required")
            loan = state.loans.apply_loan(
                int(customer_id), body.get("amount"), body.get("purpose"),
                body.get("term_months"), credit_score=body.get("credit_score"))
            state.audit.append_event(user["username"], "loan_application",
                                     {"loan_id": loan["id"],
                                      "customer_id": loan["customer_id"],
                                      "amount": loan["amount"]})
            self._send_json(201, loan)
            return
        if len(parts) == 4 and parts[1] == "loans" and parts[3] == "review" \
                and method == "POST":
            if not has_permission(user, "review_loan"):
                raise ApiError(403, "manager/admin only may review loans")
            body = self._read_json()
            loan = state.loans.review_loan(int(parts[2]), user,
                                           body.get("decision"),
                                           body.get("note"))
            state.audit.append_event(user["username"], "loan_review",
                                     {"loan_id": loan["id"],
                                      "status": loan["status"],
                                      "decision": body.get("decision")})
            self._send_json(200, loan)
            return

        # Audit
        if parts == ["api", "audit"] and method == "GET":
            ok, bad = state.audit.verify_chain()
            self._send_json(200, {"events": state.audit.list_events(),
                                  "chain_valid": ok,
                                  "first_bad_index": bad})
            return

        # Reports (manager/admin only)
        if parts == ["api", "reports"] and method == "GET":
            _require_manager_or_admin(user)
            accounts = _all_accounts(state)
            txns = _all_transactions(state)
            flagged = _fraud_review(state, user)
            flagged_plain = []
            for item in flagged:
                plain = dict(item["transaction"])
                plain["reason"] = "; ".join(item["reasons"])
                flagged_plain.append(plain)
            self._send_json(200, {
                "totals": totals_report(accounts, txns),
                "flagged": flagged_report(flagged_plain),
                "loan_pipeline": loan_pipeline_report(state.loans.list_loans()),
                "demo_notice": DEMO_BANNER})
            return

        raise ApiError(404, "not found")


def make_server(state, host="127.0.0.1", port=8000):
    server = HTTPServer((host, port), Handler)
    server.state = state
    return server


def serve(state, host="127.0.0.1", port=8000):
    server = make_server(state, host, port)
    print("AI Banking System (DEMO / EDUCATIONAL ONLY)", flush=True)
    print("Dashboard: http://%s:%d/" % (host, port), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Server stopped.", flush=True)
    return server
