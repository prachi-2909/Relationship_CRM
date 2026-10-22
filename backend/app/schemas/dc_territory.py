"""Request/response models for DC territory assignment and the DC profile."""

from datetime import datetime

from pydantic import BaseModel


class TerritoryAssign(BaseModel):
    dc_user_id: int
    organization_unit_id: int


class TerritoryOut(BaseModel):
    id: int | None = None
    dc_user_id: int
    dc_user_name: str
    organization_unit_id: int
    organization_unit_name: str
    organization_unit_type: str
    assigned_at: datetime | None = None
    # False for a parent RBO/AO shown because it carries officials that cover
    # the DC's assigned branches (e.g. a shared Field Investigator) - not an
    # actual DCTerritory assignment, so there's nothing to remove/re-assign.
    is_direct: bool = True


class DcProfile(BaseModel):
    id: int
    name: str
    email: str
    status: str
    territory: list[TerritoryOut]
    pending_calls: int
    logged_interactions: int
