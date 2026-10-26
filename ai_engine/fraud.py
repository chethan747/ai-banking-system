"""Transparent rule-based fraud scoring (demo only, stdlib only).

The score is a sum of explainable rule contributions, capped at 100.
It is an illustrative demo model, NOT a production fraud detector and
it makes no accuracy claims.

Rules (all contributions are reported in ``reasons``):
  * Large amount vs the account's typical (median) amount.
  * High velocity: many transactions in the 60 minutes before this one.
  * Unusual hour: 00:00-04:59.
  * Rapid repeated amounts: the same amount appearing repeatedly in
    the previous 24 hours.
  * New/unusual location or category never seen in the history.

A transaction is flagged when ``score >= FRAUD_THRESHOLD`` (70).
"""

from __future__ import annotations

from datetime import datetime, timezone

FRAUD_THRESHOLD = 70
_UNUSUAL_HOURS = set(range(0, 5))  # 00:00-04:59


def _parse_timestamp(value):
    """Parse a datetime, ISO string, or epoch seconds/ms to a datetime.

    Returns None when the value is missing or unparseable; rules that
    need a timestamp are then simply skipped (never guessed).
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    if isinstance(value, (int, float)):
        seconds = float(value)
        if seconds > 1e11:  # milliseconds
            seconds /= 1000.0
        try:
            return datetime.fromtimestamp(seconds, tz=timezone.utc).replace(tzinfo=None)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed
        except ValueError:
            pass
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
    return None


def _median(values):
    ordered = sorted(values)
    n = len(ordered)
    if n == 0:
        return 0.0
    mid = n // 2
    if n % 2:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def _same_account_history(txn, history):
    account_id = txn.get("account_id")
    if account_id is None:
        return list(history)
    kept = []
    for item in history or []:
        other = item.get("account_id")
        if other is None or other == account_id:
            kept.append(item)
    return kept


def score_transaction(txn, history):
    """Score one transaction against prior history.

    Args:
        txn: dict with ``amount`` and optionally ``account_id``,
            ``timestamp``, ``location`` and ``category``.
        history: list of prior transaction dicts (same shape).

    Returns:
        ``(score, flagged, reasons)`` where ``score`` is an int 0-100,
        ``flagged`` is ``score >= 70``, and ``reasons`` is a list of
        plain-language strings, one per rule that contributed.
    """
    history = list(history or [])
    same_account = _same_account_history(txn, history)
    try:
        amount = float(txn.get("amount", 0) or 0)
    except (TypeError, ValueError):
        amount = 0.0
    txn_time = _parse_timestamp(txn.get("timestamp"))
    score = 0
    reasons = []

    # 1. Large amount vs typical (median) amount for this account.
    amounts = []
    for item in same_account:
        try:
            amounts.append(float(item.get("amount", 0) or 0))
        except (TypeError, ValueError):
            continue
    typical = _median(amounts)
    if typical > 0 and amount > 0:
        ratio = amount / typical
        if ratio >= 10:
            score += 45
            reasons.append(
                f"Amount {amount:.2f} is {ratio:.1f}x your typical "
                f"amount ({typical:.2f})."
            )
        elif ratio >= 5:
            score += 35
            reasons.append(
                f"Amount {amount:.2f} is {ratio:.1f}x your typical "
                f"amount ({typical:.2f})."
            )
        elif ratio >= 3:
            score += 25
            reasons.append(
                f"Amount {amount:.2f} is {ratio:.1f}x your typical "
                f"amount ({typical:.2f})."
            )
        elif ratio >= 2:
            score += 15
            reasons.append(
                f"Amount {amount:.2f} is {ratio:.1f}x your typical "
                f"amount ({typical:.2f})."
            )
    elif not amounts and amount >= 10000:
        score += 10
        reasons.append(
            "No prior history to compare against and the amount is "
            f"large ({amount:.2f})."
        )

    # 2. High velocity: transactions in the 60 minutes before this one.
    if txn_time is not None:
        recent = 0
        for item in same_account:
            other_time = _parse_timestamp(item.get("timestamp"))
            if other_time is None:
                continue
            delta_minutes = (txn_time - other_time).total_seconds() / 60.0
            if 0 < delta_minutes <= 60:
                recent += 1
        if recent >= 10:
            score += 35
            reasons.append(f"High velocity: {recent} transactions in the last hour.")
        elif recent >= 5:
            score += 25
            reasons.append(f"High velocity: {recent} transactions in the last hour.")
        elif recent >= 3:
            score += 15
            reasons.append(f"Elevated velocity: {recent} transactions in the last hour.")

        # 4. Rapid repeated amounts in the previous 24 hours.
        same_amount = 0
        for item in same_account:
            other_time = _parse_timestamp(item.get("timestamp"))
            if other_time is None:
                continue
            delta_hours = (txn_time - other_time).total_seconds() / 3600.0
            if 0 < delta_hours <= 24:
                try:
                    if float(item.get("amount", 0) or 0) == amount and amount != 0:
                        same_amount += 1
                except (TypeError, ValueError):
                    continue
        if same_amount >= 3:
            score += 20
            reasons.append(
                f"Repeated amount: {amount:.2f} also appeared "
                f"{same_amount} times in the last 24 hours."
            )
        elif same_amount == 2:
            score += 10
            reasons.append(
                f"Repeated amount: {amount:.2f} also appeared "
                "2 times in the last 24 hours."
            )
    else:
        # No timestamp: fall back to counting repeated amounts in all history.
        same_amount = 0
        for item in same_account:
            try:
                if float(item.get("amount", 0) or 0) == amount and amount != 0:
                    same_amount += 1
            except (TypeError, ValueError):
                continue
        if same_amount >= 3:
            score += 20
            reasons.append(
                f"Repeated amount: {amount:.2f} also appeared "
                f"{same_amount} times in prior history."
            )

    # 3. Unusual hour.
    if txn_time is not None and txn_time.hour in _UNUSUAL_HOURS:
        score += 15
        reasons.append(f"Unusual hour: transaction at {txn_time.hour:02d}:00.")

    # 5. New/unusual location or category.
    location = txn.get("location")
    if location:
        seen_locations = {item.get("location") for item in same_account if item.get("location")}
        if seen_locations and location not in seen_locations:
            score += 15
            reasons.append(f"New location not seen before: {location}.")
    category = txn.get("category")
    if category:
        seen_categories = {item.get("category") for item in same_account if item.get("category")}
        if seen_categories and category not in seen_categories:
            score += 10
            reasons.append(f"Unusual category not seen before: {category}.")

    score = max(0, min(100, int(score)))
    return score, score >= FRAUD_THRESHOLD, reasons


def review_queue(transactions, history=None):
    """Return the flagged items from a list of transactions.

    Each item may be:
      * a raw transaction dict — it is scored with ``score_transaction``
        against ``history`` (which may also be a dict mapping
        ``account_id`` -> history list), or
      * a dict already carrying ``flagged`` (bool) and/or ``score``,
        or
      * a tuple/list ``(txn, score, flagged, reasons)``.

    Flagged items are returned exactly as supplied, in input order.
    """
    flagged_items = []
    for item in transactions or []:
        txn = item
        flagged = None
        score = None
        if isinstance(item, (tuple, list)) and len(item) >= 3:
            txn, score, flagged = item[0], item[1], item[2]
        elif isinstance(item, dict):
            txn = item.get("transaction", item) if isinstance(item.get("transaction"), dict) else item
            if "flagged" in item:
                flagged = bool(item["flagged"])
            elif "score" in item:
                score = item["score"]
        if flagged is None:
            if score is not None:
                try:
                    flagged = float(score) >= FRAUD_THRESHOLD
                except (TypeError, ValueError):
                    flagged = False
            else:
                hist = history
                if isinstance(history, dict) and isinstance(txn, dict):
                    hist = history.get(txn.get("account_id"), [])
                _, flagged, _ = score_transaction(txn, hist)
        if flagged:
            flagged_items.append(item)
    return flagged_items
