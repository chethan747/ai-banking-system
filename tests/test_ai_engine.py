"""Tests for ai_engine (Module 2) — stdlib unittest only.

Run from ~/workspace/ai-banking-system/ with:
    python3 -m unittest discover -s tests -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ai_engine.assistant import FAQ, answer_question
from ai_engine.credit import band_for_score, credit_score
from ai_engine.fraud import review_queue, score_transaction
from ai_engine.insights import categorise, spending_insights


def _history(amounts, day="2026-10-20", hour=12, location="Chicago", category="groceries"):
    return [
        {
            "amount": a,
            "account_id": "acc-1",
            "timestamp": f"{day}T{hour:02d}:00:00",
            "location": location,
            "category": category,
        }
        for a in amounts
    ]


class TestFraud(unittest.TestCase):
    def test_flags_large_unusual_transaction(self):
        history = _history([45.0, 50.0, 55.0, 48.0, 52.0])
        txn = {
            "amount": 5000.0,
            "account_id": "acc-1",
            "timestamp": "2026-10-20T02:30:00",
            "location": "Lagos",
            "category": "electronics",
        }
        score, flagged, reasons = score_transaction(txn, history)
        self.assertGreaterEqual(score, 70)
        self.assertTrue(flagged)
        self.assertTrue(reasons)
        self.assertTrue(any("typical" in r for r in reasons))

    def test_does_not_flag_normal_transaction(self):
        history = _history([45.0, 50.0, 55.0, 48.0, 52.0])
        txn = {
            "amount": 51.0,
            "account_id": "acc-1",
            # Next day, so the prior day's history is not "last hour".
            "timestamp": "2026-10-21T12:30:00",
            "location": "Chicago",
            "category": "groceries",
        }
        score, flagged, reasons = score_transaction(txn, history)
        self.assertLess(score, 70)
        self.assertFalse(flagged)

    def test_velocity_flagging(self):
        # 8 varied-amount transactions in the hour before a 9th: the
        # velocity reason must appear and the score must rise versus a
        # quiet history (velocity alone does not auto-flag; it adds 25).
        base_history = _history([40.0, 45.0, 55.0, 60.0, 48.0, 52.0, 47.0, 53.0], hour=12)
        # Rewrite timestamps to 11:05-11:47 on the same day.
        for i, item in enumerate(base_history):
            item["timestamp"] = f"2026-10-20T11:{5 + i * 6:02d}:00"
        txn = {
            "amount": 99.0,  # 1.98x the median: below the 2x amount threshold
            "account_id": "acc-1",
            "timestamp": "2026-10-20T12:00:00",
            "location": "Chicago",
            "category": "groceries",
        }
        score, _flagged, reasons = score_transaction(txn, base_history)
        self.assertTrue(any("velocity" in r for r in reasons))
        quiet_score, _, _ = score_transaction(txn, _history([50.0]))
        self.assertGreater(score, quiet_score)

    def test_velocity_plus_large_amount_flags(self):
        history = _history([50.0] * 6, hour=12)
        for i, item in enumerate(history):
            item["timestamp"] = f"2026-10-20T11:{10 + i * 8:02d}:00"
        txn = {
            "amount": 500.0,  # 10x typical -> 45, plus velocity 25 = 70
            "account_id": "acc-1",
            "timestamp": "2026-10-20T12:00:00",
            "location": "Chicago",
            "category": "groceries",
        }
        score, flagged, reasons = score_transaction(txn, history)
        self.assertGreaterEqual(score, 70)
        self.assertTrue(flagged)
        self.assertTrue(any("velocity" in r for r in reasons))

    def test_review_queue_filters_flagged_only(self):
        history = _history([50.0] * 5)
        normal = {
            "amount": 51.0, "account_id": "acc-1",
            "timestamp": "2026-10-21T12:30:00",
            "location": "Chicago", "category": "groceries",
        }
        suspicious = {
            "amount": 5000.0, "account_id": "acc-1",
            "timestamp": "2026-10-20T02:30:00",
            "location": "Lagos", "category": "electronics",
        }
        queue = review_queue([normal, suspicious], history=history)
        self.assertEqual(queue, [suspicious])

    def test_review_queue_accepts_prescored_items(self):
        queue = review_queue([
            {"amount": 10.0, "score": 85},
            {"amount": 20.0, "score": 10},
            {"amount": 30.0, "flagged": True},
        ])
        self.assertEqual(len(queue), 2)

    def test_score_always_in_range(self):
        score, _, _ = score_transaction(
            {"amount": 999999.0, "timestamp": "2026-10-20T03:00:00",
             "location": "Nowhere", "category": "other"},
            _history([10.0] * 20),
        )
        self.assertTrue(0 <= score <= 100)


class TestCredit(unittest.TestCase):
    BASE = {
        "income": 60000, "monthly_debt": 500, "employment_years": 5,
        "past_defaults": 0, "open_loans": 1, "savings_balance": 10000,
    }

    def test_score_in_range_with_band_and_reasons(self):
        result = credit_score(self.BASE)
        self.assertTrue(300 <= result["score"] <= 850)
        self.assertIn(result["band"], ("Poor", "Fair", "Good", "Excellent"))
        self.assertEqual(result["band"], band_for_score(result["score"]))
        self.assertTrue(result["reasons"])
        # Every contribution is explained in a reason.
        self.assertEqual(len(result["reasons"]), len(result["contributions"]))
        self.assertEqual(
            result["base_score"] + sum(c["points"] for c in result["contributions"]),
            result["score"],
        )

    def test_rises_with_income(self):
        low = credit_score({**self.BASE, "income": 20000})
        high = credit_score(self.BASE)
        self.assertGreater(high["score"], low["score"])

    def test_rises_with_savings(self):
        low = credit_score({**self.BASE, "savings_balance": 500})
        high = credit_score({**self.BASE, "savings_balance": 50000})
        self.assertGreater(high["score"], low["score"])

    def test_falls_with_defaults(self):
        clean = credit_score(self.BASE)
        defaulted = credit_score({**self.BASE, "past_defaults": 2})
        self.assertGreater(clean["score"], defaulted["score"])

    def test_falls_with_debt(self):
        light = credit_score(self.BASE)
        heavy = credit_score({**self.BASE, "monthly_debt": 3000})
        self.assertGreater(light["score"], heavy["score"])

    def test_mixed_profile_has_positive_and_negative_reasons(self):
        result = credit_score({**self.BASE, "past_defaults": 1, "monthly_debt": 3000})
        self.assertTrue(any(r.startswith("+") for r in result["reasons"]))
        self.assertTrue(any(r.startswith("-") for r in result["reasons"]))


class TestInsights(unittest.TestCase):
    def test_categorise_at_least_eight_descriptions(self):
        cases = {
            "Tesco supermarket weekly shop": "groceries",
            "Uber ride downtown": "transport",
            "Starbucks coffee": "dining",
            "Electricity bill": "utilities",
            "Netflix subscription": "entertainment",
            "Monthly salary payment": "salary",
            "Transfer to John": "transfer",
            "Some random unrecognised thing xyz": "other",
            "Uber Eats dinner": "dining",
            "Shell petrol station": "transport",
        }
        for description, expected in cases.items():
            with self.subTest(description=description):
                self.assertEqual(categorise(description), expected)

    def test_spending_insights_totals_and_top(self):
        txns = [
            {"amount": 120.0, "description": "Tesco supermarket", "timestamp": "2026-10-05T10:00:00"},
            {"amount": 80.0, "description": "Tesco supermarket", "timestamp": "2026-10-12T10:00:00"},
            {"amount": 60.0, "description": "Starbucks coffee", "timestamp": "2026-10-13T09:00:00"},
            {"amount": 40.0, "description": "Uber ride", "timestamp": "2026-10-14T18:00:00"},
        ]
        result = spending_insights(txns)
        self.assertEqual(result["totals_by_category"]["groceries"], 200.0)
        self.assertEqual(result["totals_by_category"]["dining"], 60.0)
        self.assertEqual(result["totals_by_category"]["transport"], 40.0)
        self.assertEqual(result["top_categories"][0]["category"], "groceries")
        self.assertEqual(result["month_total"], 300.0)
        self.assertTrue(any("groceries" in insight for insight in result["insights"]))

    def test_spending_insights_spike_vs_average(self):
        txns = [
            {"amount": 100.0, "description": "Tesco supermarket", "timestamp": "2026-08-10T10:00:00"},
            {"amount": 100.0, "description": "Tesco supermarket", "timestamp": "2026-09-10T10:00:00"},
            {"amount": 400.0, "description": "Tesco supermarket", "timestamp": "2026-10-10T10:00:00"},
        ]
        result = spending_insights(txns)
        self.assertTrue(any("spiked" in insight for insight in result["insights"]))

    def test_spending_insights_empty(self):
        result = spending_insights([])
        self.assertEqual(result["month_total"], 0.0)
        self.assertEqual(result["transaction_count"], 0)
        self.assertTrue(result["insights"])


class TestAssistant(unittest.TestCase):
    def test_faq_covers_required_topics(self):
        self.assertGreaterEqual(len(FAQ), 12)
        titles = " ".join(e["title"].lower() for e in FAQ)
        for topic in ("account", "transfer", "interest", "fraud", "loan", "kyc", "statement"):
            self.assertIn(topic, titles)

    def test_answers_known_question_with_cited_source(self):
        answer, sources = answer_question("How do I open a savings account?")
        self.assertTrue(answer)
        self.assertTrue(sources)
        self.assertIn("Opening an account", sources)

    def test_answers_fraud_question(self):
        answer, sources = answer_question("What happens if my transaction is flagged for fraud?")
        self.assertTrue(sources)
        self.assertIn("fraud", answer.lower())

    def test_declines_unknown_question_gracefully(self):
        answer, sources = answer_question("What is the capital of France?")
        self.assertEqual(sources, [])
        self.assertIn("don't have an answer", answer)
        self.assertIn("transfers", answer)  # suggests topics

    def test_declines_unrelated_question(self):
        answer, sources = answer_question("Tell me about quantum computing and Mars weather")
        self.assertEqual(sources, [])
        self.assertIn("don't have an answer", answer)


if __name__ == "__main__":
    unittest.main()
