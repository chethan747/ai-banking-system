"""AI Engine for the AI banking system demo.

Pure Python (standard library only) — no numpy, scikit-learn or any
external ML library. Every model here is a transparent, rule-based,
illustrative demo: scores are NOT regulated credit decisions and are
NOT real fraud-detection accuracy claims. Demo data only.

Public API:
    fraud:      score_transaction, review_queue, FRAUD_THRESHOLD
    credit:     credit_score, band_for_score
    insights:   categorise, spending_insights, CATEGORIES
    assistant:  answer_question, FAQ
"""

from .fraud import FRAUD_THRESHOLD, review_queue, score_transaction
from .credit import band_for_score, credit_score
from .insights import CATEGORIES, categorise, spending_insights
from .assistant import FAQ, answer_question

__all__ = [
    "FRAUD_THRESHOLD",
    "review_queue",
    "score_transaction",
    "band_for_score",
    "credit_score",
    "CATEGORIES",
    "categorise",
    "spending_insights",
    "FAQ",
    "answer_question",
]
