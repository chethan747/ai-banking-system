"""Management & Compliance package (Module 3).

DEMONSTRATION / EDUCATIONAL SYSTEM ONLY -- NOT production banking
software. It is not PCI-DSS / SOC 2 compliant, makes no real payments,
has no bank partnerships, and must not be used with real people, real
government ID numbers, or real money. All seed/demo data is fictitious.

Submodules (stdlib only):
  auth    -- role-based access, salted PBKDF2 password hashing
  kyc     -- customer / KYC records (ID numbers stored only as hashes)
  loans   -- loan applications with manager/admin approval workflow
  audit   -- append-only, hash-chained audit log
  reports -- management reports over plain-list/dict inputs
"""

from .auth import AuthStore, create_user, verify_user, has_permission, ROLES, PERMISSIONS
from .kyc import CustomerStore, create_customer_record, get_customer_record, update_kyc_status, list_customer_records, hash_id_number, KYC_STATUSES
from .loans import LoanStore, apply_loan, review_loan, get_loan, list_loans
from .audit import AuditLog, append_event, verify_chain
from .reports import totals_report, flagged_report, loan_pipeline_report

__all__ = [
    "AuthStore", "create_user", "verify_user", "has_permission", "ROLES", "PERMISSIONS",
    "CustomerStore", "create_customer_record", "get_customer_record",
    "update_kyc_status", "list_customer_records", "hash_id_number", "KYC_STATUSES",
    "LoanStore", "apply_loan", "review_loan", "get_loan", "list_loans",
    "AuditLog", "append_event", "verify_chain",
    "totals_report", "flagged_report", "loan_pipeline_report",
]
