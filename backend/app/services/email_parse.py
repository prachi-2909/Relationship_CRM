"""Parse a pasted email or an uploaded .eml into fields for the interaction log.

Handles both a full RFC-822 message and a lightly-formatted paste
("From: ...\\nSubject: ...\\n\\nbody"). Quoted history is collapsed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from email import message_from_string
from email.utils import getaddresses, parsedate_to_datetime

_QUOTE_MARKERS = re.compile(
    r"^\s*(?:-{2,}\s*Original Message\s*-{2,}"
    r"|On .+ wrote:\s*$"
    r"|From:\s.+\bwrote:?\s*$"
    r"|_{5,}\s*$)",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass
class ParsedEmail:
    from_name: str | None = None
    from_email: str | None = None
    to: list[str] = field(default_factory=list)
    date: datetime | None = None
    subject: str | None = None
    body: str = ""
    quoted_removed: bool = False


def _plain_body(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and not part.get_filename():
                try:
                    return part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", "replace"
                    )
                except Exception:
                    continue
        # fall back to any text/* part
        for part in msg.walk():
            if part.get_content_type().startswith("text/"):
                try:
                    raw = part.get_payload(decode=True)
                    text = raw.decode("utf-8", "replace") if raw else ""
                    return re.sub(r"<[^>]+>", " ", text)
                except Exception:
                    continue
        return ""
    payload = msg.get_payload(decode=True)
    if payload is None:
        return str(msg.get_payload())
    return payload.decode(msg.get_content_charset() or "utf-8", "replace")


def _collapse_quotes(body: str) -> tuple[str, bool]:
    marker = _QUOTE_MARKERS.search(body)
    cut = marker.start() if marker else len(body)

    lines = body[:cut].splitlines()
    kept: list[str] = []
    removed = marker is not None
    trailing_quote = 0
    for line in lines:
        if line.lstrip().startswith(">"):
            trailing_quote += 1
            removed = True
            continue
        trailing_quote = 0
        kept.append(line)
    # drop trailing blank lines
    while kept and not kept[-1].strip():
        kept.pop()
    _ = trailing_quote
    return "\n".join(kept).strip(), removed


def parse_email(raw: str) -> ParsedEmail:
    msg = message_from_string(raw or "")

    from_name, from_email = None, None
    addrs = getaddresses([msg.get("From", "")])
    if addrs and addrs[0][1]:
        from_name = addrs[0][0] or None
        from_email = addrs[0][1].lower()

    to = [a[1].lower() for a in getaddresses(msg.get_all("To", [])) if a[1]]

    date = None
    if msg.get("Date"):
        try:
            date = parsedate_to_datetime(msg["Date"])
        except (TypeError, ValueError):
            date = None

    body, removed = _collapse_quotes(_plain_body(msg))

    return ParsedEmail(
        from_name=from_name,
        from_email=from_email,
        to=to,
        date=date,
        subject=(msg.get("Subject") or None),
        body=body,
        quoted_removed=removed,
    )
