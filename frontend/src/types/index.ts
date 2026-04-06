export type PersonaType =
  | "student"
  | "faculty"
  | "executive"
  | "it_head"
  | "dept_head"
  | "admin_staff";

export type PersonaKey =
  | "executive"
  | "student"
  | "faculty"
  | "it_head"
  | "admissions"
  | "finance"
  | "hr"
  | "exam"
  | "hod_cse"
  | "hod_ece"
  | "hod_me"
  | "hod_ce"
  | "hod_bba"
  | "hod_law"
  | "hod_med"
  | "hod_bio"
  | "hod_math"
  | "hod_art";

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

export interface PersonaOption {
  key: PersonaKey;
  type: PersonaType;
  name: string;
  email: string;
}

export interface PersonaGroupOption {
  title: string;
  items: PersonaOption[];
}

export const PERSONA_BADGE_COLOR: Record<PersonaType, string> = {
  student: "bg-sky-500/15 text-sky-300 border-sky-400/40",
  faculty: "bg-violet-500/15 text-violet-300 border-violet-400/40",
  executive: "bg-amber-400/15 text-amber-200 border-amber-300/45",
  it_head: "bg-red-500/15 text-red-200 border-red-400/45",
  dept_head: "bg-emerald-500/15 text-emerald-200 border-emerald-300/45",
  admin_staff: "bg-orange-500/15 text-orange-200 border-orange-300/45",
};

export const PERSONA_GROUPS: PersonaGroupOption[] = [
  {
    title: "Executive",
    items: [
      {
        key: "executive",
        type: "executive",
        name: "Executive Council",
        email: "executive@ipeds.local",
      },
    ],
  },
  {
    title: "Student",
    items: [
      {
        key: "student",
        type: "student",
        name: "Student Primary",
        email: "student@ipeds.local",
      },
    ],
  },
  {
    title: "Faculty",
    items: [
      {
        key: "faculty",
        type: "faculty",
        name: "Faculty Primary",
        email: "faculty@ipeds.local",
      },
    ],
  },
  {
    title: "Department Heads",
    items: [
      {
        key: "hod_cse",
        type: "dept_head",
        name: "CSE Department Head",
        email: "hod.cse@ipeds.local",
      },
      {
        key: "hod_ece",
        type: "dept_head",
        name: "ECE Department Head",
        email: "hod.ece@ipeds.local",
      },
      {
        key: "hod_me",
        type: "dept_head",
        name: "ME Department Head",
        email: "hod.me@ipeds.local",
      },
      {
        key: "hod_ce",
        type: "dept_head",
        name: "CE Department Head",
        email: "hod.ce@ipeds.local",
      },
      {
        key: "hod_bba",
        type: "dept_head",
        name: "BBA Department Head",
        email: "hod.bba@ipeds.local",
      },
      {
        key: "hod_law",
        type: "dept_head",
        name: "LAW Department Head",
        email: "hod.law@ipeds.local",
      },
      {
        key: "hod_med",
        type: "dept_head",
        name: "MED Department Head",
        email: "hod.med@ipeds.local",
      },
      {
        key: "hod_bio",
        type: "dept_head",
        name: "BIO Department Head",
        email: "hod.bio@ipeds.local",
      },
      {
        key: "hod_math",
        type: "dept_head",
        name: "MATH Department Head",
        email: "hod.math@ipeds.local",
      },
      {
        key: "hod_art",
        type: "dept_head",
        name: "ART Department Head",
        email: "hod.art@ipeds.local",
      },
    ],
  },
  {
    title: "Admin Staff",
    items: [
      {
        key: "admissions",
        type: "admin_staff",
        name: "Admissions Office",
        email: "admissions@ipeds.local",
      },
      {
        key: "finance",
        type: "admin_staff",
        name: "Finance Office",
        email: "finance@ipeds.local",
      },
      {
        key: "hr",
        type: "admin_staff",
        name: "HR Office",
        email: "hr@ipeds.local",
      },
      {
        key: "exam",
        type: "admin_staff",
        name: "Exam Office",
        email: "exam@ipeds.local",
      },
    ],
  },
  {
    title: "IT Head",
    items: [
      {
        key: "it_head",
        type: "it_head",
        name: "IT Head",
        email: "ithead@ipeds.local",
      },
    ],
  },
];

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
