"""Interaction understanding.

One entry point, ``extract_interaction``, always returns a schema-validated
``ExtractionResult``. With no LLM endpoint configured it runs a deterministic
offline stub so the rest of the system stays testable and demoable; set
``LLM_BASE_URL`` / ``LLM_MODEL`` to use any OpenAI-compatible chat endpoint.
"""

from __future__ import annotations

import json
import re

from pydantic import BaseModel, Field

from ..config import get_settings
from ..models.interaction import Sentiment

settings = get_settings()


class ExtractionResult(BaseModel):
    summary: str = ""
    sentiment: Sentiment = Sentiment.UNKNOWN
    topics: list[str] = Field(default_factory=list)
    commitments: list[str] = Field(default_factory=list)
    requests: list[str] = Field(default_factory=list)
    people: list[str] = Field(default_factory=list)
    model: str = "stub"


_POSITIVE = {
    "thanks", "thank", "appreciate", "appreciated", "glad", "resolved", "resolve",
    "approved", "approval", "happy", "good", "great", "pleased", "confirmed",
    "sorted", "dhanyavaad", "shukriya", "theek",
}
_NEGATIVE = {
    "delay", "delayed", "issue", "problem", "escalate", "escalated", "unhappy",
    "concern", "concerned", "disappointed", "pending", "unresolved", "stuck",
    "complaint", "not working", "failure", "failed", "shikayat", "pareshani",
}
_COMMIT_HINTS = (
    "will ", "we will", "i will", "shall ", "by eod", "by tomorrow", "by monday",
    "by next", "commit", "ensure", "revert", "get back", "share the", "send the",
    "provide the", "circulate", "follow up", "close by",
)
_REQUEST_HINTS = (
    "please", "request", "requested", "kindly", "need ", "needs ", "require",
    "can you", "could you", "would you", "expedite", "help with",
)
_HONORIFICS = re.compile(
    r"\b(?:Mr\.?|Mrs\.?|Ms\.?|Shri|Smt\.?|Dr\.?|Sri)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,2})"
)
_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "have", "been", "will",
    "your", "our", "was", "were", "are", "not", "but", "they", "them", "their",
    "about", "into", "also", "would", "could", "should", "there", "here", "which",
}


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?।])\s+|\n+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _stub_extract(text: str) -> ExtractionResult:
    sentences = _sentences(text)
    lowered = text.lower()

    pos = sum(lowered.count(w) for w in _POSITIVE)
    neg = sum(lowered.count(w) for w in _NEGATIVE)
    if pos > neg:
        sentiment = Sentiment.POSITIVE
    elif neg > pos:
        sentiment = Sentiment.NEGATIVE
    elif sentences:
        sentiment = Sentiment.NEUTRAL
    else:
        sentiment = Sentiment.UNKNOWN

    summary = " ".join(sentences[:2])[:280]

    commitments, requests = [], []
    for s in sentences:
        low = s.lower()
        if any(h in low for h in _COMMIT_HINTS):
            commitments.append(s[:200])
        if any(h in low for h in _REQUEST_HINTS):
            requests.append(s[:200])

    people = []
    for m in _HONORIFICS.finditer(text):
        name = m.group(1).strip()
        if name not in people:
            people.append(name)

    freq: dict[str, int] = {}
    for token in re.findall(r"[A-Za-z]{5,}", lowered):
        if token in _STOPWORDS:
            continue
        freq[token] = freq.get(token, 0) + 1
    topics = [w for w, _ in sorted(freq.items(), key=lambda kv: -kv[1])[:5]]

    return ExtractionResult(
        summary=summary,
        sentiment=sentiment,
        topics=topics,
        commitments=commitments[:8],
        requests=requests[:8],
        people=people[:8],
        model="stub",
    )


_SYSTEM_PROMPT = (
    "You extract structured intelligence from a single business interaction note "
    "for a relationship-management system. The note may be in English, Hindi, or a "
    "mix. Reply with ONLY a JSON object with keys: summary (string, <= 3 sentences, "
    "English), sentiment (one of positive/neutral/negative/unknown), topics (array "
    "of short strings), commitments (array of strings - things someone said they "
    "will do), requests (array of strings - things someone asked for), people "
    "(array of person names mentioned). Keep quoted phrases in their original "
    "language; write summary and topics in English."
)


def _llm_extract(text: str, interaction_type: str) -> ExtractionResult:
    import httpx  # local import: only needed when an endpoint is configured

    payload = {
        "model": settings.llm_model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Interaction type: {interaction_type}\n\nNote:\n{text}",
            },
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    headers = {"Content-Type": "application/json"}
    if settings.llm_api_key:
        headers["Authorization"] = f"Bearer {settings.llm_api_key}"

    url = settings.llm_base_url.rstrip("/") + "/chat/completions"
    with httpx.Client(timeout=settings.llm_timeout_seconds) as client:
        resp = client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]

    data = json.loads(content)
    return ExtractionResult(
        summary=str(data.get("summary", ""))[:1000],
        sentiment=_coerce_sentiment(data.get("sentiment")),
        topics=[str(x) for x in data.get("topics", [])][:12],
        commitments=[str(x) for x in data.get("commitments", [])][:12],
        requests=[str(x) for x in data.get("requests", [])][:12],
        people=[str(x) for x in data.get("people", [])][:12],
        model=settings.llm_model,
    )


def _coerce_sentiment(value: object) -> Sentiment:
    try:
        return Sentiment(str(value).lower())
    except ValueError:
        return Sentiment.UNKNOWN


def extract_interaction(text: str, *, interaction_type: str = "note") -> ExtractionResult:
    text = (text or "").strip()
    if not text:
        return ExtractionResult(model=settings.llm_model if settings.llm_base_url else "stub")
    if settings.llm_base_url:
        try:
            return _llm_extract(text, interaction_type)
        except Exception:
            # Never let extraction failure block logging the interaction.
            result = _stub_extract(text)
            result.model = f"stub (fallback from {settings.llm_model})"
            return result
    return _stub_extract(text)
