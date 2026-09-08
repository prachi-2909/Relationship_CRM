"""Helpers for officials: the verification roll-up and the provenance field map."""

from ..models.official import (
    FieldVerification,
    Official,
    OfficialFieldProvenance,
    PROVENANCED_FIELDS,
    VerificationStatus,
)


def _field_value(official: Official, field: str):
    return getattr(official, field)


def recompute_verification(official: Official) -> VerificationStatus:
    """Roll up per-field provenance into the official's overall status.

    Only fields that actually hold a value are considered. All such fields
    verified -> VERIFIED; some -> PARTIALLY_VERIFIED; none -> UNVERIFIED.
    """
    provenance = {p.field: p for p in official.field_provenance}
    populated = [f for f in PROVENANCED_FIELDS if _field_value(official, f) not in (None, "")]

    if not populated:
        status = VerificationStatus.UNVERIFIED
    else:
        verified = [
            f
            for f in populated
            if provenance.get(f)
            and provenance[f].verification_status is FieldVerification.VERIFIED
        ]
        if len(verified) == len(populated):
            status = VerificationStatus.VERIFIED
        elif verified:
            status = VerificationStatus.PARTIALLY_VERIFIED
        else:
            status = VerificationStatus.UNVERIFIED

    official.verification_status = status
    return status


def provenance_map(official: Official) -> dict[str, OfficialFieldProvenance]:
    return {p.field: p for p in official.field_provenance}
