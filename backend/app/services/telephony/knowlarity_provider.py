"""Wraps the existing, untouched Knowlarity client - no behavior change."""

from __future__ import annotations

from .. import knowlarity


class KnowlarityTelephonyProvider:
    def initiate_call(self, dc_number: str | None, customer_number: str) -> str | None:
        return knowlarity.trigger_click_to_call(dc_number or "", customer_number)
