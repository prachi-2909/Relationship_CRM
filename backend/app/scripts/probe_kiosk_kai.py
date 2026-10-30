"""Shows what Kiosk KAI (TARA) returns, so the CRM's TARA figures can be built to match the real answers.

    python -m app.scripts.probe_kiosk_kai                 # first 3 active CSPs from TARA, to pick a code
    python -m app.scripts.probe_kiosk_kai <CSP_CODE>      # that CSP's performance and profile
    python -m app.scripts.probe_kiosk_kai <CSP_CODE> --shape   # field names and types only, no values

Read-only. Uses the CRM's own key (KIOSK_KAI_APP_KEY) from the environment and never prints it.
"""

from __future__ import annotations

import argparse
import json

from ..services import kiosk_kai

MAX_CHARS = 5000


def _shape(value):
    if isinstance(value, dict):
        return {k: _shape(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_shape(value[0])] if value else []
    return type(value).__name__


def _show(title: str, body: dict | None, shape: bool) -> None:
    print(f"\n===== {title} =====")
    if body is None:
        print("no answer (see the app log for 'kiosk_kai event=CALL_FAILED')")
        return
    shown = {k: body.get(k) for k in ("source", "as_of", "caveats", "keys")}
    data = _shape(body.get("data")) if shape else body.get("data")
    shown["data"] = data
    text = json.dumps(shown, indent=2, default=str, ensure_ascii=False)
    print(text if len(text) <= MAX_CHARS else text[:MAX_CHARS] + "\n... (cut)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csp_code", nargs="?")
    parser.add_argument("--shape", action="store_true", help="print field names and types only")
    args = parser.parse_args()

    if not kiosk_kai.configured():
        raise SystemExit("KIOSK_KAI_APP_KEY is not set in this environment, so nothing was called.")

    if not args.csp_code:
        _show("tara.my_csps (first 3 active)", kiosk_kai.call("tara.my_csps", status="active", limit=3), args.shape)
        return
    _show("tara.csp_performance", kiosk_kai.call("tara.csp_performance", csp_code=args.csp_code), args.shape)
    _show("tara.csp_profile", kiosk_kai.call("tara.csp_profile", csp_code=args.csp_code), args.shape)


if __name__ == "__main__":
    main()
