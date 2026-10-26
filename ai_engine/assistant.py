"""Banking assistant over a built-in FAQ (demo only, stdlib only).

Answers come ONLY from the FAQ below, matched by keyword overlap.
If no FAQ entry matches well enough, the assistant says so and
suggests topics instead of inventing a policy, rate, or figure.
No answer here states a real bank's policy or a specific rate/fee:
wording is generic and demo-scoped on purpose.
"""

from __future__ import annotations

import re

_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "do", "does", "did",
    "how", "what", "why", "when", "where", "which", "who", "can", "could",
    "should", "would", "i", "my", "me", "we", "you", "your", "to", "of",
    "for", "on", "in", "at", "with", "about", "please", "tell", "get",
    "and", "or", "if", "it", "its", "this", "that", "am",
}

# A single distinctive keyword is enough for these topics; otherwise
# at least two keyword matches are required (see answer_question).
_DISTINCTIVE = {"kyc", "overdraft", "fraud", "statement", "interest", "loan"}

FAQ = [
    {
        "title": "Opening an account",
        "keywords": {"open", "opening", "account", "new", "sign", "create", "savings", "checking", "current"},
        "answer": (
            "To open an account in this demo system, choose the account type "
            "(for example savings or checking), provide your name and contact "
            "details, and complete identity verification. A real bank would "
            "also confirm its own eligibility and documentation requirements."
        ),
    },
    {
        "title": "Savings account interest",
        "keywords": {"interest", "savings", "earn", "rate", "apy", "balance"},
        "answer": (
            "Interest on a savings account is typically calculated on your "
            "balance over time and credited periodically. This demo does not "
            "quote a specific rate: a real rate depends on the account and "
            "the bank's current terms, so check those terms before relying "
            "on any figure."
        ),
    },
    {
        "title": "Transferring money",
        "keywords": {"transfer", "send", "money", "payment", "pay", "recipient"},
        "answer": (
            "To transfer money, enter the recipient's account details and "
            "the amount, then confirm the transfer. Transfers between accounts "
            "at the same bank are usually fast, while transfers to another "
            "bank can take longer depending on the transfer method used."
        ),
    },
    {
        "title": "Transfer limits",
        "keywords": {"limit", "limits", "transfer", "maximum", "daily"},
        "answer": (
            "Transfer limits cap how much can be sent in a single transfer or "
            "in one day. Limits vary by account type and bank, and this demo "
            "does not set a real limit — check the account terms for the "
            "limit that applies to you."
        ),
    },
    {
        "title": "Fraud flags on transactions",
        "keywords": {"fraud", "flag", "flagged", "suspicious", "blocked", "transaction"},
        "answer": (
            "A transaction may be flagged for possible fraud when it looks "
            "unusual compared with "
            "your normal activity — for example a much larger amount than "
            "usual, many transactions in a short time, or a new location. "
            "If a transaction of yours is flagged, review it and confirm "
            "whether you recognise it; contact the bank if you do not."
        ),
    },
    {
        "title": "Reporting fraud or a lost card",
        "keywords": {"fraud", "report", "lost", "stolen", "card", "unauthorised", "unauthorized"},
        "answer": (
            "If you spot a transaction you do not recognise, or your card is "
            "lost or stolen, report it to the bank as soon as possible and ask "
            "for the card to be blocked. Keep a note of the date, amount, and "
            "any reference the bank gives you."
        ),
    },
    {
        "title": "Loans",
        "keywords": {"loan", "borrow", "borrowing", "mortgage", "credit", "apply"},
        "answer": (
            "Applying for a loan usually involves stating the amount and "
            "purpose, and the lender assessing income, existing debts, and "
            "repayment history. This demo's credit score is illustrative only "
            "and is not a lending decision; a real lender applies its own "
            "criteria and terms."
        ),
    },
    {
        "title": "KYC and identity verification",
        "keywords": {"kyc", "identity", "verification", "verify", "document", "documents", "id"},
        "answer": (
            "KYC (Know Your Customer) checks confirm a customer's identity "
            "before an account is opened or certain services are offered. "
            "They typically involve a photo ID and proof of address; the "
            "exact documents accepted depend on the bank and local rules."
        ),
    },
    {
        "title": "Statements",
        "keywords": {"statement", "statements", "download", "history", "transactions"},
        "answer": (
            "A statement lists the transactions on your account over a chosen "
            "period, with the opening and closing balances. In this demo you "
            "can request a statement for a date range; a real bank also "
            "provides statements through its app or by post."
        ),
    },
    {
        "title": "Changing contact details",
        "keywords": {"address", "change", "contact", "details", "phone", "email", "update"},
        "answer": (
            "To change your contact details, update your address, phone number, "
            "or email in your account settings and confirm the change. Keeping "
            "these details current matters because the bank uses them for "
            "security checks and important notices."
        ),
    },
    {
        "title": "Closing an account",
        "keywords": {"close", "closing", "cancel", "account"},
        "answer": (
            "To close an account, first move or withdraw any remaining balance, "
            "cancel linked direct debits or standing orders, and then request "
            "closure. A real bank may ask you to settle outstanding charges "
            "before closure is completed."
        ),
    },
    {
        "title": "Account access and passwords",
        "keywords": {"password", "login", "access", "locked", "reset", "forgot"},
        "answer": (
            "If you cannot log in, use the password-reset option and follow "
            "the verification steps sent to your registered contact details. "
            "Never share your password or one-time code with anyone, including "
            "someone claiming to be from the bank."
        ),
    },
    {
        "title": "Overdrafts",
        "keywords": {"overdraft", "negative", "balance", "overdrawn"},
        "answer": (
            "An overdraft lets an account balance go below zero up to an "
            "agreed limit, usually with interest or fees. This demo does not "
            "set a real overdraft limit or fee — check the account terms, and "
            "avoid relying on an overdraft for regular spending."
        ),
    },
    {
        "title": "Direct debits and standing orders",
        "keywords": {"direct", "debit", "standing", "order", "recurring", "subscription"},
        "answer": (
            "A direct debit lets a company collect varying amounts from your "
            "account with your permission, while a standing order sends a fixed "
            "amount on a regular date that you control. You can usually cancel "
            "either before the next payment is due."
        ),
    },
]

