"""CSP API schemas."""

from datetime import date

from pydantic import BaseModel, ConfigDict

from .call_intelligence import CallSessionDetail


class CspOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    csp_id: str
    name: str
    mobile: str | None = None
    alternate_mobile: str | None = None
    category: str | None = None
    rm_name: str
    rm_user_id: int | None = None
    branch_name: str | None = None
    district: str | None = None
    state: str | None = None
    status: str
    # Relationship-building details (from the KO enrichment).
    date_of_birth: date | None = None
    gender: str | None = None
    email: str | None = None
    address: str | None = None
    pincode: str | None = None
    home_phone: str | None = None


class CspRmGroup(BaseModel):
    """All CSPs assigned to one Relationship Manager."""

    rm_name: str
    rm_user_id: int | None = None
    count: int
    csps: list[CspOut]


class CspByRmResponse(BaseModel):
    groups: list[CspRmGroup]
    total: int


class CspProfileResponse(BaseModel):
    """A single Kiosk Operator with the full history of calls had with them -
    the "ye baat hui" record on the KO's profile."""

    csp: CspOut
    calls: list[CallSessionDetail]
    calls_total: int
