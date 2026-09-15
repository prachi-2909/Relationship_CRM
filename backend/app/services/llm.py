"""Interaction understanding.

One entry point, ``extract_interaction``, always returns a schema-validated
``ExtractionResult``. With no LLM endpoint configured it runs a deterministic
offline stub so the rest of the system stays testable and demoable; set
``LLM_BASE_URL`` / ``LLM_MODEL`` to use any OpenAI-compatible chat endpoint.

Groq (hosted, OpenAI-compatible)::

    LLM_BASE_URL=https://api.groq.com/openai/v1
    LLM_MODEL=llama-3.1-8b-instant
    LLM_API_KEY=gsk_...

Local Ollama (no key, but needs the RAM for the model)::

    LLM_BASE_URL=http://localhost:11434/v1
    LLM_MODEL=llama3.1:8b
    LLM_TIMEOUT_SECONDS=120     # first call loads the model into memory
"""

from __future__ import annotations

import json
import re

from pydantic import BaseModel, Field

from ..config import get_settings
from ..models.interaction import Sentiment

settings = get_settings()


class RelationMention(BaseModel):
    """A relationship between two named people, stated in the note.

    ``from_`` / ``to`` are person names (never pronouns). Direction:
    reports_to -> from is the subordinate; introduced_by -> from is the person
    who was introduced, to is the introducer; works_with is symmetric.
    """

    from_: str = Field(alias="from")
    to: str
    type: str  # reports_to | works_with | introduced_by
    evidence: str = ""

    model_config = {"populate_by_name": True}


class ExtractionResult(BaseModel):
    summary: str = ""
    sentiment: Sentiment = Sentiment.UNKNOWN
    topics: list[str] = Field(default_factory=list)
    commitments: list[str] = Field(default_factory=list)
    requests: list[str] = Field(default_factory=list)
    people: list[str] = Field(default_factory=list)
    relations: list[RelationMention] = Field(default_factory=list)
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

# a person name for the relation patterns: 1-3 capitalised words, optional
# honorific. NOT case-insensitive - the capitalisation is what anchors a name.
_N = r"(?:(?:Mr|Mrs|Ms|Shri|Smt|Dr|Sri)\.?\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})"
# each: (compiled pattern, which group is `from`, which is `to`, type)
_RELATION_PATTERNS = [
    (re.compile(rf"{_N}\s+reports?\s+(?:directly\s+)?to\s+{_N}"), 1, 2, "reports_to"),
    (
        re.compile(
            rf"{_N}(?:'s|s'|s)?\s+(?:reporting\s+)?(?:manager|boss|supervisor|team\s+lead|reporting\s+manager)\s+(?:is\s+)?{_N}"
        ),
        1, 2, "reports_to",
    ),
    (
        re.compile(rf"{_N}\s+(?:manages|heads\s+up|line-?manages)\s+{_N}"),
        2, 1, "reports_to",
    ),
    (
        re.compile(
            rf"{_N}\s+(?:introduced|connected)\s+(?:us|me|the\s+team|our\s+team)\s+(?:to|with)\s+{_N}"
        ),
        2, 1, "introduced_by",
    ),
    (
        re.compile(
            rf"(?:introduced|connected)\s+(?:to|with)\s+{_N}\s+(?:by|through|via)\s+{_N}"
        ),
        1, 2, "introduced_by",
    ),
    (re.compile(rf"{_N}\s+works?\s+(?:closely\s+)?with\s+{_N}"), 1, 2, "works_with"),
]
_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "have", "been", "will",
    "your", "our", "was", "were", "are", "not", "but", "they", "them", "their",
    "about", "into", "also", "would", "could", "should", "there", "here", "which",
}


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?।])\s+|\n+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _stub_relations(text: str) -> list[RelationMention]:
    out: list[RelationMention] = []
    seen: set[tuple[str, str, str]] = set()
    for pattern, gf, gt, rtype in _RELATION_PATTERNS:
        for m in pattern.finditer(text):
            a, b = m.group(gf).strip(), m.group(gt).strip()
            if a.lower() == b.lower():
                continue
            key = (a.lower(), b.lower(), rtype)
            if key in seen:
                continue
            seen.add(key)
            out.append(
                RelationMention(**{"from": a, "to": b, "type": rtype, "evidence": m.group(0).strip()[:180]})
            )
    return out[:8]


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

    relations = _stub_relations(text)
    for r in relations:  # make sure both endpoints show up in people
        for nm in (r.from_, r.to):
            if nm not in people:
                people.append(nm)

    return ExtractionResult(
        summary=summary,
        sentiment=sentiment,
        topics=topics,
        commitments=commitments[:8],
        requests=requests[:8],
        people=people[:8],
        relations=relations,
        model="stub",
    )


