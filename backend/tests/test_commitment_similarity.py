"""The duplicate detector, measured on labelled pairs.

The labelled sets are written by the developers, not drawn from live data, so they show the detector
behaves as designed on the cases we thought of - not how it will fare on every real brief. What matters
most is precision: a FALSE POSITIVE hides a real promise behind a "possible duplicate" prompt.
"""

from datetime import date

import pytest
from commitment_pairs import DISTINCT, SIMILAR

from app.services.commitment_similarity import are_similar, features, similarity
from app.services.commitments import _party


def _flag(a, b):
    return are_similar(a, b, party_a=_party(a, False).value, party_b=_party(b, False).value)[0]


@pytest.mark.parametrize("a,b", DISTINCT)
def test_genuinely_different_commitments_are_never_flagged(a, b):
    assert _flag(a, b) is False, f"false positive: {a!r} vs {b!r}"


def test_recall_on_rewordings_of_the_same_promise():
    missed = [(a, b) for a, b in SIMILAR if not _flag(a, b)]
    recall = 1 - len(missed) / len(SIMILAR)
    assert recall >= 0.9, f"recall {recall:.0%}; missed {missed}"


def test_precision_is_perfect_on_the_labelled_distinct_set():
    false_positives = [(a, b) for a, b in DISTINCT if _flag(a, b)]
    assert false_positives == []


def test_ownership_must_match_unless_one_side_is_unclear():
    a, b = "CSP to send the report.", "RM to send the report."
    assert are_similar(a, b, party_a="theirs", party_b="ours")[0] is False
    assert are_similar(a, b, party_a="theirs", party_b="mutual")[0] is True


def test_different_due_dates_mean_different_commitments():
    a = b = "CSP to send the sales report."
    assert are_similar(a, b, due_a=date(2026, 12, 5), due_b=date(2026, 12, 20))[0] is False
    assert are_similar(a, b, due_a=date(2026, 12, 5), due_b=date(2026, 12, 5))[0] is True
    assert are_similar(a, b, due_a=date(2026, 12, 5), due_b=None)[0] is True   # an unknown date does not separate


def test_a_one_word_commitment_is_never_matched():
    assert are_similar("CSP to call.", "CSP to call.")[0] is False   # too little to compare


def test_parenthetical_commentary_and_non_breaking_hyphens_are_ignored():
    assert features("CSP to fix the terminal (no specific deadline given).").content == features(
        "CSP to fix the terminal."
    ).content
    assert features("complete 3 PM‑SBY").critical == features("complete 3 PMSBY").critical


def test_similarity_is_symmetric_and_bounded():
    a, b = "CSP to fix the terminal expiry issue.", "CSP will repair the terminal expiry problem."
    assert similarity(a, b) == similarity(b, a)
    assert 0.0 <= similarity(a, b) <= 1.0
    assert similarity("", b) == 0.0
