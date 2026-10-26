"""Tests for Module 4 -- API server + audit-on-action (stdlib unittest).

Starts the real server on an ephemeral port in a dedicated thread
(the server thread builds its own Bank/stores, because the stdlib
sqlite connection is used only from the serving thread). Demo data
only: fictitious names, no real money.

Run from the project root:
    python3 -m unittest discover -s tests
"""

import http.client
import json
import os
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.seed import seed_data
from api.server import build_state, make_server


def _parse_details(event):
    details = event.get("details", "")
    if isinstance(details, str):
        try:
            return json.loads(details)
        except ValueError:
            return {"raw": details}
    return details


class ApiTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="ai-banking-api-test-")
        cls.ready = threading.Event()
        cls.holder = {}

        def _serve():
            state = build_state(os.path.join(cls._tmp.name, "data"))
            seed_data(state)
            server = make_server(state, "127.0.0.1", 0)
            cls.holder["server"] = server
            cls.holder["port"] = server.server_address[1]
            cls.ready.set()
            server.serve_forever()

        cls._thread = threading.Thread(target=_serve, daemon=True)
        cls._thread.start()
        assert cls.ready.wait(60), "server did not start"
        cls.port = cls.holder["port"]

    @classmethod
    def tearDownClass(cls):
        cls.holder["server"].shutdown()
        cls.holder["server"].server_close()
        cls._tmp.cleanup()

    # -- helpers -------------------------------------------------------
    def request(self, method, path, body=None, token=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        conn.request(method, path,
                     body=json.dumps(body) if body is not None else None,
                     headers=headers)
        resp = conn.getresponse()
        raw = resp.read()
        conn.close()
        try:
            data = json.loads(raw.decode("utf-8"))
        except ValueError:
            data = {}
        return resp.status, data

    def login(self, username, password):
        status, data = self.request("POST", "/api/login",
                                    {"username": username, "password": password})
        self.assertEqual(status, 200, data)
        return data["token"]

    def accounts(self, token):
        status, data = self.request("GET", "/api/accounts", token=token)
        self.assertEqual(status, 200, data)
        return data["accounts"]

    # -- tests ---------------------------------------------------------
    def test_login_success_and_failure(self):
        status, data = self.request("POST", "/api/login",
                                    {"username": "admin", "password": "admin123"})
        self.assertEqual(status, 200)
        self.assertIn("token", data)
        self.assertEqual(data["username"], "admin")
        self.assertEqual(data["role"], "admin")
        self.assertNotIn("password", data)
        self.assertNotIn("password_hash", data)
        status, _ = self.request("POST", "/api/login",
                                 {"username": "admin", "password": "wrong"})
        self.assertEqual(status, 401)
        status, _ = self.request("GET", "/api/accounts")
        self.assertEqual(status, 401)

    def test_deposit_increases_balance(self):
        token = self.login("teller", "teller123")
        acct = self.accounts(token)[0]
        before = acct["balance"]
        status, txn = self.request(
            "POST", "/api/accounts/%d/deposit" % acct["id"],
            {"amount": 50, "description": "Test deposit"}, token=token)
        self.assertEqual(status, 200, txn)
        after = self.accounts(token)[0]["balance"]
        self.assertAlmostEqual(after, before + 50, places=2)

    def test_transfer_moves_money(self):
        token = self.login("teller", "teller123")
        accts = self.accounts(token)
        src, dst = accts[0], accts[1]
        before_src, before_dst = src["balance"], dst["balance"]
        status, data = self.request("POST", "/api/transfers",
                                    {"from_id": src["id"], "to_id": dst["id"],
                                     "amount": 25, "description": "Test transfer"},
                                    token=token)
        self.assertEqual(status, 200, data)
        fresh = {a["id"]: a["balance"] for a in self.accounts(token)}
        self.assertAlmostEqual(fresh[src["id"]], before_src - 25, places=2)
        self.assertAlmostEqual(fresh[dst["id"]], before_dst + 25, places=2)

    def test_fraud_review_returns_flagged_demo_transaction(self):
        token = self.login("manager", "manager123")
        status, data = self.request("GET", "/api/fraud/review", token=token)
        self.assertEqual(status, 200, data)
        self.assertGreaterEqual(data["flagged_count"], 1)
        big = [f for f in data["flagged"]
               if f["transaction"]["amount"] >= 5000 and f["score"] >= 70]
        self.assertGreaterEqual(len(big), 1)
        self.assertTrue(big[0]["reasons"])

    def test_credit_score_endpoint_returns_band_and_reasons(self):
        token = self.login("teller", "teller123")
        status, data = self.request("POST", "/api/credit/score",
                                    {"features": {"income": 80000,
                                                  "monthly_debt": 800,
                                                  "employment_years": 4,
                                                  "past_defaults": 0,
                                                  "open_loans": 1,
                                                  "savings_balance": 12000}},
                                    token=token)
        self.assertEqual(status, 200, data)
        self.assertTrue(300 <= data["score"] <= 850)
        self.assertIn(data["band"], ("Poor", "Fair", "Good", "Excellent"))
        self.assertTrue(data["reasons"])

    def test_loan_approve_by_manager_and_customer_forbidden(self):
        manager = self.login("manager", "manager123")
        customer = self.login("customer", "customer123")
        accts = self.accounts(manager)
        cust_id = accts[0]["customer_id"]
        _, loan = self.request("POST", "/api/loans",
                               {"customer_id": cust_id, "amount": 1000,
                                "purpose": "Test loan", "term_months": 12},
                               token=manager)
        status, reviewed = self.request(
            "POST", "/api/loans/%d/review" % loan["id"],
            {"decision": "approve"}, token=manager)
        self.assertEqual(status, 200, reviewed)
        self.assertEqual(reviewed["status"], "approved")
        _, loan2 = self.request("POST", "/api/loans",
                                {"customer_id": cust_id, "amount": 1000,
                                 "purpose": "Test loan 2", "term_months": 12},
                                token=manager)
        status, _ = self.request(
            "POST", "/api/loans/%d/review" % loan2["id"],
            {"decision": "approve"}, token=customer)
        self.assertEqual(status, 403)

    def test_reports_gated_to_manager_admin(self):
        manager = self.login("manager", "manager123")
        customer = self.login("customer", "customer123")
        status, data = self.request("GET", "/api/reports", token=manager)
        self.assertEqual(status, 200, data)
        self.assertIn("totals", data)
        self.assertIn("loan_pipeline", data)
        status, _ = self.request("GET", "/api/reports", token=customer)
        self.assertEqual(status, 403)

    def test_transfer_creates_audit_event(self):
        manager = self.login("manager", "manager123")
        accts = self.accounts(manager)
        src, dst = accts[0], accts[1]
        status, _ = self.request("POST", "/api/transfers",
                                 {"from_id": src["id"], "to_id": dst["id"],
                                  "amount": 10, "description": "Audit test"},
                                 token=manager)
        self.assertEqual(status, 200)
        status, data = self.request("GET", "/api/audit", token=manager)
        self.assertEqual(status, 200, data)
        self.assertTrue(data["chain_valid"])
        transfers = [e for e in data["events"] if e["action"] == "transfer"]
        self.assertGreaterEqual(len(transfers), 1)
        details = _parse_details(transfers[-1])
        self.assertEqual(details.get("from_account_id"), src["id"])
        self.assertEqual(details.get("to_account_id"), dst["id"])
        self.assertEqual(transfers[-1]["actor"], "manager")

    def test_statement_endpoint(self):
        token = self.login("teller", "teller123")
        acct = self.accounts(token)[0]
        import datetime
        now = datetime.datetime.now()
        status, data = self.request(
            "GET", "/api/accounts/%d/statement?year=%d&month=%d"
            % (acct["id"], now.year, now.month), token=token)
        self.assertEqual(status, 200, data)
        self.assertIn("opening_balance", data)
        self.assertIn("closing_balance", data)
        self.assertIn("total_in", data)
        self.assertIn("total_out", data)


if __name__ == "__main__":
    unittest.main()