_SUGGESTED_TOPICS = "accounts, transfers, interest, fraud flags, loans, KYC, and statements"


def _tokens(text):
    words = re.findall(r"[a-z]+", (text or "").lower())
    return {w for w in words if w not in _STOPWORDS}


def answer_question(question):
    """Answer a question from the built-in FAQ.

    Returns ``(answer_text, source_titles)``. When no FAQ entry
    matches well enough, the answer says so, lists topics the
    assistant can help with, and ``source_titles`` is empty — it
    never invents a policy or figure.
    """
    tokens = _tokens(question)
    if not tokens:
        return (
            "I don't have an answer for that in the demo knowledge base. "
            f"I can help with topics such as: {_SUGGESTED_TOPICS}. "
            "Try asking about one of those.",
            [],
        )
    best = None
    best_overlap = 0
    for entry in FAQ:
        overlap = entry["keywords"] & tokens
        count = len(overlap)
        if count > best_overlap:
            best, best_overlap, best_overlap_set = entry, count, overlap
    if best is None or best_overlap == 0:
        matched = False
    elif best_overlap >= 2:
        matched = True
    else:  # exactly one keyword matched
        matched = bool(best_overlap_set & _DISTINCTIVE)
    if not matched:
        return (
            "I don't have an answer for that in the demo knowledge base. "
            f"I can help with topics such as: {_SUGGESTED_TOPICS}. "
            "Try asking about one of those.",
            [],
        )
    return best["answer"], [best["title"]]