_SYSTEM_PROMPT = (
    "You extract structured intelligence from a single business interaction note "
    "for a relationship-management system. The note may be in English, Hindi, or a "
    "mix. Reply with ONLY a JSON object with keys: summary (string, <= 3 sentences, "
    "English), sentiment (one of positive/neutral/negative/unknown), topics (array "
    "of short strings), commitments (array of strings - things someone said they "
    "will do), requests (array of strings - things someone asked for), people "
    "(array of person names mentioned), relations (array of objects describing a "
    "relationship BETWEEN TWO NAMED PEOPLE that the note states or clearly implies). "
    'Each relation object is {"from": name, "to": name, "type": one of '
    '"reports_to" | "works_with" | "introduced_by", "evidence": the phrase that '
    'implies it}. For "reports_to", from is the subordinate and to is the manager. '
    'For "introduced_by", from is the person who was introduced and to is the '
    'introducer. "works_with" is symmetric - use it only when the note actually '
    "says they collaborate, not merely because both are mentioned. Use real names "
    "only, never pronouns; omit a relation if either side is not a named person. "
    "Keep quoted phrases in their original language; write summary and topics in "
    "English."
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

    data = json.loads(_json_blob(content))
    return ExtractionResult(
        summary=str(data.get("summary", ""))[:1000],
        sentiment=_coerce_sentiment(data.get("sentiment")),
        topics=[str(x) for x in data.get("topics", [])][:12],
        commitments=[str(x) for x in data.get("commitments", [])][:12],
        requests=[str(x) for x in data.get("requests", [])][:12],
        people=[str(x) for x in data.get("people", [])][:12],
        relations=_coerce_relations(data.get("relations")),
        model=settings.llm_model,
    )


_REL_TYPES = {"reports_to", "works_with", "introduced_by"}


def _coerce_relations(value: object) -> list[RelationMention]:
    if not isinstance(value, list):
        return []
    out: list[RelationMention] = []
    for item in value[:16]:
        if not isinstance(item, dict):
            continue
        a = str(item.get("from") or item.get("from_") or "").strip()
        b = str(item.get("to") or "").strip()
        t = str(item.get("type") or "").strip().lower().replace(" ", "_").replace("-", "_")
        if not a or not b or a.lower() == b.lower() or t not in _REL_TYPES:
            continue
        out.append(
            RelationMention(
                **{"from": a, "to": b, "type": t, "evidence": str(item.get("evidence") or "")[:200]}
            )
        )
    return out


def _coerce_sentiment(value: object) -> Sentiment:
    try:
        return Sentiment(str(value).lower())
    except ValueError:
        return Sentiment.UNKNOWN


def _json_blob(content: str) -> str:
    """Pull the JSON object out of a model reply.

    Smaller local models (via Ollama) often wrap the object in a ```json fence
    or add a line of preamble even when told not to; take the outermost {...}.
    """
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", text).strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


def chat(
    system: str,
    user: str,
    *,
    temperature: float = 0.2,
    history: list[dict] | None = None,
) -> str | None:
    """Free-form completion via the configured OpenAI-compatible endpoint.

    ``history`` is prior turns as ``[{"role": "user"|"assistant", "content": str},
    ...]``, oldest first - passed through as real chat messages (not stuffed
    into the prompt text) so the model can resolve "what about him" style
    follow-ups. Returns None when no endpoint is set (the caller falls back
    to a template) or when the call fails. Reusable by any read-only agent
    that needs prose.
    """
    if not settings.llm_base_url:
        return None
    try:
        import httpx

        headers = {"Content-Type": "application/json"}
        if settings.llm_api_key:
            headers["Authorization"] = f"Bearer {settings.llm_api_key}"
        url = settings.llm_base_url.rstrip("/") + "/chat/completions"
        messages = [{"role": "system", "content": system}]
        messages.extend(history or [])
        messages.append({"role": "user", "content": user})
        with httpx.Client(timeout=settings.llm_timeout_seconds) as client:
            resp = client.post(
                url,
                json={
                    "model": settings.llm_model,
                    "messages": messages,
                    "temperature": temperature,
                },
                headers=headers,
            )
            resp.raise_for_status()
            text = (resp.json()["choices"][0]["message"]["content"] or "").strip()
            if text.startswith("```"):
                text = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", text).strip()
            return text or None
    except Exception:
        return None


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
