"""The Supervisor — routes a free-text question to the right read-only data
and synthesises one answer from it. No autonomy: it never writes anything,
and it never sends anything. A human reads the answer and decides.

Routing is deterministic, not an LLM tool-calling loop:
  1. Try to resolve person names mentioned in the question against known
     officials (a handful of officials, one query — cheap).
  2. If any resolve to a relationship, build a full Brief for each (capped,
     since a Brief is several queries) - a *targeted* answer.
  3. Otherwise fall back to a ranked portfolio scan (three queries total,
     regardless of how many relationships exist) - a *portfolio* answer.
Exactly one LLM call happens either way, over the already-gathered context.
"""

from __future__ import annotations

import json
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.official import Official
from ..models.relationship import Relationship
from ..models.user import User
from . import brief as brief_svc
from . import llm, portfolio

_MAX_TARGETED = 3  # more named people than this -> treat as a portfolio question


def _match_officials(db: Session, question: str) -> list[Official]:
    """Officials whose name is plausibly referenced in the question.

    Cheap on purpose: one query over a small table (a CRM's own contacts,
    not a general text corpus), then in-memory token overlap - no per-name
    query. Requires 2+ matching tokens for a multi-word name to cut down on
    a single common surname matching by accident.
    """
    q_tokens = set(re.findall(r"[a-z0-9]+", question.lower()))
    if not q_tokens:
        return []
    matches = []
    for official in db.scalars(select(Official)):
        name_tokens = [t for t in re.findall(r"[a-z0-9]+", official.name.lower()) if len(t) > 1]
        if not name_tokens:
            continue
        hits = sum(1 for t in name_tokens if t in q_tokens)
        needed = 1 if len(name_tokens) == 1 else 2
        if hits >= min(needed, len(name_tokens)):
            matches.append(official)
    return matches


_SYSTEM_PROMPT = (
    "You are a relationship-intelligence assistant for a CRM. Answer the "
    "user's question using ONLY the structured data provided below - never "
    "invent a fact, a name, or a number that is not in it. If the data does "
    "not cover what was asked, say plainly what is missing instead of "
    "guessing.\n\n"
    "The data may cover several relationships even when the question is "
    "about just one thing - you are given the whole portfolio to choose "
    "from, not to report on in full. Match the BREADTH of your answer to "
    "the question, not to how much data you were handed:\n"
    "- A question about one person, or asking for a single top pick / the "
    "most urgent one / who to focus on FIRST, gets ONE relationship named "
    "in the answer - the single best match. Do not mention the others.\n"
    "- Only list multiple relationships when the question explicitly asks "
    "for a list, several names, a ranking, or 'relationships' (plural).\n"
    "- If several relationships are genuinely tied for most urgent, say so "
    "briefly rather than listing everyone.\n\n"
    "Reference relationships by the official's name, and give at least one "
    "line of concrete reasoning for each one you mention - never answer "
    "with just a bare name. Reply in PLAIN TEXT ONLY: no markdown, no "
    "asterisks or other bold/italic markers, no headings. For a list (only "
    "when one is actually called for), put one item per line starting with "
    "a hyphen, each followed by the reason; otherwise write a short plain "
    "paragraph. This is analysis for a human to act on, not a message to "
    "send - never draft an email or greeting."
)


def _synthesize(question: str, scope: str, context: list[dict]) -> tuple[str, str]:
    payload = json.dumps({"scope": scope, "data": context}, default=str)
    text = llm.chat(_SYSTEM_PROMPT, f"Question: {question}\n\nData:\n{payload}")
    if text:
        return text, f"llm:{llm.settings.llm_model}"
    return _template_answer(question, scope, context), "template"


def _template_answer(question: str, scope: str, context: list[dict]) -> str:
    if not context:
        return "There's nothing on record yet to answer that from."
    if scope == "targeted":
        lines = []
        for c in context:
            lines.append(
                f"{c['official_name']}: {c['what_is_important']} {c['next_interaction']}"
            )
        return " ".join(lines)
    top = context[:5]
    lines = [
        f"{c['official_name']} — {c['band']} (score {c['score']}), "
        f"{c['open_moments']} open moment(s), {c['overdue_followups']} overdue follow-up(s)"
        for c in top
    ]
    return "Top relationships needing attention:\n" + "\n".join(f"- {l}" for l in lines)


def answer(db: Session, actor: User, question: str) -> dict:
    matched = _match_officials(db, question)
    considered: list[dict] = []
    context: list[dict] = []
    scope = "portfolio"

    if matched and len(matched) <= _MAX_TARGETED:
        matched_ids = [o.id for o in matched]
        rels = {
            r.official_id: r
            for r in db.scalars(
                select(Relationship).where(Relationship.official_id.in_(matched_ids))
            )
        }
        for official in matched:
            rel = rels.get(official.id)
            if rel is None:
                continue
            b = brief_svc.build(db, rel)
            context.append(b)
            considered.append(
                {"relationship_id": rel.id, "official_name": official.name}
            )
        if context:
            scope = "targeted"

    if not context:
        rows = portfolio.scan(db, actor)
        context = rows
        considered = [
            {"relationship_id": r["relationship_id"], "official_name": r["official_name"]}
            for r in rows
        ]

    answer_text, generated_by = _synthesize(question, scope, context)
    return {
        "answer": answer_text,
        "generated_by": generated_by,
        "scope": scope,
        "considered": considered,
    }
