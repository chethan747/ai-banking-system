"""Spending categorisation and insights (demo only, stdlib only).

Categorisation is pure keyword matching on the transaction
description — no ML model, no external data. ``spending_insights``
aggregates those categories into totals and plain-language notes.
"""

from __future__ import annotations

from datetime import datetime

CATEGORIES = (
    "groceries",
    "transport",
    "dining",
    "utilities",
    "entertainment",
    "salary",
    "transfer",
    "other",
)

# Checked in order: earlier groups win when keywords overlap
# (e.g. "Uber Eats" is dining, not transport).
_KEYWORDS = (
    ("salary", ("salary", "payroll", "wages", "pay cheque", "paycheck")),
    ("dining", ("restaurant", "cafe", "coffee", "starbucks", "mcdonald",
                "pizza", "burger", "dining", "takeaway", "uber eats",
                "deliveroo", "doordash", "bakery", "sandwich")),
    ("groceries", ("supermarket", "grocery", "groceries", "tesco", "asda",
                   "sainsbury", "morrisons", "aldi", "lidl", "kroger",
                   "whole foods", "trader joe", "safeway", "food market",
                   "walmart")),
    ("transport", ("uber", "lyft", "taxi", "bus fare", "train", "metro",
                   "fuel", "petrol", "gas station", "shell", "parking",
                   "airline", "flight", "toll", "car rental")),
    ("utilities", ("electric", "electricity", "water bill", "gas bill",
                   "internet", "broadband", "phone bill", "mobile bill",
                   "utility", "utilities", "council tax")),
    ("entertainment", ("netflix", "spotify", "cinema", "movie", "concert",
                        "theatre", "theater", "gaming", "steam", "disney",
                        "hulu", "gym", "streaming")),
    ("transfer", ("transfer", "venmo", "zelle", "paypal", "sent to",
                  "bank transfer", "wire transfer")),
)


def categorise(description):
    """Categorise a transaction description by keyword rules.

    Returns one of ``CATEGORIES``; anything unmatched is ``"other"``.
    """
    text = (description or "").lower()
    for category, keywords in _KEYWORDS:
        for keyword in keywords:
            if keyword in text:
                return category
    return "other"


def _parse_month(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m")
    if isinstance(value, str):
        text = value.strip()
        if len(text) >= 7:
            candidate = text[:7]
            try:
                datetime.strptime(candidate, "%Y-%m")
                return candidate
            except ValueError:
                pass
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).strftime("%Y-%m")
        except ValueError:
            return None
    return None


def _amount(txn):
    try:
        return float(txn.get("amount", 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def spending_insights(transactions):
    """Summarise a list of transaction dicts.

    Each transaction may carry ``amount``, ``description`` and
    ``timestamp``/``date``; an explicit ``category`` is honoured only
    if it is one of ``CATEGORIES``, otherwise ``categorise`` is used.

    Returns a dict::

        {
            "totals_by_category": {category: total, ...},
            "top_categories": [{"category": str, "total": float}, ...],
                # spending categories only (salary excluded), largest first
            "month_total": float,   # non-salary total for the latest month
            "monthly_totals": {month: total, ...},  # non-salary, by YYYY-MM
            "transaction_count": int,
            "insights": [str, ...],  # plain-language notes
        }

    ``month_total`` uses the latest month present in the data; when no
    transaction carries a date, all transactions count as one period.
    """
    transactions = list(transactions or [])
    totals = {}
    monthly = {}
    for txn in transactions:
        category = txn.get("category")
        if category not in CATEGORIES:
            category = categorise(txn.get("description", ""))
        amount = _amount(txn)
        totals[category] = totals.get(category, 0.0) + amount
        if category != "salary":
            month = _parse_month(txn.get("timestamp", txn.get("date")))
            key = month or "undated"
            monthly[key] = monthly.get(key, 0.0) + amount

    totals = {cat: round(total, 2) for cat, total in totals.items()}
    monthly = {month: round(total, 2) for month, total in monthly.items()}

    spending_totals = {c: t for c, t in totals.items() if c != "salary"}
    top_categories = [
        {"category": cat, "total": total}
        for cat, total in sorted(spending_totals.items(), key=lambda kv: -kv[1])
        if total != 0
    ]
    # Latest dated month wins; "undated" only if nothing is dated.
    dated_months = sorted(m for m in monthly if m != "undated")
    if dated_months:
        latest_month = dated_months[-1]
    elif monthly:
        latest_month = "undated"
    else:
        latest_month = None
    month_total = monthly.get(latest_month, 0.0) if latest_month else 0.0

    insights = []
    if not transactions:
        insights.append("No transactions to analyse.")
        return {
            "totals_by_category": totals,
            "top_categories": top_categories,
            "month_total": month_total,
            "monthly_totals": monthly,
            "transaction_count": 0,
            "insights": insights,
        }

    if top_categories:
        top = top_categories[0]
        insights.append(
            f"Your largest spending category is {top['category']} "
            f"({top['total']:.2f})."
        )
        total_spending = sum(t for t in spending_totals.values())
        if total_spending > 0 and top["total"] / total_spending >= 0.5:
            share = top["total"] / total_spending * 100
            insights.append(
                f"{top['category'].capitalize()} accounts for {share:.0f}% "
                "of your spending."
            )
    if latest_month and latest_month != "undated" and len(dated_months) >= 2:
        prior = [monthly[m] for m in dated_months[:-1]]
        average_prior = sum(prior) / len(prior) if prior else 0.0
        if average_prior > 0:
            if month_total >= 1.5 * average_prior:
                insights.append(
                    f"Spending spiked in {latest_month} ({month_total:.2f}), "
                    f"compared with an average of {average_prior:.2f} in "
                    "earlier months."
                )
            elif month_total >= 1.25 * average_prior:
                insights.append(
                    f"Spending in {latest_month} ({month_total:.2f}) was "
                    f"higher than your earlier monthly average "
                    f"({average_prior:.2f})."
                )
            elif month_total < 0.75 * average_prior:
                insights.append(
                    f"Spending in {latest_month} ({month_total:.2f}) was "
                    f"lower than your earlier monthly average "
                    f"({average_prior:.2f})."
                )
    if totals.get("salary"):
        insights.append(f"Income recorded as salary totals {totals['salary']:.2f}.")
    if not insights:
        insights.append("No unusual spending pattern stood out.")

    return {
        "totals_by_category": totals,
        "top_categories": top_categories,
        "month_total": round(month_total, 2),
        "monthly_totals": monthly,
        "transaction_count": len(transactions),
        "insights": insights,
    }
