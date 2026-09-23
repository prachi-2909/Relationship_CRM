"""Phone number normalization - used both for Official.phone matching and for
the caller number a Knowlarity webhook delivers, so the two sides compare
apples to apples regardless of formatting (+91, spaces, dashes, a leading 0).
"""

from __future__ import annotations

import re

_NON_DIGITS = re.compile(r"[^0-9]")


def normalize(raw: str | None) -> str:
    """Returns the last 10 digits of a phone number, stripping everything
    else (spaces, dashes, +91, a leading trunk 0). Empty/None input -> "".
    Not a full E.164 implementation - just enough to compare two Indian
    mobile numbers written differently.
    """
    if not raw:
        return ""
    digits = _NON_DIGITS.sub("", raw)
    if digits.startswith("0") and len(digits) > 10:
        digits = digits.lstrip("0")
    return digits[-10:] if len(digits) >= 10 else digits
