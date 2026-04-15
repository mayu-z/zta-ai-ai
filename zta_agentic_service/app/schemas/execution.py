from pydantic import BaseModel, Field


class UserContext(BaseModel):
    user_id: str
    tenant_id: str
    persona: str
    department: str | None = None


class ExecuteRequest(BaseModel):
    query: str
    user_context: UserContext
    tenant_id: str


class ExecutionResult(BaseModel):
    execution_id: str
    status: str
    state: str
    output_summary: str | None = None
    requires_confirmation: bool = False
    requires_approval: bool = False
    next_actions: list[str] = Field(default_factory=list)


class ConfirmRequest(BaseModel):
    actor_user_id: str
    decision: str = Field(pattern="^(confirm|cancel|approve|reject)$")
