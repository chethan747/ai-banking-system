"""Tests for Module 3 -- Management & Compliance (stdlib unittest).

All stores use in-memory SQLite (":memory:") so tests are isolated.
Demo data only: fictitious names, no real IDs, no real money.
Run from ~/workspace/ai-banking-system/:
    python3 -m unittest discover -s tests -v
"""

import hashlib
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from management.auth import AuthStore, has_permission
from management.kyc import CustomerStore, hash_id_number
from management.loans import LoanStore
from management.audit import AuditLog
from management.reports import totals_report, flagged_report, loan_pipeline_report


def _users():
    auth = AuthStore(":memory:")
    customer = auth.create_user("demo_customer", "cust-pass-123", "customer", customer_id=1)
    teller = auth.create_user("demo_teller", "tell-pass-123", "teller")
    manager = auth.create_user("demo_manager", "mgr-pass-123", "manager")
    admin = auth.create_user("demo_admin", "adm-pass-123", "admin")
    return auth, customer, teller, manager, admin


class TestAuth(unittest.TestCase):
    def test_no_plaintext_stored_and_verify_correct(self):
        auth, *_ = _users()
        stored = auth.raw_password_hash("demo_manager")
        self.assertIsNotNone(stored)
        self.assertNotIn("mgr-pass-123", stored)
        self.assertNotEqual(stored, "mgr-pass-123")
        user = auth.verify_user("demo_manager", "mgr-pass-123")
        self.assertIsNotNone(user)
        self.assertEqual(user["username"], "demo_manager")
        self.assertEqual(user["role"], "manager")
        self.assertNotIn("password_hash", user)
        self.assertNotIn("password", user)

    def test_wrong_password_and_unknown_user_fail(self):
        auth, *_ = _users()
        self.assertIsNone(auth.verify_user("demo_manager", "wrong-password"))
        self.assertIsNone(auth.verify_user("nobody", "mgr-pass-123"))

    def test_salts_differ_per_user(self):
        auth = AuthStore(":memory:")
        auth.create_user("user_a", "same-password", "teller")
        auth.create_user("user_b", "same-password", "teller")
        self.assertNotEqual(auth.raw_password_hash("user_a"),
                            auth.raw_password_hash("user_b"))

    def test_duplicate_username_and_bad_role_rejected(self):
        auth, *_ = _users()
        with self.assertRaises(ValueError):
            auth.create_user("demo_manager", "other-pass", "manager")
        with self.assertRaises(ValueError):
            auth.create_user("new_user", "pass", "superuser")

    def test_permission_checks(self):
        _, customer, teller, manager, admin = _users()
        # Only manager/admin approve loans; only admin manage users.
        self.assertFalse(has_permission(customer, "approve_loans"))
        self.assertFalse(has_permission(teller, "approve_loans"))
        self.assertTrue(has_permission(manager, "approve_loans"))
        self.assertTrue(has_permission(admin, "approve_loans"))
        self.assertFalse(has_permission(manager, "manage_users"))
        self.assertTrue(has_permission(admin, "manage_users"))
        # Teller can view/create customers; customer cannot.
        self.assertTrue(has_permission(teller, "view_customers"))
        self.assertTrue(has_permission(teller, "create_customer"))
        self.assertFalse(has_permission(customer, "view_customers"))
        # Customer can view own records only.
        self.assertTrue(has_permission(customer, "view_own_records"))
        self.assertFalse(has_permission(customer, "view_all_records"))
        # Unknown action denied.
        self.assertFalse(has_permission(admin, "launch_rockets"))


