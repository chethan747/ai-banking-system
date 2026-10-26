"""Transparent feature-based credit scoring (demo only, stdlib only).

The score is built from a fixed base plus one contribution per input
feature. Every contribution is reported, so the result is never a
black box: the sum of the contributions plus the base equals the score
(before clamping to the 300-850 scale).

This is an ILLUSTRATIVE educational model. It is NOT a regulated
credit decision, NOT a real credit bureau score, and must not be used
to approve or decline real lending.

Features (all optional, missing values default to 0):
    income: annual income (same currency throughout)
    monthly_debt: total monthly debt payments
    employment_years: years in current employment
    past_defaults: number of past defaults / missed-payment events
    open_loans: number of currently open loans
    savings_balance: current savings balance
"""

from __future__ import annotations

_BASE_SCORE = 350
_MIN_SCORE = 300
_MAX_SCORE = 850


def band_for_score(score):
    """Map a 300-850 score to its band."""
    if score >= 750:
        return "Excellent"
    if score >= 650:
        return "Good"
    if score >= 550:
        return "Fair"
    return "Poor"


def _num(features, key):
    try:
        value = float(features.get(key, 0) or 0)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, value)


def credit_score(features):
    """Score a feature dict on the 300-850 scale.

    Returns a dict::

        {
            "score": int,            # clamped to 300-850
            "band": "Poor"|"Fair"|"Good"|"Excellent",
            "reasons": [str, ...],   # one per factor, with +/- points
            "contributions": [       # machine-readable form of reasons
                {"factor": str, "points": int, "detail": str}, ...
            ],
            "base_score": 350,
        }

    ``base_score + sum(contribution points)`` equals ``score`` unless
    clamping at 300/850 applied (which is stated in no contribution;
    clamped scores sit exactly on a bound).
    """
    features = dict(features or {})
    income = _num(features, "income")
    monthly_debt = _num(features, "monthly_debt")
    employment_years = _num(features, "employment_years")
    past_defaults = int(_num(features, "past_defaults"))
    open_loans = int(_num(features, "open_loans"))
    savings_balance = _num(features, "savings_balance")

    contributions = []

    # Income (annual).
    if income >= 100000:
        points, detail = 120, f"High annual income ({income:.0f})."
    elif income >= 60000:
        points, detail = 90, f"Annual income ({income:.0f})."
    elif income >= 40000:
        points, detail = 70, f"Moderate annual income ({income:.0f})."
    elif income >= 25000:
        points, detail = 45, f"Lower annual income ({income:.0f})."
    elif income >= 10000:
        points, detail = 20, f"Low annual income ({income:.0f})."
    else:
        points, detail = 0, "No / very low reported income (0 points)."
    contributions.append({"factor": "income", "points": points, "detail": detail})

    # Debt burden: monthly debt as a share of monthly income.
    if income > 0:
        dti = monthly_debt / (income / 12.0)
        if dti <= 0.20:
            points, detail = 100, f"Low debt burden ({dti:.0%} of monthly income)."
        elif dti <= 0.35:
            points, detail = 70, f"Moderate debt burden ({dti:.0%} of monthly income)."
        elif dti <= 0.50:
            points, detail = 30, f"Elevated debt burden ({dti:.0%} of monthly income)."
        elif dti <= 0.65:
            points, detail = -30, f"High debt burden ({dti:.0%} of monthly income)."
        else:
            points, detail = -80, f"Very high debt burden ({dti:.0%} of monthly income)."
    else:
        points, detail = -30, "Debt burden cannot be assessed without income."
    contributions.append({"factor": "monthly_debt", "points": points, "detail": detail})

    # Employment stability.
    if employment_years >= 10:
        points, detail = 70, f"Long employment history ({employment_years:.0f} years)."
    elif employment_years >= 5:
        points, detail = 55, f"Stable employment history ({employment_years:.0f} years)."
    elif employment_years >= 3:
        points, detail = 40, f"Employment history ({employment_years:.0f} years)."
    elif employment_years >= 1:
        points, detail = 20, f"Short employment history ({employment_years:.0f} years)."
    else:
        points, detail = 0, "No employment history reported (0 points)."
    contributions.append({"factor": "employment_years", "points": points, "detail": detail})

    # Past defaults.
    if past_defaults == 0:
        points, detail = 90, "No past defaults."
    elif past_defaults == 1:
        points, detail = -60, "1 past default."
    elif past_defaults == 2:
        points, detail = -120, "2 past defaults."
    else:
        points, detail = -170, f"{past_defaults} past defaults."
    contributions.append({"factor": "past_defaults", "points": points, "detail": detail})

    # Open loans.
    if open_loans == 0:
        points, detail = 50, "No open loans."
    elif open_loans == 1:
        points, detail = 30, "1 open loan."
    elif open_loans == 2:
        points, detail = 10, "2 open loans."
    elif open_loans == 3:
        points, detail = -15, "3 open loans."
    else:
        points, detail = -40, f"{open_loans} open loans."
    contributions.append({"factor": "open_loans", "points": points, "detail": detail})

    # Savings buffer.
    if savings_balance >= 50000:
        points, detail = 90, f"Large savings balance ({savings_balance:.0f})."
    elif savings_balance >= 20000:
        points, detail = 70, f"Healthy savings balance ({savings_balance:.0f})."
    elif savings_balance >= 10000:
        points, detail = 50, f"Savings balance ({savings_balance:.0f})."
    elif savings_balance >= 5000:
        points, detail = 30, f"Modest savings balance ({savings_balance:.0f})."
    elif savings_balance >= 1000:
        points, detail = 15, f"Small savings balance ({savings_balance:.0f})."
    else:
        points, detail = 0, "No / very low savings balance (0 points)."
    contributions.append({"factor": "savings_balance", "points": points, "detail": detail})

    raw = _BASE_SCORE + sum(c["points"] for c in contributions)
    score = max(_MIN_SCORE, min(_MAX_SCORE, int(raw)))
    reasons = [
        f"{c['points']:+d} points: {c['detail']}" for c in contributions
    ]
    return {
        "score": score,
        "band": band_for_score(score),
        "reasons": reasons,
        "contributions": contributions,
        "base_score": _BASE_SCORE,
    }
