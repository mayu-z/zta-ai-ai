from pydantic import BaseModel, Field


class ActionStepConfig(BaseModel):
    step_id: str
    step_type: str
    timeout_ms: int = Field(default=1000, ge=100)
    retry_policy: dict = Field(default_factory=dict)
    config: dict = Field(default_factory=dict)


class AgentDefinitionContract(BaseModel):
    agent_key: str
    name: str
    description: str
    version: str
    domain: str
    trigger_type: str
    trigger_config: dict = Field(default_factory=dict)
    input_schema: dict = Field(default_factory=dict)
    output_schema: dict = Field(default_factory=dict)
    action_steps: list[ActionStepConfig] = Field(default_factory=list)
    rbac_permissions: dict = Field(default_factory=dict)
    constraints: dict = Field(default_factory=dict)
    requires_confirmation: bool = False
    confirmation_prompt: str | None = None
    chain_to: list[str] = Field(default_factory=list)
    allowed_output_channels: list[str] = Field(default_factory=list)
    is_sensitive_monitor: bool = False
    status: str = "beta"
    risk_rank: int = Field(default=50, ge=0, le=100)


class TenantAgentConfigPatch(BaseModel):
    is_enabled: bool | None = None
    custom_templates: dict | None = None
    custom_constraints: dict | None = None
    approval_config: dict | None = None
    notification_channels: dict | None = None
    edit_version: int | None = None


class AgentDefinitionDraftRequest(BaseModel):
    definition: AgentDefinitionContract
    actor_user_id: str | None = None
    expected_base_version: str | None = None


class VersionPointerRequest(BaseModel):
    tenant_id: str
    definition_version_id: str
    config_version_id: str
    actor_user_id: str | None = None
    notes: str | None = None
    expected_edit_version: int | None = Field(default=None, ge=0)


class AgentStatusPatch(BaseModel):
    status: str = Field(pattern="^(active|beta|deprecated)$")
