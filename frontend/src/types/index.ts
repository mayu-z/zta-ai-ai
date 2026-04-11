export type PersonaType =
  | "student"
  | "faculty"
  | "executive"
  | "it_head"
  | "dept_head"
  | "admin_staff"
  | "system_admin";

export interface AuthUser {
  id: string;
  email: string;
  name: string;
  persona: PersonaType;
  department: string | null;
}

export interface AuthResponse {
  jwt: string;
  user: AuthUser;
}

export interface ScopeClaims {
  session_id: string;
  role_key: string;
  allowed_domains: string[];
  denied_domains: string[];
  masked_fields: string[];
  chat_enabled: boolean;
  aggregate_only: boolean;
}

export interface ChatSuggestion {
  id: string;
  text: string;
}

export interface ChatHistoryItem {
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "blocked";
  content: string;
  createdAt: string;
  source?: string;
  latencyMs?: number;
  blockReason?: string;
}

export interface TokenFrame {
  type: "token" | "done" | "error";
  content?: string;
  source?: string;
  latency_ms?: number;
  message?: string;
}

export type PipelineStageState = "idle" | "running" | "success" | "failed" | "skipped";

export interface PipelineStage {
  key: string;
  group: string;
  name: string;
  state: PipelineStageState;
  latencyMs: number | null;
  badge?: string;
  error?: string;
}

export interface PipelineGroup {
  id: string;
  label: string;
}

export interface PipelineStageDefinition {
  key: string;
  name: string;
  group: string;
  backendStages: string[];
}

export interface PipelineStartData {
  pipeline_id: string;
  tenant_id: string;
  user_id: string;
  session_id: string;
  query_text: string;
  started_at: string;
}

export interface StageEventData {
  event_id: string;
  pipeline_id: string;
  stage_name: string;
  stage_index: number;
  status: "started" | "completed" | "error" | "skipped";
  timestamp: string;
  duration_ms?: number;
  metadata?: Record<string, unknown>;
  error_message?: string;
}

export interface PipelineCompleteData {
  pipeline_id: string;
  status: "success" | "error";
  total_duration_ms: number;
  final_message?: string;
}

export type PipelineMonitorFrame =
  | { type: "connected"; message: string }
  | { type: "pipeline_start"; data: PipelineStartData }
  | { type: "stage_event"; data: StageEventData }
  | { type: "pipeline_complete"; data: PipelineCompleteData }
  | { type: "error"; message: string };

export interface AuditLogItem {
  id: string;
  user_id: string;
  query_text: string;
  domains_accessed: string[];
  was_blocked: boolean;
  block_reason: string | null;
  latency_ms: number;
  created_at: string;
}

export interface AuditLogResponse {
  page: number;
  limit: number;
  items: AuditLogItem[];
}

export type DataSourceStatus = "connected" | "disconnected" | "error" | "paused";

export interface DataSourceItem {
  id: string;
  name: string;
  source_type: string;
  status: DataSourceStatus;
  last_sync_at: string | null;
}

export interface GovernanceRoleMap {
  role_key: string;
  display_name: string;
  allowed_domains: string[];
  masked_fields: string[];
  row_scope_mode: string | null;
  aggregate_only: boolean;
  chat_enabled: boolean;
}

export interface GovernanceLineage {
  domain: string;
  source_type: string;
  data_source_id: string | null;
  data_source_name: string | null;
  data_source_status: string | null;
  is_active: boolean;
}

export interface GovernancePolicyProof {
  proof_id: string;
  intent_hash: string;
  domain: string;
  source_type: string;
  masked_fields: string[];
  created_at: string;
}

export interface GraphOverviewResponse {
  summary: {
    total_nodes: number;
    total_edges: number;
    last_graph_rebuild_at: string;
  };
  nodes_by_type: Record<string, number>;
  edges_by_type: Record<string, number>;
  role_map: GovernanceRoleMap[];
  data_lineage: GovernanceLineage[];
  recent_policy_proofs: GovernancePolicyProof[];
}

