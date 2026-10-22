"""Telephony provider abstraction: who places an outgoing call.

Knowlarity and Android-native are NOT symmetric. For Knowlarity, this backend
triggers the call via an external API and later receives a webhook. For native
mode, the call is placed and observed entirely on the DC's device - this
backend's only job is to record the session and later accept a completion
report (see services/call_intelligence.py::complete_native_call). So the only
piece that's genuinely pluggable server-side is "trigger an outgoing call, if
there's anything to trigger at all" - that's all TelephonyProvider covers.
"""

from __future__ import annotations

from ...config import Settings
from .base import TelephonyProvider
from .knowlarity_provider import KnowlarityTelephonyProvider
from .native_provider import NativeTelephonyProvider

__all__ = ["TelephonyProvider", "telephony_provider_for"]


def telephony_provider_for(settings: Settings) -> TelephonyProvider:
    if settings.telephony_provider == "android_native":
        return NativeTelephonyProvider()
    return KnowlarityTelephonyProvider()
