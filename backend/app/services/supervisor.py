"""The Supervisor — routes a free-text question to the right read-only data
and synthesises one answer from it. No autonomy: it never writes anything,
and it never sends anything. A human reads the answer and decides.

Routing is deterministic, not an LLM tool-calling loop:
  1. Try to resolve person names mentioned in the question against known
     officials (a handful of officials, one query — cheap).
  2. Named nobody, but the question reads like a pronoun follow-up ("what
     about HIS stakeholders?") and the conversation's last turn named
     someone -> carry that subject forward instead of resolving names again.
  3. Either way, build a full Brief per subject (capped, since a Brief is
     several queries) - a *targeted* answer.
  4. Otherwise fall back to a ranked portfolio scan (three queries total,
     regardless of how many relationships exist) - a *portfolio* answer.
Exactly one LLM call happens either way, over the already-gathered context
plus the recent conversation turns (real chat history, not stuffed text) so
the model can actually resolve a follow-up rather than just guess.
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


# English + common Hindi/Hinglish referents. Whole-word match only, so this
# never fires on an unrelated word that merely contains one as a substring.
_FOLLOWUP_HINTS = {
    "he", "him", "his", "she", "her", "hers", "they", "them", "their",
    "unka", "unke", "unko", "uske", "uska", "usko", "unhe", "unhone",
    "voh", "wo", "vo",
}


def _looks_like_followup(question: str) -> bool:
    tokens = set(re.findall(r"[a-z']+", question.lower()))
    return bool(tokens & _FOLLOWUP_HINTS)


def _briefs_for(db: Session, official_ids: list[int]) -> tuple[list[dict], list[dict]]:
    """Full Brief + a considered-entry for each official that has a
    relationship, in the given order. Skips ids with no relationship."""
    rels = {
        r.official_id: r
        for r in db.scalars(
            select(Relationship).where(Relationship.official_id.in_(official_ids))
        )
    }
    context: list[dict] = []
    considered: list[dict] = []
    for official_id in official_ids:
        rel = rels.get(official_id)
        if rel is None:
            continue
        context.append(brief_svc.build(db, rel))
        considered.append({"relationship_id": rel.id, "official_name": rel.official.name})
    return context, considered


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
    "send - never draft an email or greeting.\n\n"
    "The data may include engagement moments (birthday/anniversary/"
    "promotion/inactivity check-ins) and overdue follow-ups for each "
    "relationship - fold these in when relevant instead of only talking "
    "about score and contact gap:\n"
    "- A moment with status draft_ready or approved (or moment_draft_ready "
    "= true) means a draft already exists and is waiting for a human to "
    "review and send - say so plainly (e.g. 'a birthday draft is ready to "
    "review'). Never write the draft's wording yourself.\n"
    "- A moment with status detected has not been drafted yet - at most "
    "note that one is open, don't imply it is ready to send.\n"
    "- Name any overdue follow-up by its title, not just that one exists.\n\n"
    "You may be shown earlier turns of this same conversation before the "
    "current question. Use them only to resolve what a pronoun or vague "
    "reference in the new question points to (e.g. 'his', 'them') - the "
    "structured data given for THIS question is still the only source of "
    "fact for your answer; do not restate the earlier answer."
)


def _synthesize(
    question: str, scope: str, context: list[dict], history: list[dict] | None
) -> tuple[str, str]:
    payload = json.dumps({"scope": scope, "data": context}, default=str)
    text = llm.chat(
        _SYSTEM_PROMPT,
        f"Question: {question}\n\nData:\n{payload}",
        history=history,
    )
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
    lines = []
    for c in top:
        bits = [f"{c['official_name']} — {c['band']} (score {c['score']})"]
        if c.get("moment_draft_ready"):
            bits.append("a draft is ready to review")
        elif c.get("open_moments"):
            bits.append(f"{c['open_moments']} open moment(s)")
        if c.get("overdue_tasks"):
            bits.append("overdue: " + ", ".join(t["title"] for t in c["overdue_tasks"]))
        elif c.get("overdue_followups"):
            bits.append(f"{c['overdue_followups']} overdue follow-up(s)")
        lines.append(", ".join(bits))
    return "Top relationships needing attention:\n" + "\n".join(f"- {l}" for l in lines)


def answer(
    db: Session,
    actor: User,
    question: str,
    *,
    history: list[dict] | None = None,
    prior_considered: list[dict] | None = None,
) -> dict:
    considered: list[dict] = []
    context: list[dict] = []
    scope = "portfolio"

    matched = _match_officials(db, question)
    if matched and len(matched) <= _MAX_TARGETED:
        context, considered = _briefs_for(db, [o.id for o in matched])
        if context:
            scope = "targeted"

    # named nobody new, but this reads as a follow-up on who was just
    # discussed ("what about his stakeholders?") -> carry that subject
    # forward instead of falling through to a portfolio-wide answer
    if not context and prior_considered and _looks_like_followup(question):
        prior_rel_ids = [c["relationship_id"] for c in prior_considered][:_MAX_TARGETED]
        if prior_rel_ids:
            rels = db.scalars(
                select(Relationship).where(Relationship.id.in_(prior_rel_ids))
            ).all()
            context = [brief_svc.build(db, rel) for rel in rels]
            considered = [
                {"relationship_id": rel.id, "official_name": rel.official.name}
                for rel in rels
            ]
            if context:
                scope = "targeted"

    if not context:
        rows = portfolio.scan(db, actor)
        context = rows
        considered = [
            {"relationship_id": r["relationship_id"], "official_name": r["official_name"]}
            for r in rows
        ]

    answer_text, generated_by = _synthesize(question, scope, context, history)
    return {
        "answer": answer_text,
        "generated_by": generated_by,
        "scope": scope,
        "considered": considered,
    }