export interface ActionTemplateItem {
  action_id: string;
  trigger: string;
  risk_classification: string;
  required_permissions: string[];
  required_data_scope: string[];
  audit_implications: string[];
  allowed_personas: string[];
  approval_requirements: {
    required?: boolean;
    approver_role?: string;
  };
  enabled?: boolean;
  override?: {
    is_enabled?: boolean;
    approval_required_override?: boolean | null;
    approver_role_override?: string | null;
    sla_hours_override?: number | null;
  } | null;
}

export interface ActionTemplateListResponse {
  templates: ActionTemplateItem[];
  health: {
    healthy: boolean;
    template_count: number;
    errors: string[];
  };
  requested_by: string;
}

export const PERSONA_BADGE_COLOR: Record<PersonaType, string> = {
  student: "bg-primary-tint text-primary-hover border-primary",
  faculty: "bg-primary-tint text-primary-hover border-primary",
  executive: "bg-primary-tint text-primary-hover border-primary",
  it_head: "bg-primary-tint text-primary-hover border-primary",
  dept_head: "bg-primary-tint text-primary-hover border-primary",
  admin_staff: "bg-primary-tint text-primary-hover border-primary",
  system_admin: "bg-primary-tint text-primary-hover border-primary",
};

export const PIPELINE_GROUPS: PipelineGroup[] = [
  { id: "intake", label: "INTAKE" },
  { id: "interpretation", label: "INTERPRETATION" },
  { id: "policy", label: "POLICY & SECURITY" },
  { id: "slm", label: "SLM" },
  { id: "execution", label: "EXECUTION" },
  { id: "output", label: "OUTPUT" },
  { id: "persistence", label: "PERSISTENCE" },
];

export const PIPELINE_STAGE_DEFINITIONS: PipelineStageDefinition[] = [
  {
    key: "intake_history",
    name: "History",
    group: "intake",
    backendStages: ["history_user_message"],
  },
  {
    key: "intake_sanitizer",
    name: "Sanitizer",
    group: "intake",
    backendStages: ["interpreter"],
  },
  {
    key: "intake_domain_gate",
    name: "Domain Gate",
    group: "intake",
    backendStages: ["interpreter"],
  },
  {
    key: "interpretation_interpreter",
    name: "Interpreter",
    group: "interpretation",
    backendStages: ["interpreter"],
  },
  {
    key: "interpretation_intent_cache",
    name: "Intent Cache",
    group: "interpretation",
    backendStages: ["intent_cache"],
  },
  {
    key: "policy_compiler",
    name: "Compiler",
    group: "policy",
    backendStages: ["compiler"],
  },
  {
    key: "policy_authorization",
    name: "Policy Authorization",
    group: "policy",
    backendStages: ["policy_authorization"],
  },
  {
    key: "slm_render",
    name: "SLM Render",
    group: "slm",
    backendStages: ["slm_render"],
  },
  {
    key: "execution_tool",
    name: "Tool Execution",
    group: "execution",
    backendStages: ["tool_execution"],
  },
  {
    key: "execution_masking",
    name: "Field Masking",
    group: "execution",
    backendStages: ["field_masking"],
  },
  {
    key: "output_policy_proof",
    name: "Policy Proof",
    group: "output",
    backendStages: ["policy_proof"],
  },
  {
    key: "output_detokenization",
    name: "Detokenization",
    group: "output",
    backendStages: ["detokenization"],
  },
  {
    key: "persistence_cache",
    name: "Cache Storage",
    group: "persistence",
    backendStages: ["cache_storage"],
  },
  {
    key: "persistence_history",
    name: "History (assistant)",
    group: "persistence",
    backendStages: ["history_assistant_message"],
  },
  {
    key: "persistence_audit",
    name: "Audit Logging",
    group: "persistence",
    backendStages: ["audit_logging", "audit_logging_error"],
  },
];
