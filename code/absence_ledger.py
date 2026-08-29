"""
Absence Ledger: deterministic statement of what a confirmed diversion left
unfunded, in the institution's own CPD terms.

Constitutional rules of this module, enforced by tests:
1. Never estimate consequence. Every value is arithmetic over fields the CPD
   itself states, with the CPD cited, or it is None.
2. None means "not stated in CPD" and is never rendered as zero.
3. No wall clock. All durations compute against an explicit as_of date.
"""

from typing import Any


def _get_absence_param(obj: Any, param: str, default: Any = None) -> Any:
    """
    Safely retrieve an absence-related parameter from a CPD object.

    Mirrors _get_delivery_param: absence fields are added to CPDOutputTarget
    additively, and any profile-like object lacking them still works. A
    missing attribute returns the default, which for absence semantics is
    None ("not stated in CPD"), never zero.
    """
    return getattr(obj, param, default)
