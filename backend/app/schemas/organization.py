"""Request/response models for organisation units and unit types."""

from pydantic import BaseModel, ConfigDict, Field

from ..models.organization_unit import OrgUnitStatus


class UnitTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    label: str
    rank: int
    active: bool


class UnitTypeCreate(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    label: str = Field(min_length=1, max_length=120)
    rank: int = 100


class UnitBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    type_code: str = Field(min_length=1, max_length=32)
    parent_id: int | None = None
    location: str | None = Field(default=None, max_length=200)
    department: str | None = Field(default=None, max_length=200)
    metadata: dict | None = None


class UnitCreate(UnitBase):
    pass


class UnitUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    type_code: str | None = Field(default=None, min_length=1, max_length=32)
    parent_id: int | None = None
    location: str | None = Field(default=None, max_length=200)
    department: str | None = Field(default=None, max_length=200)
    status: OrgUnitStatus | None = None
    metadata: dict | None = None


class UnitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    name: str
    type_code: str
    parent_id: int | None
    location: str | None
    department: str | None
    status: OrgUnitStatus
    metadata: dict | None = Field(
        default=None,
        validation_alias="unit_metadata",
        serialization_alias="metadata",
    )


class UnitTreeNode(UnitOut):
    children: list["UnitTreeNode"] = []
