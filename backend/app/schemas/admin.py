from pydantic import BaseModel, Field


class UserUpdateRequest(BaseModel):
    persona_type: str | None = None
    department: str | None = None
    status: str | None = None


class DataSourceCreateRequest(BaseModel):
    name: str
    source_type: str
    config: dict = Field(default_factory=dict)
    department_scope: list[str] = Field(default_factory=list)


class KillSwitchRequest(BaseModel):
    scope: str
    target_id: str | None = None
