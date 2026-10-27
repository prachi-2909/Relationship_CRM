"""Are two commitments the same promise worded differently?

Offline and deterministic (no model call): the text is normalised to its *meaning-bearing* words -
filler and the "who" words are dropped, verbs are stemmed and mapped onto synonym groups ("fix" /
"repair" / "resolve") - and compared as sets. It is built to be conservative, because a wrong match
hides a real promise behind a "possible duplicate" prompt while a missed match only costs a human one
extra glance. Facts that distinguish two tasks are therefore gates that must agree:

* CRITICAL tokens must be identical: every number, product name (PMSBY, APY, ...), weekday or month,
  time word ("this" vs "next", "weekly" vs "monthly") and negation. "complete 3 PMSBY" and "complete 2
  PMJJBY", "call on Monday" and "call on Friday", "reach 50 this month" and "next month" never match.
* PROPER NOUNS (a capitalised word mid-sentence, or an acronym such as RBO / LHO, or a single capital
  letter such as "branch A") must appear on both sides: "call Rakesh" and "call Suresh" never match.
* The two commitments must be owned by the same side (or one of them unclear).
* If both carry a due date and the dates differ they are different commitments.
* What remains must overlap strongly (overlap coefficient AND Dice above a threshold), over at least
  MIN_CONTENT_TOKENS words.

This is lexical matching with synonyms, not a neural embedding: it catches re-wordings of the same verb
and object but not arbitrary paraphrase. A match is only ever a SUGGESTION shown to a human.
"""

from __future__ import annotations

import re

# A pair is flagged only when BOTH hold.
OVERLAP_THRESHOLD = 0.8
DICE_THRESHOLD = 0.6
MIN_CONTENT_TOKENS = 2

# Words that carry no meaning for "is this the same promise": fillers, auxiliaries, and the words that
# merely announce a commitment ("commits to", "agreed to"). The party words are dropped because
# ownership is compared separately.
_STOP = {
    "a", "an", "the", "to", "of", "and", "or", "in", "on", "at", "by", "for", "with", "from", "that",
    "this", "it", "is", "are", "was", "were", "be", "been", "being", "will", "shall", "would", "should",
    "may", "can", "has", "have", "had", "do", "does", "did", "as", "soon", "possible", "asap", "once",
    "after", "before", "then", "also", "please", "kindly", "need", "needs", "needed", "must", "agree",
    "agreed", "commit", "commits", "committed", "committing", "promise", "promised", "promises",
    "ensure", "ensures", "ensured", "make", "makes", "made", "sure", "specific", "deadline", "given",
    "time", "own", "their", "his", "her", "its", "our", "your", "my", "we", "they", "he", "she", "i",
    "csp", "csps", "rm", "rms", "operator", "officer", "dc", "official", "bank", "mitra", "eko", "sbi",
    "relationship", "manager", "customer", "now", "again", "so", "if", "when", "while",
}

# Verbs/nouns that mean the same thing for our purposes, collapsed to one representative.
_SYNONYM_GROUPS = [
    {"fix", "repair", "resolve", "rectify", "solve", "correct", "troubleshoot"},
    {"share", "send", "provide", "submit", "forward", "give", "deliver", "email", "mail"},
    {"update", "revise", "refresh", "amend", "edit", "modify"},
    {"complete", "finish", "finalize", "finalise", "conclude", "accomplish"},
    {"call", "phone", "ring", "contact", "reach"},
    {"visit", "meet", "attend"},
    {"report", "summary", "statement"},
    {"figure", "number", "count", "data", "numbers", "figures"},
    {"issue", "problem", "error", "fault", "bug", "glitch"},
    {"enroll", "enrol", "register", "onboard", "sign"},
    {"check", "verify", "confirm", "review", "validate"},
    {"follow", "followup", "chase"},
]
_CANON: dict[str, str] = {}

_NEGATIONS = {"not", "never", "cannot", "cant", "wont", "dont", "doesnt", "didnt", "without", "neither", "nor"}
# Words that change WHEN or HOW OFTEN: swapping one for another makes a different commitment.
_TIME = {
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "mon", "tue", "tues", "wed",
    "thu", "thur", "thurs", "fri", "sat", "sun", "today", "tomorrow", "tonight", "weekend",
    "january", "february", "march", "april", "june", "july", "august", "september", "october", "november",
    "december", "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
    "this", "next", "last", "previous", "coming", "upcoming", "daily", "weekly", "monthly", "quarterly",
    "yearly", "annually", "fortnightly", "week", "month", "year", "quarter", "fortnight",
    # "may" is deliberately absent: here it is overwhelmingly the modal verb, not the month.
}
_PRODUCT = re.compile(r"^(pm|apy|sss|ssy|sukanya|jjby|sby|jdy|pmjjby|pmsby|pmjdy|pmsbui)")
_PARENS = re.compile(r"\([^)]*\)")
_DASHES = re.compile("[\\-‐‑‒–]")
_APOSTROPHES = re.compile("['’]")
_TOKEN = re.compile(r"[A-Za-z0-9]+")
_SENTENCE_END = ".!?;:\n"


