"""Request bodies shared by the CSP and SBI-official intelligence routes."""

from pydantic import BaseModel


class CommitmentStatusUpdate(BaseModel):
    status: str                    # open | done | cancelled  ("open" on a proposal = accept it)
    outcome: str | None = None     # fulfilled | not_fulfilled  (how it ended)


class DuplicateDecision(BaseModel):
    decision: str                  # merge | separate


class FeedbackIn(BaseModel):
    target_type: str               # talking_point | followup
    key: str
    verdict: str                   # useful | not_useful | relevant | not_relevant
    note: str | None = None
