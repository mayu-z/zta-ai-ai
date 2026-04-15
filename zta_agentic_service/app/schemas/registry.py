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
    trigger_config_schema: dict = Field(default_factory=dict)
    required_data_scope: list[str] = Field(default_factory=list)
    input_schema: dict = Field(default_factory=dict)
    output_schema: dict = Field(default_factory=dict)
    action_steps: list[ActionStepConfig] = Field(default_factory=list)
    rbac_permissions: dict = Field(default_factory=dict)
    constraints: dict = Field(default_factory=dict)
    output_type: str = "read"
    requires_confirmation: bool = False
    approval_level: str = "user"
    allowed_personas: list[str] = Field(default_factory=list)
    confirmation_prompt: str | None = None
    chain_to: list[str] = Field(default_factory=list)
    allowed_output_channels: list[str] = Field(default_factory=list)
    handler_class: str = ""
    is_side_effect: bool = False
    risk_level: str = "low"
    is_sensitive_monitor: bool = False
    is_active: bool = True
    status: str = "beta"
    risk_rank: int = Field(default=50, ge=0, le=100)


class TenantAgentConfigPatch(BaseModel):
    is_enabled: bool | None = None
    custom_templates: dict | None = None
    custom_constraints: dict | None = None
    approval_config: dict | None = None
    notification_channels: dict | None = None
    config: dict | None = None
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
