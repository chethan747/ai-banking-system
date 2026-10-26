"""CLI demo of the AI Banking System (no server needed).

Usage (from the project root -- the folder containing this file):
    macOS / Linux:  python3 demo.py
    Windows:        py demo.py

Runs a full end-to-end scenario against a fresh temporary database
that is deleted afterwards: open accounts, deposit, withdraw,
transfer, a fraud-flagged transaction, a credit score, a loan
application approved by a manager, a monthly statement, and an audit
chain verification. Prints readable output and exits 0.

DEMO / EDUCATIONAL ONLY: fictitious data, no real people or money.
AI scores are illustrative, not regulated decisions.
"""

from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai_engine.credit import credit_score
from ai_engine.fraud import score_transaction
from banking.core import Bank
from management.audit import AuditLog
from management.auth import AuthStore
from management.loans import LoanStore


def money(value):
    return "$%.2f" % value


def main():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    with tempfile.TemporaryDirectory(prefix="ai-banking-demo-") as tmp:
        tmp_path = Path(tmp)
        bank = Bank(str(tmp_path / "bank.db"))
        mgmt = str(tmp_path / "management.db")
        auth = AuthStore(mgmt)
        loans = LoanStore(mgmt)
        audit = AuditLog(mgmt)

        print("=== AI Banking System - CLI Demo ===")
        print("DEMO / EDUCATIONAL ONLY - fictitious data, not a real bank.\n")

        # 1. Customers and accounts
        dana = bank.create_customer("Dana Demo", "dana.demo@example.test")
        eli = bank.create_customer("Eli Demo", "eli.demo@example.test")
        dana_checking = bank.create_account(dana["id"], "checking", 1000)
        dana_savings = bank.create_account(dana["id"], "savings", 5000)
        eli_checking = bank.create_account(eli["id"], "checking", 500)
        print("1. Accounts opened")
        print("   Dana checking %s balance %s"
              % (dana_checking["account_number"], money(dana_checking["balance"])))
        print("   Dana savings  %s balance %s"
              % (dana_savings["account_number"], money(dana_savings["balance"])))
        print("   Eli checking  %s balance %s"
              % (eli_checking["account_number"], money(eli_checking["balance"])))

        # 2. Deposit / withdraw / transfer
        bank.deposit(dana_checking["id"], 2500, "Salary payroll")
        bank.withdraw(dana_checking["id"], 120, "Supermarket groceries")
        result = bank.transfer(dana_checking["id"], eli_checking["id"],
                               300, "Demo transfer to Eli")
        print("\n2. Deposit, withdraw, transfer")
        print("   Deposited %s (salary), withdrew %s (groceries)"
              % (money(2500), money(120)))
        print("   Transferred %s Dana -> Eli" % money(300))
        print("   Dana checking now %s; Eli checking now %s"
              % (money(bank.get_balance(dana_checking["id"])),
                 money(bank.get_balance(eli_checking["id"]))))
        audit.append_event("dana_demo", "transfer",
                           {"from_account_id": dana_checking["id"],
                            "to_account_id": eli_checking["id"], "amount": 300})

        # 3. Fraud-flagged transaction (rule-based, explainable)
        history = []
        for minutes_ago in range(12, 0, -1):
            history.append({
                "account_id": dana_checking["id"], "amount": 50.0,
                "timestamp": (now - timedelta(minutes=minutes_ago)).isoformat(),
            })
        suspicious = {
            "account_id": dana_checking["id"], "amount": 5000.0,
            "timestamp": now.isoformat(),
        }
        score, flagged, reasons = score_transaction(suspicious, history)
        print("\n3. Fraud scoring (illustrative only, threshold 70)")
        print("   Transaction: %s after 12 prior transactions of %s"
              % (money(5000), money(50)))
        print("   Score: %d/100  Flagged: %s" % (score, flagged))
        for reason in reasons:
            print("   - %s" % reason)
        assert flagged, "demo fraud transaction should be flagged"

        # 4. Credit score (illustrative only)
        result_score = credit_score({
            "income": 80000, "monthly_debt": 800, "employment_years": 4,
            "past_defaults": 0, "open_loans": 1, "savings_balance": 12000,
        })
        print("\n4. Credit score (illustrative only, NOT a lending decision)")
        print("   Score: %d  Band: %s" % (result_score["score"], result_score["band"]))
        for reason in result_score["reasons"]:
            print("   - %s" % reason)

        # 5. Loan: apply, then approve as manager
        manager = auth.create_user("demo_manager", "manager123", "manager")
        loan = loans.apply_loan(dana["id"], 8000, "Demo home repair", 36,
                                credit_score=result_score["score"])
        print("\n5. Loan workflow")
        print("   Applied: %s for %s (%s months) -> status %s"
              % (money(loan["amount"]), loan["purpose"],
                 loan["term_months"], loan["status"]))
        reviewed = loans.review_loan(loan["id"], manager, "approve",
                                     "Demo approval by manager")
        audit.append_event(manager["username"], "loan_review",
                           {"loan_id": loan["id"], "status": reviewed["status"]})
        print("   Reviewed by %s -> status %s"
              % (reviewed["reviewer"], reviewed["status"]))

        # 6. Monthly statement for the current month
        statement = bank.monthly_statement(dana_checking["id"],
                                           now.year, now.month)
        print("\n6. Monthly statement %04d-%02d for Dana checking"
              % (now.year, now.month))
        print("   Opening %s  Closing %s  In %s  Out %s  (%d transactions)"
              % (money(statement["opening_balance"]),
                 money(statement["closing_balance"]),
                 money(statement["total_in"]), money(statement["total_out"]),
                 statement["transaction_count"]))

        # 7. Audit chain
        ok, bad = audit.verify_chain()
        print("\n7. Audit chain")
        print("   Events: %d  Chain valid: %s (first bad index: %s)"
              % (len(audit.list_events()), ok, bad))
        assert ok, "audit chain must verify"

        print("\nDemo complete. Temporary database removed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