class TestKyc(unittest.TestCase):
    def test_create_stores_hash_not_raw_id(self):
        store = CustomerStore(":memory:")
        raw_demo_id = "DEMO-ID-12345"
        rec = store.create_customer_record(
            "Demo Person", "demo@example.test", "1990-01-01",
            "1 Demo Street, Demo City", "passport", raw_demo_id)
        self.assertEqual(rec["kyc_status"], "pending")
        self.assertEqual(rec["id_number_hash"], hashlib.sha256(raw_demo_id.encode()).hexdigest())
        self.assertNotIn(raw_demo_id, str(rec))
        self.assertNotIn("id_number", str(rec).replace("id_number_hash", ""))

    def test_prehashed_id_stored_as_is(self):
        store = CustomerStore(":memory:")
        digest = hash_id_number("DEMO-ID-999")
        rec = store.create_customer_record(
            "Demo Person", "demo@example.test", "1990-01-01",
            "1 Demo Street", "license", digest)
        self.assertEqual(rec["id_number_hash"], digest)

    def test_kyc_status_flow_and_listing_by_status(self):
        store = CustomerStore(":memory:")
        a = store.create_customer_record("A Demo", "a@example.test", "1990-01-01",
                                         "1 Demo St", "passport", "DEMO-A")
        b = store.create_customer_record("B Demo", "b@example.test", "1991-02-02",
                                         "2 Demo St", "passport", "DEMO-B")
        store.update_kyc_status(a["id"], "verified", "demo_manager")
        self.assertEqual(store.get_customer_record(a["id"])["kyc_status"], "verified")
        self.assertEqual(store.get_customer_record(a["id"])["reviewed_by"], "demo_manager")
        store.update_kyc_status(b["id"], "rejected", "demo_manager")
        self.assertEqual([r["id"] for r in store.list_customer_records(status="verified")],
                         [a["id"]])
        self.assertEqual([r["id"] for r in store.list_customer_records(status="rejected")],
                         [b["id"]])
        self.assertEqual(len(store.list_customer_records()), 2)
        self.assertIsNone(store.get_customer_record(9999))

    def test_invalid_kyc_status_and_unknown_customer(self):
        store = CustomerStore(":memory:")
        rec = store.create_customer_record("A Demo", "a@example.test", "1990-01-01",
                                           "1 Demo St", "passport", "DEMO-A")
        with self.assertRaises(ValueError):
            store.update_kyc_status(rec["id"], "maybe", "demo_manager")
        with self.assertRaises(ValueError):
            store.update_kyc_status(9999, "verified", "demo_manager")


class TestLoans(unittest.TestCase):
    def test_pending_to_approved_with_reviewer_recorded(self):
        _, _, _, manager, _ = _users()
        loans = LoanStore(":memory:")
        loan = loans.apply_loan(1, 5000.0, "demo home repair", 24, credit_score=720)
        self.assertEqual(loan["status"], "pending")
        reviewed = loans.review_loan(loan["id"], manager, "approve", "demo approval")
        self.assertEqual(reviewed["status"], "approved")
        self.assertEqual(reviewed["reviewer"], "demo_manager")
        self.assertEqual(reviewed["note"], "demo approval")
        self.assertIsNotNone(reviewed["reviewed_at"])
        self.assertEqual(loans.get_loan(loan["id"])["status"], "approved")

    def test_reject_and_list_by_status(self):
        _, _, _, manager, _ = _users()
        loans = LoanStore(":memory:")
        l1 = loans.apply_loan(1, 1000.0, "demo purpose", 12)
        l2 = loans.apply_loan(2, 2000.0, "demo purpose", 12)
        loans.review_loan(l1["id"], manager, "reject", "demo rejection")
        self.assertEqual([l["id"] for l in loans.list_loans(status="rejected")], [l1["id"]])
        self.assertEqual([l["id"] for l in loans.list_loans(status="pending")], [l2["id"]])
        self.assertEqual(len(loans.list_loans()), 2)

    def test_double_review_rejected(self):
        _, _, _, manager, _ = _users()
        loans = LoanStore(":memory:")
        loan = loans.apply_loan(1, 1000.0, "demo purpose", 12)
        loans.review_loan(loan["id"], manager, "approve")
        with self.assertRaises(ValueError):
            loans.review_loan(loan["id"], manager, "reject")

    def test_non_manager_review_rejected(self):
        _, customer, teller, _, admin = _users()
        loans = LoanStore(":memory:")
        loan = loans.apply_loan(1, 1000.0, "demo purpose", 12)
        with self.assertRaises(PermissionError):
            loans.review_loan(loan["id"], customer, "approve")
        with self.assertRaises(PermissionError):
            loans.review_loan(loan["id"], teller, "approve")
        # Admin can review, and the loan is still pending after the failures.
        self.assertEqual(loans.review_loan(loan["id"], admin, "approve")["status"], "approved")

    def test_invalid_loan_inputs(self):
        loans = LoanStore(":memory:")
        with self.assertRaises(ValueError):
            loans.apply_loan(1, -100.0, "demo", 12)
        with self.assertRaises(ValueError):
            loans.apply_loan(1, 100.0, "demo", 0)
        with self.assertRaises(ValueError):
            loans.apply_loan(1, 100.0, "demo", 12, credit_score=100)


