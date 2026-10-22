"""Android-native mode: the DC's own device places the call via its SIM, not
this backend. There is nothing to trigger server-side - the Android app dials
after seeing channel="android_native" in the /calls/outgoing response, then
reports the outcome via POST /calls/{id}/native/complete."""

from __future__ import annotations


class NativeTelephonyProvider:
    def initiate_call(self, dc_number: str | None, customer_number: str) -> str | None:
        return None
