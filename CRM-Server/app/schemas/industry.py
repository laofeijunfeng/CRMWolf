from pydantic import BaseModel, Field


class IndustryHierarchyChild(BaseModel):
    code: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)


class IndustryHierarchyGroup(BaseModel):
    name: str = Field(..., min_length=1)
    children: list[IndustryHierarchyChild] = Field(default_factory=list)


IndustryHierarchyResponse = dict[str, IndustryHierarchyGroup]