class TestAudit(unittest.TestCase):
    def test_chain_verifies_and_tamper_detected(self):
        log = AuditLog(":memory:")
        log.append_event("demo_manager", "loan_approved", {"loan_id": 1})
        log.append_event("demo_admin", "user_created", {"username": "demo_teller"})
        log.append_event("demo_teller", "kyc_verified", {"customer_id": 1})
        ok, bad = log.verify_chain()
        self.assertTrue(ok)
        self.assertIsNone(bad)
        events = log.list_events()
        self.assertEqual(events[0]["previous_hash"], "0" * 64)
        self.assertEqual(events[1]["previous_hash"], events[0]["hash"])
        # Tamper: rewrite a stored detail directly in the DB.
        log.conn.execute("UPDATE audit_log SET details = ? WHERE id = ?",
                         ('{"loan_id": 999}', events[0]["id"]))
        log.conn.commit()
        ok, bad = log.verify_chain()
        self.assertFalse(ok)
        self.assertEqual(bad, 0)

    def test_empty_chain_verifies(self):
        self.assertEqual(AuditLog(":memory:").verify_chain(), (True, None))


class TestReports(unittest.TestCase):
    def test_totals_report(self):
        report = totals_report(
            [{"balance": 1000.0}, {"balance": 500.0}],
            [{"amount": 200.0, "type": "deposit"},
             {"amount": 50.0, "type": "withdrawal"},
             {"amount": 25.0, "type": "deposit"}])
        self.assertEqual(report["account_count"], 2)
        self.assertEqual(report["total_balance"], 1500.0)
        self.assertEqual(report["average_balance"], 750.0)
        self.assertEqual(report["transaction_count"], 3)
        self.assertEqual(report["total_credits"], 225.0)
        self.assertEqual(report["total_debits"], 50.0)
        self.assertEqual(report["net_flow"], 175.0)
        self.assertEqual(report["total_transaction_volume"], 275.0)
        self.assertEqual(totals_report([], []),
                         {"account_count": 0, "total_balance": 0.0, "average_balance": 0.0,
                          "transaction_count": 0, "total_credits": 0.0, "total_debits": 0.0,
                          "net_flow": 0.0, "total_transaction_volume": 0.0})

    def test_flagged_and_loan_pipeline_reports(self):
        flagged = flagged_report([
            {"id": 7, "amount": 900.0, "reason": "large_amount", "severity": "high"},
            {"id": 8, "amount": 100.0, "reason": "large_amount", "severity": "low"},
        ])
        self.assertEqual(flagged["flagged_count"], 2)
        self.assertEqual(flagged["total_flagged_amount"], 1000.0)
        self.assertEqual(flagged["by_reason"], {"large_amount": 2})
        self.assertEqual(flagged["by_severity"], {"high": 1, "low": 1})
        self.assertEqual(flagged["transaction_ids"], [7, 8])

        pipeline = loan_pipeline_report([
            {"amount": 5000.0, "status": "approved"},
            {"amount": 3000.0, "status": "pending"},
            {"amount": 2000.0, "status": "rejected"},
        ])
        self.assertEqual(pipeline["loan_count"], 3)
        self.assertEqual(pipeline["by_status"],
                         {"approved": 1, "pending": 1, "rejected": 1})
        self.assertEqual(pipeline["total_requested"], 10000.0)
        self.assertEqual(pipeline["total_approved_amount"], 5000.0)
        self.assertEqual(pipeline["total_pending_amount"], 3000.0)
        self.assertAlmostEqual(pipeline["approval_rate"], 1 / 3, places=4)


if __name__ == "__main__":
    unittest.main()