def _stem(w: str) -> str:
    if len(w) > 5 and w.endswith("ing"):
        w = w[:-3]
    elif len(w) > 4 and w.endswith("ied"):
        w = w[:-3] + "y"
    elif len(w) > 4 and w.endswith("ed"):
        w = w[:-2]
    elif len(w) > 4 and w.endswith("es"):
        w = w[:-2]
    elif len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        w = w[:-1]
    if len(w) > 3 and w.endswith("e"):
        w = w[:-1]  # complete -> complet, so "complete"/"completed"/"completing" all agree
    return w


def _build_canon() -> None:
    # Keys include each word's stem so "resolved"/"resolving" (stem "resolv") still reach "resolve".
    for group in _SYNONYM_GROUPS:
        rep = sorted(group)[0]
        for w in group:
            _CANON[w] = rep
            _CANON[_stem(w)] = rep


_build_canon()


def _canon(word: str) -> str:
    return _CANON.get(word) or _CANON.get(_stem(word)) or _stem(word)


class Features:
    """What a commitment text boils down to for comparison."""

    __slots__ = ("content", "critical", "proper")

    def __init__(self, content: frozenset[str], critical: frozenset[str], proper: frozenset[str]):
        self.content = content
        self.critical = critical
        self.proper = proper


def features(text: str) -> Features:
    t = _PARENS.sub(" ", text or "")   # "(no specific deadline given)" is commentary, not content
    t = _DASHES.sub("", t)             # PM-SBY / PM‑SBY -> PMSBY
    t = _APOSTROPHES.sub("", t)        # CSP's -> CSPs, don't -> dont
    content: set[str] = set()
    critical: set[str] = set()
    proper: set[str] = set()
    for m in _TOKEN.finditer(t):
        tok = m.group(0)
        low = tok.lower()
        if any(ch.isdigit() for ch in low):
            critical.add(low)
            continue
        if low in _NEGATIONS:
            critical.add("NOT")
            continue
        if low in _TIME:
            critical.add(low)
            continue
        if _PRODUCT.match(low):
            critical.add(_stem(low))
            continue
        if low in _STOP:
            continue
        canon = _canon(low)
        content.add(canon)
        # A capitalised word that does not begin a sentence is a name / place / acronym / label.
        before = t[: m.start()].rstrip()
        sentence_initial = not before or before[-1] in _SENTENCE_END
        if tok[0].isupper() and not sentence_initial:
            proper.add(canon)
    return Features(frozenset(content), frozenset(critical), frozenset(proper))


def similarity(a: str, b: str) -> float:
    """0..1 Dice similarity of the meaning-bearing words (ignores the gates - see are_similar)."""
    fa, fb = features(a), features(b)
    if not fa.content or not fb.content:
        return 0.0
    inter = len(fa.content & fb.content)
    return 2 * inter / (len(fa.content) + len(fb.content))


def are_similar(
    a: str,
    b: str,
    *,
    party_a: str | None = None,
    party_b: str | None = None,
    due_a=None,
    due_b=None,
) -> tuple[bool, float]:
    """(is_possible_duplicate, score). Conservative: every gate must pass."""
    fa, fb = features(a), features(b)
    score = similarity(a, b)
    if fa.critical != fb.critical:
        return False, score
    # A name/acronym/label on one side must at least appear on the other (as any word).
    if any(p not in fb.content for p in fa.proper) or any(p not in fa.content for p in fb.proper):
        return False, score
    if party_a and party_b and party_a != party_b and "mutual" not in (party_a, party_b):
        return False, score
    if due_a is not None and due_b is not None and due_a != due_b:
        return False, score
    if len(fa.content) < MIN_CONTENT_TOKENS or len(fb.content) < MIN_CONTENT_TOKENS:
        return False, score
    inter = len(fa.content & fb.content)
    overlap = inter / min(len(fa.content), len(fb.content))
    if overlap >= OVERLAP_THRESHOLD and score >= DICE_THRESHOLD:
        return True, score
    return False, score
