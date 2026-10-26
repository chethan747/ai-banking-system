"""Core banking package (demo only).

This is a self-contained, standard-library-only demo for an AI banking
system. It uses no real people, no real money, and no real account
numbers: account numbers generated here are local demo identifiers
prefixed ``DEMO-`` and must never be presented as real bank accounts.
"""

from .core import Bank

__all__ = ["Bank"]
