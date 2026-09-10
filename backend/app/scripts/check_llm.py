"""Check the configured LLM endpoint end to end.

    python -m app.scripts.check_llm

Prints the active config, then exercises both paths the app uses:
the free-form ``chat()`` helper (Relationship Brief narrative) and the
structured ``extract_interaction()`` (interaction notes -> fields).
Exits non-zero if an endpoint is configured but not usable.
"""

from __future__ import annotations

import sys

try:  # model output can contain characters the Windows console codec rejects
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from ..config import get_settings
from ..services import llm

_SAMPLE_NOTE = (
    "Call with the regional head. They were unhappy about the delayed settlement "
    "report and asked us to expedite it. I said we will share the corrected report "
    "by tomorrow and set up a weekly sync."
)


def main() -> int:
    s = get_settings()
    print("LLM_BASE_URL       :", s.llm_base_url or "(none - offline stub)")
    print("LLM_MODEL          :", s.llm_model)
    print("LLM_API_KEY set    :", bool(s.llm_api_key))
    print("LLM_TIMEOUT_SECONDS:", s.llm_timeout_seconds)
    print()

    if not s.llm_base_url:
        print("No endpoint configured - the app uses the deterministic stub.")
        print("Set LLM_BASE_URL / LLM_MODEL / LLM_API_KEY in backend/.env.")
        return 0

    if "groq.com" in s.llm_base_url and not s.llm_api_key:
        print("Groq endpoint is set but LLM_API_KEY is empty - add the key to")
        print("backend/.env (get one at https://console.groq.com/keys).")
        return 1

    print("1/2  chat() free-form completion ...")
    prose = llm.chat(
        "You are a relationship analyst. Answer in one short sentence.",
        "A client went quiet for 40 days after a positive meeting. What now?",
    )
    if not prose:
        print("     FAILED - chat() returned nothing. Endpoint unreachable or erroring.")
        return 1
    print("     OK ->", prose[:200])
    print()

    print("2/2  extract_interaction() structured output ...")
    res = llm.extract_interaction(_SAMPLE_NOTE, interaction_type="call")
    print("     model     :", res.model)
    print("     sentiment :", res.sentiment.value)
    print("     summary   :", res.summary[:200])
    print("     commitments:", res.commitments)
    print("     requests  :", res.requests)
    if res.model.startswith("stub"):
        print("     FAILED - fell back to the stub; the live call raised.")
        return 1
    print("     OK - structured extraction is running on the live model.")
    print()
    print("All good. The Relationship Brief and interaction extraction now use", s.llm_model)
    return 0


if __name__ == "__main__":
    sys.exit(main())
