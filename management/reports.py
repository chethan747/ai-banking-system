"""Management reports over plain data.

DEMONSTRATION / EDUCATIONAL ONLY -- not production reporting or
compliance output.

These functions deliberately take only simple inputs -- lists/dicts
of accounts, transactions, flagged items, loans -- and do NOT import
``banking`` or ``ai_engine`` internals, so they can be tested and
reused against any plain-data source. Each returns a dict of counts
and totals; empty inputs yield zeros (not errors). Amounts are read
with ``dict.get`` and coerced to float, tolerating missing keys.

Transaction direction: a ``type`` of credit/deposit counts as a
credit and debit/withdrawal as a debit; when ``type`` is absent, a
positive amount counts as a credit and a negative amount as a debit.
``total_transaction_volume`` is the sum of absolute amounts.
"""

_CREDIT_TYPES = {"credit", "deposit", "incoming", "credit_card_payment"}
_DEBIT_TYPES = {"debit", "withdrawal", "payment", "outgoing", "purchase"}


def _amount(item, *keys):
    for key in keys:
        if key in item and item[key] is not None:
            try:
                return float(item[key])
            except (TypeError, ValueError):
                return 0.0
    return 0.0


def _round(value):
    return round(float(value), 2)


def totals_report(accounts, transactions):
    """Totals over accounts and transactions (plain lists of dicts)."""
    accounts = list(accounts or [])
    transactions = list(transactions or [])
    total_balance = sum(_amount(a, "balance", "amount") for a in accounts)
    credits = 0.0
    debits = 0.0
    for txn in transactions:
        amount = _amount(txn, "amount")
        txn_type = str(txn.get("type", "")).lower()
        if txn_type in _CREDIT_TYPES or (txn_type not in _DEBIT_TYPES and amount > 0):
            credits += abs(amount)
        elif txn_type in _DEBIT_TYPES or amount < 0:
            debits += abs(amount)
    return {
        "account_count": len(accounts),
        "total_balance": _round(total_balance),
        "average_balance": _round(total_balance / len(accounts)) if accounts else 0.0,
        "transaction_count": len(transactions),
        "total_credits": _round(credits),
        "total_debits": _round(debits),
        "net_flow": _round(credits - debits),
        "total_transaction_volume": _round(credits + debits),
    }


def flagged_report(flagged_transactions):
    """Summary of flagged transactions (plain list of dicts).

    ``reason`` and ``severity`` keys are grouped when present;
    transaction ids are collected from ``id`` / ``transaction_id``.
    """
    items = list(flagged_transactions or [])
    by_reason = {}
    by_severity = {}
    ids = []
    total = 0.0
    for item in items:
        total += abs(_amount(item, "amount"))
        reason = item.get("reason", "unspecified")
        by_reason[str(reason)] = by_reason.get(str(reason), 0) + 1
        if "severity" in item and item["severity"] is not None:
            sev = str(item["severity"])
            by_severity[sev] = by_severity.get(sev, 0) + 1
        txn_id = item.get("id", item.get("transaction_id"))
        if txn_id is not None:
            ids.append(txn_id)
    return {
        "flagged_count": len(items),
        "total_flagged_amount": _round(total),
        "by_reason": by_reason,
        "by_severity": by_severity,
        "transaction_ids": ids,
    }


def loan_pipeline_report(loans):
    """Summary of the loan pipeline (plain list of loan dicts)."""
    items = list(loans or [])
    by_status = {}
    total_requested = 0.0
    approved_amount = 0.0
    pending_amount = 0.0
    approved_count = 0
    for loan in items:
        amount = _amount(loan, "amount")
        status = str(loan.get("status", "pending")).lower()
        by_status[status] = by_status.get(status, 0) + 1
        total_requested += amount
        if status == "approved":
            approved_amount += amount
            approved_count += 1
        elif status == "pending":
            pending_amount += amount
    total = len(items)
    return {
        "loan_count": total,
        "by_status": by_status,
        "total_requested": _round(total_requested),
        "total_approved_amount": _round(approved_amount),
        "total_pending_amount": _round(pending_amount),
        "average_amount": _round(total_requested / total) if total else 0.0,
        "approval_rate": round(approved_count / total, 4) if total else 0.0,
    }
