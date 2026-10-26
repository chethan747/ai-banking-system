"""Unit tests for Module 1 — Core Banking (banking.core.Bank).

Run from ~/workspace/ai-banking-system with:
    python3 -m unittest discover -s tests -v
All tests use an in-memory SQLite database and demo-only seed data.
"""

import unittest
from datetime import datetime, timezone

from banking.core import Bank


class BankingTestCase(unittest.TestCase):
    def setUp(self):
        self.bank = Bank(":memory:", annual_savings_rate=0.12)
        self.customer = self.bank.create_customer("Demo User", "demo@example.test")

    def tearDown(self):
        self.bank.close()

    def _checking(self, initial=0):
        return self.bank.create_account(self.customer["id"], "checking", initial)

    def _savings(self, initial=0):
        return self.bank.create_account(self.customer["id"], "savings", initial)

    # -- creation / balances -------------------------------------------
    def test_create_customer_and_account(self):
        account = self._checking(500)
        self.assertEqual(account["customer_id"], self.customer["id"])
        self.assertEqual(account["account_type"], "checking")
        self.assertEqual(account["balance"], 500)
        self.assertEqual(account["status"], "open")
        self.assertTrue(account["account_number"].startswith("DEMO-"))
        other = self._savings()
        self.assertNotEqual(account["account_number"], other["account_number"])

    def test_create_account_rejects_bad_type_missing_customer_negative(self):
        with self.assertRaises(ValueError):
            self.bank.create_account(self.customer["id"], "credit")
        with self.assertRaises(LookupError):
            self.bank.create_account(99999, "checking")
        with self.assertRaises(ValueError):
            self.bank.create_account(self.customer["id"], "checking", -10)

    def test_get_balance_and_get_account_missing(self):
        account = self._checking(250)
        self.assertEqual(self.bank.get_balance(account["id"]), 250)
        self.assertEqual(self.bank.get_account(account["id"])["balance"], 250)
        with self.assertRaises(LookupError):
            self.bank.get_balance(99999)
        with self.assertRaises(LookupError):
            self.bank.get_account(99999)

    # -- deposit / withdraw ---------------------------------------------
    def test_deposit_and_withdraw(self):
        account = self._checking(100)
        deposit = self.bank.deposit(account["id"], 50, "Payday demo")
        self.assertEqual(deposit["type"], "deposit")
        self.assertEqual(deposit["amount"], 50)
        self.assertEqual(deposit["balance_after"], 150)
        withdrawal = self.bank.withdraw(account["id"], 30, "Groceries demo")
        self.assertEqual(withdrawal["type"], "withdrawal")
        self.assertEqual(withdrawal["balance_after"], 120)
        self.assertEqual(self.bank.get_balance(account["id"]), 120)

    def test_positive_amount_validation(self):
        account = self._checking(100)
        for bad in (0, -5, -0.01):
            with self.assertRaises(ValueError, msg=f"deposit {bad}"):
                self.bank.deposit(account["id"], bad)
            with self.assertRaises(ValueError, msg=f"withdraw {bad}"):
                self.bank.withdraw(account["id"], bad)
        self.assertEqual(self.bank.get_balance(account["id"]), 100)

    def test_withdraw_insufficient_funds_rejected_and_balance_unchanged(self):
        account = self._checking(40)
        with self.assertRaises(ValueError):
            self.bank.withdraw(account["id"], 41)
        with self.assertRaises(ValueError):
            self.bank.withdraw(account["id"], 1000)
        self.assertEqual(self.bank.get_balance(account["id"]), 40)

    # -- transfer --------------------------------------------------------
    def test_transfer_moves_money_and_records_both_sides(self):
        source = self._checking(500)
        dest = self._savings(100)
        result = self.bank.transfer(source["id"], dest["id"], 200, "Rent demo")
        self.assertEqual(result["from"]["type"], "transfer_out")
        self.assertEqual(result["to"]["type"], "transfer_in")
        self.assertEqual(result["from"]["balance_after"], 300)
        self.assertEqual(result["to"]["balance_after"], 300)
        self.assertEqual(self.bank.get_balance(source["id"]), 300)
        self.assertEqual(self.bank.get_balance(dest["id"]), 300)

    def test_transfer_to_self_rejected(self):
        account = self._checking(100)
        with self.assertRaises(ValueError):
            self.bank.transfer(account["id"], account["id"], 10)
        self.assertEqual(self.bank.get_balance(account["id"]), 100)

    def test_transfer_atomicity_on_insufficient_funds(self):
        source = self._checking(50)
        dest = self._checking(20)
        before = self.bank.transaction_history(source["id"])
        with self.assertRaises(ValueError):
            self.bank.transfer(source["id"], dest["id"], 51)
        self.assertEqual(self.bank.get_balance(source["id"]), 50)
        self.assertEqual(self.bank.get_balance(dest["id"]), 20)
        self.assertEqual(self.bank.transaction_history(source["id"]), before)
        self.assertEqual(len(self.bank.transaction_history(dest["id"])), 1)

    def test_transfer_atomicity_on_closed_or_missing_destination(self):
        source = self._checking(200)
        closed = self._checking(10)
        self.bank.close_account(closed["id"])
        before = self.bank.transaction_history(source["id"])
        with self.assertRaises(ValueError):
            self.bank.transfer(source["id"], closed["id"], 25)
        with self.assertRaises(LookupError):
            self.bank.transfer(source["id"], 99999, 25)
        self.assertEqual(self.bank.get_balance(source["id"]), 200)
        self.assertEqual(self.bank.transaction_history(source["id"]), before)

    def test_closed_account_rejects_operations(self):
        account = self._checking(100)
        self.bank.close_account(account["id"])
        self.assertEqual(self.bank.get_account(account["id"])["status"], "closed")
        for call in (
            lambda: self.bank.deposit(account["id"], 10),
            lambda: self.bank.withdraw(account["id"], 10),
        ):
            with self.assertRaises(ValueError):
                call()
        self.assertEqual(self.bank.get_balance(account["id"]), 100)

    # -- history ---------------------------------------------------------
    def test_transaction_history_chronological_with_details(self):
        account = self._checking(100)
        self.bank.deposit(account["id"], 50, "first")
        self.bank.withdraw(account["id"], 20, "second")
        history = self.bank.transaction_history(account["id"])
        self.assertEqual(
            [t["type"] for t in history], ["opening", "deposit", "withdrawal"])
        self.assertEqual(
            [t["balance_after"] for t in history], [100, 150, 130])
        self.assertEqual(history[1]["description"], "first")
        self.assertTrue(all("timestamp" in t and "amount" in t for t in history))
        stamps = [t["timestamp"] for t in history]
        self.assertEqual(stamps, sorted(stamps))

    def test_transaction_history_limit_returns_most_recent_in_order(self):
        account = self._checking()
        for amount in (10, 20, 30):
            self.bank.deposit(account["id"], amount)
        recent = self.bank.transaction_history(account["id"], limit=2)
        self.assertEqual([t["amount"] for t in recent], [20, 30])
        self.assertEqual([t["balance_after"] for t in recent], [30, 60])
        with self.assertRaises(LookupError):
            self.bank.transaction_history(99999)

    # -- interest ----------------------------------------------------------
    def test_interest_accrual_savings_only_and_recorded(self):
        savings = self._savings(1200)
        # 12% annual / 12 months = 1% of 1200 = 12.00
        recorded = self.bank.accrue_interest(savings["id"])
        self.assertEqual(len(recorded), 1)
        self.assertEqual(recorded[0]["type"], "interest")
        self.assertEqual(recorded[0]["amount"], 12)
        self.assertEqual(recorded[0]["balance_after"], 1212)
        self.assertEqual(self.bank.get_balance(savings["id"]), 1212)

    def test_interest_accrual_rejects_checking_and_accrues_all_savings(self):
        checking = self._checking(1200)
        with self.assertRaises(ValueError):
            self.bank.accrue_interest(checking["id"])
        first = self._savings(1200)
        second = self._savings(600)
        recorded = self.bank.accrue_interest()
        self.assertEqual(sorted(t["amount"] for t in recorded), [6, 12])
        self.assertEqual(self.bank.get_balance(first["id"]), 1212)
        self.assertEqual(self.bank.get_balance(second["id"]), 606)
        self.assertEqual(self.bank.get_balance(checking["id"]), 1200)

    def test_interest_accrual_zero_balance_records_nothing(self):
        savings = self._savings(0)
        self.assertEqual(self.bank.accrue_interest(savings["id"]), [])
        self.assertEqual(self.bank.get_balance(savings["id"]), 0)

    # -- statement ---------------------------------------------------------
    def test_monthly_statement_totals_reconcile(self):
        now = datetime.now(timezone.utc)
        account = self._checking(500)   # opening txn, this month
        self.bank.deposit(account["id"], 200)
        self.bank.withdraw(account["id"], 100)
        stmt = self.bank.monthly_statement(account["id"], now.year, now.month)
        self.assertEqual(stmt["opening_balance"], 0)
        self.assertEqual(stmt["closing_balance"], 600)
        self.assertEqual(stmt["total_in"], 700)   # opening 500 + deposit 200
        self.assertEqual(stmt["total_out"], 100)
        self.assertEqual(stmt["transaction_count"], 3)
        self.assertEqual(
            stmt["opening_balance"] + stmt["total_in"] - stmt["total_out"],
            stmt["closing_balance"])
        self.assertEqual(stmt["account_number"], account["account_number"])

    def test_monthly_statement_empty_month(self):
        account = self._checking(100)
        stmt = self.bank.monthly_statement(account["id"], 2000, 1)
        self.assertEqual(stmt["opening_balance"], 0)
        self.assertEqual(stmt["closing_balance"], 0)
        self.assertEqual(stmt["total_in"], 0)
        self.assertEqual(stmt["total_out"], 0)
        self.assertEqual(stmt["transactions"], [])
        with self.assertRaises(ValueError):
            self.bank.monthly_statement(account["id"], 2026, 13)


if __name__ == "__main__":
    unittest.main()
