"""The one operation that's genuinely pluggable server-side: triggering an
outgoing call. Everything downstream (status, recording, transcript, AI brief,
human review, CRM logging) already operates on CallSession/CallTranscript and
is channel-agnostic - it needs no provider interface at all.
"""

from __future__ import annotations

from typing import Protocol


class TelephonyProvider(Protocol):
    def initiate_call(self, dc_number: str | None, customer_number: str) -> str | None:
        """Places (or arranges to place) a call from dc_number to customer_number.
        Returns a provider-specific call reference to store for idempotency/lookup,
        or None if no call was actually triggered by this call (either the provider
        is unconfigured/failed, or - for native mode - there's nothing to trigger
        here at all; the device will place the call itself)."""
        ...
