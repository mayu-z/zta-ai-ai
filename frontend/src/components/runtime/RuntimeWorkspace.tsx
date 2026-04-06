"use client";

import { motion } from "framer-motion";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { AdminSection } from "@/components/home/AdminSection";
import { AuthSection } from "@/components/home/AuthSection";
import { ChatSection } from "@/components/home/ChatSection";
import { MonitorSection } from "@/components/home/MonitorSection";

type Tone = "idle" | "loading" | "ok" | "error";

type StatusMessage = {
  tone: Tone;
  text: string;
  at: string;
};

type AuthUser = {
  id: string;
  email: string;
  name: string;
  persona: string;
  department: string | null;
};

type AuthResponse = {
  jwt: string;
  user: AuthUser;
};

type ChatSuggestion = {
  id: string;
  text: string;
};

type ChatHistoryItem = {
  role: string;
  content: string;
  created_at: string;
};

type ChatMessage = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  createdAt: string;
  source?: string;
  latencyMs?: number;
  isError?: boolean;
};

type StageStatus = "pending" | "started" | "completed" | "error" | "skipped";

type PipelineStage = {
  stageIndex: number;
  stageName: string;
  status: Exclude<StageStatus, "pending">;
  durationMs?: number;
  errorMessage?: string;
  timestamp?: string;
};

type PipelineRecord = {
  id: string;
  query: string;
  userId: string;
  startedAt: string;
  status: "running" | "success" | "error";
  totalDurationMs?: number;
  finalMessage?: string;
  stages: Record<number, PipelineStage>;
};

type PagedResponse<T> = {
  page: number;
  limit: number;
  items: T[];
};

type AdminUser = {
  id: string;
  email: string;
  name: string;
  persona_type: string;
  department: string | null;
  status: string;
  last_login: string | null;
};

type RolePolicy = {
  role_key: string;
  display_name: string;
  allowed_domains: string[];
  chat_enabled: boolean;
  aggregate_only: boolean;
};

type DataSource = {
  id: string;
  name: string;
  source_type: string;
  status: string;
  last_sync_at: string | null;
};

type AuditItem = {
  id: string;
  query_text: string;
  was_blocked: boolean;
  block_reason: string | null;
  latency_ms: number;
  created_at: string;
};

type RolePreset = {
  label: string;
  email: string;
  note: string;
};

export type RuntimeView = "chat" | "monitor" | "admin";

const SESSION_KEY = "zta-next-session-v1";
const MONITOR_STATE_KEY_PREFIX = "zta-monitor-state-v1";

const ROLE_PRESETS: RolePreset[] = [
  {
    label: "Executive",
    email: "executive@ipeds.local",
    note: "Cross-domain KPI summaries and macro insights.",
  },
  {
    label: "IT Head",
    email: "ithead@ipeds.local",
    note: "Access to security controls, policies, and admin telemetry.",
  },
  {
    label: "Faculty",
    email: "faculty@ipeds.local",
    note: "Course-scoped academic and student performance signals.",
  },
  {
    label: "Student",
    email: "student@ipeds.local",
    note: "Owner-scoped personal records and campus support.",
  },
  {
    label: "Admissions",
    email: "admissions@ipeds.local",
    note: "Admissions office pipeline and enrollment analytics.",
  },
  {
    label: "Finance",
    email: "finance@ipeds.local",
    note: "Finance office budgets, dues, and scholarship snapshots.",
  },
  {
    label: "HR",
    email: "hr@ipeds.local",
    note: "HR roster, workload, and policy-sensitive operations.",
  },
  {
    label: "Exam",
    email: "exam@ipeds.local",
    note: "Examination office schedules, records, and controls.",
  },
];

const STAGE_ORDER = [
  "history_user_message",
  "interpreter",
  "intent_cache",
  "compiler",
  "policy_authorization",
  "slm_render",
  "output_guard",
  "tool_execution",
  "field_masking",
  "detokenization",
  "cache_storage",
  "history_assistant_message",
  "audit_logging",
] as const;

const STAGE_LABELS: Record<string, string> = {
  history_user_message: "Store User Message",
  interpreter: "Interpreter Layer",
  intent_cache: "Intent Cache",
  compiler: "Compiler",
  policy_authorization: "Policy Authorization",
  slm_render: "SLM Render",
  output_guard: "Output Guard",
  tool_execution: "Tool Execution",
  field_masking: "Field Masking",
  detokenization: "Detokenization",
  cache_storage: "Cache Storage",
  history_assistant_message: "Store Assistant Message",
  audit_logging: "Audit Logging",
  audit_logging_error: "Audit Logging (Error Path)",
};

const toneClasses: Record<Tone, string> = {
  idle: "border-slate-500/50 bg-slate-900/60 text-slate-200",
  loading: "border-amber-300/50 bg-amber-300/15 text-amber-100",
  ok: "border-emerald-300/50 bg-emerald-300/15 text-emerald-100",
  error: "border-rose-300/55 bg-rose-300/20 text-rose-100",
};

const stageClasses: Record<StageStatus, string> = {
  pending: "border-slate-600 bg-slate-900/70 text-slate-300",
  started: "border-amber-400 bg-amber-300/15 text-amber-100",
  completed: "border-emerald-400 bg-emerald-300/15 text-emerald-100",
  error: "border-rose-400 bg-rose-300/20 text-rose-100",
  skipped: "border-cyan-400 bg-cyan-300/15 text-cyan-100",
};

function makeId(prefix: string): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `${prefix}-${crypto.randomUUID()}`;
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
}

function toWsBase(apiBase: string): string {
  return apiBase.trim().replace(/\/$/, "").replace(/^http/i, "ws");
}

function parseErrorText(payload: unknown, fallback: string): string {
  if (typeof payload === "string" && payload.trim()) {
    return payload;
  }
  if (typeof payload === "object" && payload !== null) {
    const record = payload as Record<string, unknown>;
    if (typeof record.error === "string" && record.error.trim()) {
      return record.error;
    }
    if (typeof record.message === "string" && record.message.trim()) {
      return record.message;
    }
  }
  return fallback;
}

function formatError(error: unknown, fallback = "Unexpected request failure"): string {
  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }
  return fallback;
}

function toDisplayTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "--";
  }
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function roleHeadline(persona: string): string {
  switch (persona) {
    case "it_head":
      return "Security command authority is active. You can inspect and govern policy and sessions.";
    case "executive":
      return "Strategic mode is active. Ask for cross-domain KPIs and trends.";
    case "faculty":
      return "Teaching operations mode is active. Course-level scope and masked data policy are enforced.";
    case "student":
      return "Personal scope is active. You can query only your owner-scoped records.";
    default:
      return "Department scope is active. Query results follow your role policy in real time.";
  }
}

function initialApiBase(): string {
  const fromEnv = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (fromEnv && fromEnv.trim()) {
    return fromEnv.trim().replace(/\/$/, "");
  }
  return "http://localhost:8000";
}

type RuntimeWorkspaceProps = {
  activeView: RuntimeView;
};

export default function RuntimeWorkspace({ activeView }: RuntimeWorkspaceProps) {
  const [apiBase, setApiBase] = useState<string>(initialApiBase());
  const [status, setStatus] = useState<StatusMessage>({
    tone: "idle",
    text: "Ready",
    at: new Date().toISOString(),
  });

  const [token, setToken] = useState<string>("");
  const [user, setUser] = useState<AuthUser | null>(null);
  const [hydrated, setHydrated] = useState(false);

  const [loginEmail, setLoginEmail] = useState("student@ipeds.local");
  const [authBusy, setAuthBusy] = useState(false);

  const [suggestions, setSuggestions] = useState<ChatSuggestion[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [query, setQuery] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);

  const [pipelinesById, setPipelinesById] = useState<Record<string, PipelineRecord>>(
    {}
  );
  const [selectedPipelineId, setSelectedPipelineId] = useState<string | null>(null);
  const [monitorConnected, setMonitorConnected] = useState(false);
  const [monitorFeed, setMonitorFeed] = useState<string[]>([]);
  const monitorSocketRef = useRef<WebSocket | null>(null);
  const monitorStateHydratedForKeyRef = useRef<string | null>(null);

  const [adminUsers, setAdminUsers] = useState<AdminUser[]>([]);
  const [adminPolicies, setAdminPolicies] = useState<RolePolicy[]>([]);
  const [adminSources, setAdminSources] = useState<DataSource[]>([]);
  const [adminAudit, setAdminAudit] = useState<AuditItem[]>([]);
  const [adminBusy, setAdminBusy] = useState(false);
  const [adminMessage, setAdminMessage] = useState<string>("");
  const [userSearch, setUserSearch] = useState("");
  const [blockedOnly, setBlockedOnly] = useState(false);
  const [killScope, setKillScope] = useState<"all" | "department" | "user">("all");
  const [killTarget, setKillTarget] = useState("");
  const [sourceName, setSourceName] = useState("");
  const [sourceType, setSourceType] = useState("sql");
  const [importFile, setImportFile] = useState<File | null>(null);

  const canAccessAdmin = user?.persona === "it_head";
  const monitorStateKey = useMemo(() => {
    if (!user?.id) {
      return null;
    }
    return `${MONITOR_STATE_KEY_PREFIX}:${user.id}`;
  }, [user?.id]);

  const setBanner = useCallback((tone: Tone, text: string) => {
    setStatus({ tone, text, at: new Date().toISOString() });
  }, []);

  const callApi = useCallback(
    async <T,>(
      path: string,
      init: RequestInit = {},
      options: { skipAuth?: boolean } = {}
    ): Promise<T> => {
      const base = apiBase.trim().replace(/\/$/, "");
      const responseUrl = `${base}${path}`;
      const headers = new Headers(init.headers ?? {});

      if (!options.skipAuth && token) {
        headers.set("Authorization", `Bearer ${token}`);
      }
      if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
        headers.set("Content-Type", "application/json");
      }

      const response = await fetch(responseUrl, {
        ...init,
        headers,
      });

      const contentType = response.headers.get("content-type") ?? "";
      const payload: unknown = contentType.includes("application/json")
        ? await response.json()
        : await response.text();

      if (!response.ok) {
        throw new Error(
          parseErrorText(payload, `Request failed (${response.status})`)
        );
      }

      return payload as T;
    },
    [apiBase, token]
  );

  const addMonitorLine = useCallback((line: string) => {
    setMonitorFeed((prev) => {
      const stamped = `${toDisplayTime(new Date().toISOString())}  ${line}`;
      return [stamped, ...prev].slice(0, 120);
    });
  }, []);

  const disconnectMonitor = useCallback(() => {
    const socket = monitorSocketRef.current;
    if (socket) {
      socket.close();
    }
    monitorSocketRef.current = null;
    setMonitorConnected(false);
  }, []);

  const handleMonitorFrame = useCallback(
    (frame: unknown) => {
      if (typeof frame !== "object" || frame === null) {
        return;
      }
      const payload = frame as Record<string, unknown>;
      const type = typeof payload.type === "string" ? payload.type : "";

      if (type === "connected") {
        addMonitorLine("Monitor handshake confirmed.");
        return;
      }

      if (type === "pipeline_start") {
        const data =
          typeof payload.data === "object" && payload.data !== null
            ? (payload.data as Record<string, unknown>)
            : null;
        if (!data) {
          return;
        }

        const pipelineId = typeof data.pipeline_id === "string" ? data.pipeline_id : "";
        if (!pipelineId) {
          return;
        }

        const record: PipelineRecord = {
          id: pipelineId,
          query: typeof data.query_text === "string" ? data.query_text : "",
          userId: typeof data.user_id === "string" ? data.user_id : "unknown",
          startedAt:
            typeof data.started_at === "string"
              ? data.started_at
              : new Date().toISOString(),
          status: "running",
          stages: {},
        };

        setPipelinesById((prev) => ({
          ...prev,
          [pipelineId]: record,
        }));

        setSelectedPipelineId((current) => current ?? pipelineId);
        addMonitorLine(`Pipeline started: ${record.query.slice(0, 70)}`);
        return;
      }

      if (type === "stage_event") {
        const data =
          typeof payload.data === "object" && payload.data !== null
            ? (payload.data as Record<string, unknown>)
            : null;
        if (!data) {
          return;
        }

        const pipelineId = typeof data.pipeline_id === "string" ? data.pipeline_id : "";
        const stageIndex =
          typeof data.stage_index === "number" ? data.stage_index : Number.NaN;
        const stageName = typeof data.stage_name === "string" ? data.stage_name : "unknown";
        const statusValue = typeof data.status === "string" ? data.status : "started";
        if (!pipelineId || Number.isNaN(stageIndex)) {
          return;
        }

        const statusNormalized: Exclude<StageStatus, "pending"> =
          statusValue === "completed" ||
          statusValue === "error" ||
          statusValue === "skipped"
            ? statusValue
            : "started";

        const stage: PipelineStage = {
          stageIndex,
          stageName,
          status: statusNormalized,
          durationMs:
            typeof data.duration_ms === "number" ? data.duration_ms : undefined,
          errorMessage:
            typeof data.error_message === "string" ? data.error_message : undefined,
          timestamp: typeof data.timestamp === "string" ? data.timestamp : undefined,
        };

        setPipelinesById((prev) => {
          const current = prev[pipelineId];
          if (!current) {
            return prev;
          }

          return {
            ...prev,
            [pipelineId]: {
              ...current,
              stages: {
                ...current.stages,
                [stageIndex]: stage,
              },
            },
          };
        });

        const stageLabel = STAGE_LABELS[stageName] ?? stageName;
        addMonitorLine(`Stage ${stageIndex} ${stageLabel}: ${statusNormalized}`);
        return;
      }

      if (type === "pipeline_complete") {
        const data =
          typeof payload.data === "object" && payload.data !== null
            ? (payload.data as Record<string, unknown>)
            : null;
        if (!data) {
          return;
        }

        const pipelineId = typeof data.pipeline_id === "string" ? data.pipeline_id : "";
        const statusValue = typeof data.status === "string" ? data.status : "success";

        if (!pipelineId) {
          return;
        }

        setPipelinesById((prev) => {
          const current = prev[pipelineId];
          if (!current) {
            return prev;
          }

          return {
            ...prev,
            [pipelineId]: {
              ...current,
              status: statusValue === "error" ? "error" : "success",
              totalDurationMs:
                typeof data.total_duration_ms === "number"
                  ? data.total_duration_ms
                  : undefined,
              finalMessage:
                typeof data.final_message === "string" ? data.final_message : undefined,
            },
          };
        });

        addMonitorLine(`Pipeline completed: ${statusValue}`);
        return;
      }

      if (type === "error") {
        const message = typeof payload.message === "string" ? payload.message : "Monitor error";
        addMonitorLine(`Monitor error: ${message}`);
      }
    },
    [addMonitorLine]
  );

  const connectMonitor = useCallback(() => {
    if (!token) {
      setBanner("error", "Authenticate first to connect the monitor.");
      return;
    }

    if (monitorSocketRef.current && monitorSocketRef.current.readyState <= 1) {
      return;
    }

    const ws = new WebSocket(
      `${toWsBase(apiBase)}/admin/pipeline/monitor?token=${encodeURIComponent(token)}`
    );
    monitorSocketRef.current = ws;

    ws.onopen = () => {
      setMonitorConnected(true);
      addMonitorLine("Pipeline monitor connected.");
    };

    ws.onmessage = (event) => {
      try {
        const frame = JSON.parse(event.data) as unknown;
        handleMonitorFrame(frame);
      } catch {
        addMonitorLine("Received non-JSON monitor frame.");
      }
    };

    ws.onerror = () => {
      setMonitorConnected(false);
      addMonitorLine("Pipeline monitor connection failed.");
    };

    ws.onclose = () => {
      setMonitorConnected(false);
      monitorSocketRef.current = null;
      addMonitorLine("Pipeline monitor disconnected.");
    };
  }, [addMonitorLine, apiBase, handleMonitorFrame, setBanner, token]);

  const loadSuggestions = useCallback(async () => {
    const payload = await callApi<ChatSuggestion[]>("/chat/suggestions");
    setSuggestions(payload);
  }, [callApi]);

  const loadHistory = useCallback(async () => {
    const payload = await callApi<ChatHistoryItem[]>("/chat/history");
    const normalized: ChatMessage[] = payload.map((item) => ({
      id: makeId("history"),
      role: item.role === "user" ? "user" : "assistant",
      content: item.content,
      createdAt: item.created_at,
    }));
    setMessages(normalized);
  }, [callApi]);

  const loadAdminSnapshot = useCallback(async () => {
    if (!canAccessAdmin) {
      setAdminUsers([]);
      setAdminPolicies([]);
      setAdminSources([]);
      setAdminAudit([]);
      return;
    }

    setAdminBusy(true);
    setAdminMessage("");
    try {
      const searchQuery = userSearch.trim();
      const usersPath = searchQuery
        ? `/admin/users?page=1&limit=30&search=${encodeURIComponent(searchQuery)}`
        : "/admin/users?page=1&limit=30";

      const [users, policies, sources, audit] = await Promise.all([
        callApi<PagedResponse<AdminUser>>(usersPath),
        callApi<RolePolicy[]>("/admin/role-policies"),
        callApi<DataSource[]>("/admin/data-sources"),
        callApi<PagedResponse<AuditItem>>(
          `/admin/audit-log?page=1&limit=30&blocked_only=${blockedOnly}`
        ),
      ]);

      setAdminUsers(users.items);
      setAdminPolicies(policies);
      setAdminSources(sources);
      setAdminAudit(audit.items);
      setAdminMessage("Admin snapshot refreshed.");
    } catch (error) {
      setAdminMessage(formatError(error));
    } finally {
      setAdminBusy(false);
    }
  }, [blockedOnly, callApi, canAccessAdmin, userSearch]);

  const logout = useCallback(async () => {
    if (token) {
      try {
        await callApi<{ message: string }>("/auth/logout", { method: "POST" });
      } catch {
        // Local cleanup still runs even if backend logout fails.
      }
    }
    disconnectMonitor();
    setToken("");
    setUser(null);
    setMessages([]);
    setSuggestions([]);
    setPipelinesById({});
    setSelectedPipelineId(null);
    setMonitorFeed([]);
    setAdminMessage("");
    setBanner("ok", "Session cleared.");
  }, [callApi, disconnectMonitor, setBanner, token]);

  const loginWithEmail = useCallback(
    async (email: string) => {
      const normalized = email.trim().toLowerCase();
      if (!normalized) {
        setBanner("error", "Email is required.");
        return;
      }

      setAuthBusy(true);
      setBanner("loading", `Authenticating ${normalized}...`);

      try {
        const payload = await callApi<AuthResponse>(
          "/auth/google",
          {
            method: "POST",
            body: JSON.stringify({ google_token: `mock:${normalized}` }),
          },
          { skipAuth: true }
        );

        setToken(payload.jwt);
        setUser(payload.user);
        setBanner("ok", `Signed in as ${payload.user.email}`);
      } catch (error) {
        setBanner("error", formatError(error));
      } finally {
        setAuthBusy(false);
      }
    },
    [callApi, setBanner]
  );

  const refreshToken = useCallback(async () => {
    if (!token) {
      return;
    }

    setBanner("loading", "Refreshing token...");
    try {
      const payload = await callApi<{ jwt: string }>(
        "/auth/refresh",
        {
          method: "POST",
          body: JSON.stringify({ jwt: token }),
        },
        { skipAuth: true }
      );
      setToken(payload.jwt);
      setBanner("ok", "Token refreshed.");
    } catch (error) {
      setBanner("error", formatError(error));
    }
  }, [callApi, setBanner, token]);

  const checkHealth = useCallback(async () => {
    setBanner("loading", "Checking API health...");
    try {
      const payload = await callApi<{ status: string; service: string }>("/health", {}, { skipAuth: true });
      setBanner("ok", `${payload.service}: ${payload.status}`);
    } catch (error) {
      setBanner("error", formatError(error));
    }
  }, [callApi, setBanner]);

  const streamQuery = useCallback(
    async (queryText: string) => {
      if (!token) {
        throw new Error("You must authenticate before streaming chat.");
      }

      return new Promise<void>((resolve, reject) => {
        const ws = new WebSocket(
          `${toWsBase(apiBase)}/chat/stream?token=${encodeURIComponent(token)}`
        );

        const userMessageId = makeId("msg-user");
        const assistantMessageId = makeId("msg-assistant");
        let settled = false;

        setMessages((prev) => [
          ...prev,
          {
            id: userMessageId,
            role: "user",
            content: queryText,
            createdAt: new Date().toISOString(),
          },
          {
            id: assistantMessageId,
            role: "assistant",
            content: "",
            createdAt: new Date().toISOString(),
          },
        ]);

        ws.onopen = () => {
          ws.send(JSON.stringify({ query: queryText }));
        };

        ws.onmessage = (event) => {
          try {
            const frame = JSON.parse(event.data) as Record<string, unknown>;
            const type = typeof frame.type === "string" ? frame.type : "";

            if (type === "token") {
              const content = typeof frame.content === "string" ? frame.content : "";
              setMessages((prev) =>
                prev.map((entry) =>
                  entry.id === assistantMessageId
                    ? { ...entry, content: `${entry.content}${content}` }
                    : entry
                )
              );
              return;
            }

            if (type === "done") {
              const source = typeof frame.source === "string" ? frame.source : "unknown";
              const latency =
                typeof frame.latency_ms === "number" ? frame.latency_ms : undefined;

              setMessages((prev) =>
                prev.map((entry) =>
                  entry.id === assistantMessageId
                    ? {
                        ...entry,
                        source,
                        latencyMs: latency,
                      }
                    : entry
                )
              );

              setBanner("ok", `Response complete from ${source}.`);
              settled = true;
              ws.close();
              resolve();
              return;
            }

            if (type === "error") {
              const message =
                typeof frame.message === "string"
                  ? frame.message
                  : "Streaming failed.";

              setMessages((prev) =>
                prev.map((entry) =>
                  entry.id === assistantMessageId
                    ? {
                        ...entry,
                        content: message,
                        isError: true,
                      }
                    : entry
                )
              );

              setBanner("error", message);
              settled = true;
              ws.close();
              reject(new Error(message));
            }
          } catch {
            setBanner("error", "Received malformed stream frame.");
          }
        };

        ws.onerror = () => {
          const message = "WebSocket stream connection failed.";
          setBanner("error", message);
          if (!settled) {
            reject(new Error(message));
          }
          settled = true;
        };

        ws.onclose = () => {
          if (!settled) {
            const message = "Stream closed before completion.";
            setBanner("error", message);
            reject(new Error(message));
          }
        };
      });
    },
    [apiBase, setBanner, token]
  );

  const submitChat = useCallback(
    async (presetQuery?: string) => {
      const message = (presetQuery ?? query).trim();
      if (!message || isStreaming) {
        return;
      }

      setQuery("");
      setIsStreaming(true);
      setBanner("loading", "Streaming response...");
      try {
        await streamQuery(message);
      } catch {
        // status is set in stream handler
      } finally {
        setIsStreaming(false);
      }
    },
    [isStreaming, query, setBanner, streamQuery]
  );

  const runKillSwitch = useCallback(async () => {
    if (!canAccessAdmin) {
      return;
    }

    setAdminMessage("Applying kill switch...");
    try {
      const payload = await callApi<{ sessions_revoked: string | number }>(
        "/admin/security/kill",
        {
          method: "POST",
          body: JSON.stringify({
            scope: killScope,
            target_id: killTarget.trim() || null,
          }),
        }
      );
      setAdminMessage(`Kill switch applied (${String(payload.sessions_revoked)}).`);
    } catch (error) {
      setAdminMessage(formatError(error));
    }
  }, [callApi, canAccessAdmin, killScope, killTarget]);

  const createSource = useCallback(async () => {
    if (!canAccessAdmin || !sourceName.trim()) {
      return;
    }

    try {
      await callApi<{ id: string }>("/admin/data-sources", {
        method: "POST",
        body: JSON.stringify({
          name: sourceName.trim(),
          source_type: sourceType,
          config: {},
          department_scope: [],
        }),
      });
      setSourceName("");
      setAdminMessage("Data source created.");
      await loadAdminSnapshot();
    } catch (error) {
      setAdminMessage(formatError(error));
    }
  }, [callApi, canAccessAdmin, loadAdminSnapshot, sourceName, sourceType]);

  const importUsersCsv = useCallback(async () => {
    if (!canAccessAdmin || !importFile) {
      return;
    }

    const formData = new FormData();
    formData.append("file", importFile);

    try {
      const payload = await callApi<{ imported: number; failed: number }>(
        "/admin/users/import",
        {
          method: "POST",
          body: formData,
        }
      );
      setAdminMessage(`CSV import finished: ${payload.imported} imported, ${payload.failed} failed.`);
      setImportFile(null);
      await loadAdminSnapshot();
    } catch (error) {
      setAdminMessage(formatError(error));
    }
  }, [callApi, canAccessAdmin, importFile, loadAdminSnapshot]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    const raw = window.localStorage.getItem(SESSION_KEY);
    if (!raw) {
      setHydrated(true);
      return;
    }

    try {
      const parsed = JSON.parse(raw) as {
        apiBase?: string;
        token?: string;
        user?: AuthUser | null;
      };

      if (typeof parsed.apiBase === "string" && parsed.apiBase.trim()) {
        setApiBase(parsed.apiBase.trim().replace(/\/$/, ""));
      }
      if (typeof parsed.token === "string") {
        setToken(parsed.token);
      }
      if (parsed.user && typeof parsed.user === "object") {
        setUser(parsed.user);
      }
    } catch {
      // ignore corrupt local session payload
    } finally {
      setHydrated(true);
    }
  }, []);

  useEffect(() => {
    if (!hydrated || typeof window === "undefined") {
      return;
    }

    const payload = JSON.stringify({
      apiBase,
      token,
      user,
    });
    window.localStorage.setItem(SESSION_KEY, payload);
  }, [apiBase, hydrated, token, user]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    if (!monitorStateKey) {
      monitorStateHydratedForKeyRef.current = null;
      return;
    }

    if (monitorStateHydratedForKeyRef.current === monitorStateKey) {
      return;
    }

    const raw = window.sessionStorage.getItem(monitorStateKey);
    if (!raw) {
      monitorStateHydratedForKeyRef.current = monitorStateKey;
      return;
    }

    try {
      const parsed = JSON.parse(raw) as {
        pipelinesById?: Record<string, PipelineRecord>;
        selectedPipelineId?: string | null;
        monitorFeed?: string[];
      };

      if (parsed.pipelinesById && typeof parsed.pipelinesById === "object") {
        setPipelinesById(parsed.pipelinesById);
      }
      if (
        typeof parsed.selectedPipelineId === "string" ||
        parsed.selectedPipelineId === null
      ) {
        setSelectedPipelineId(parsed.selectedPipelineId ?? null);
      }
      if (Array.isArray(parsed.monitorFeed)) {
        setMonitorFeed(parsed.monitorFeed.slice(0, 120));
      }
    } catch {
      window.sessionStorage.removeItem(monitorStateKey);
    } finally {
      monitorStateHydratedForKeyRef.current = monitorStateKey;
    }
  }, [monitorStateKey]);

  useEffect(() => {
    if (typeof window === "undefined" || !monitorStateKey) {
      return;
    }

    const payload = JSON.stringify({
      pipelinesById,
      selectedPipelineId,
      monitorFeed: monitorFeed.slice(0, 120),
      savedAt: new Date().toISOString(),
    });

    window.sessionStorage.setItem(monitorStateKey, payload);
  }, [monitorFeed, monitorStateKey, pipelinesById, selectedPipelineId]);

  useEffect(() => {
    if (!token || !user) {
      disconnectMonitor();
      return;
    }

    void loadSuggestions().catch((error: unknown) => {
      setBanner("error", formatError(error));
    });
    void loadHistory().catch((error: unknown) => {
      setBanner("error", formatError(error));
    });

    connectMonitor();

    return () => {
      disconnectMonitor();
    };
  }, [
    connectMonitor,
    disconnectMonitor,
    loadHistory,
    loadSuggestions,
    setBanner,
    token,
    user,
  ]);

  useEffect(() => {
    if (!token || !canAccessAdmin) {
      return;
    }
    void loadAdminSnapshot();
  }, [canAccessAdmin, loadAdminSnapshot, token]);

  useEffect(() => {
    return () => {
      disconnectMonitor();
    };
  }, [disconnectMonitor]);

  const pipelines = useMemo(
    () =>
      Object.values(pipelinesById).sort(
        (a, b) =>
          new Date(b.startedAt).getTime() - new Date(a.startedAt).getTime()
      ),
    [pipelinesById]
  );

  const selectedPipeline = useMemo(() => {
    if (selectedPipelineId && pipelinesById[selectedPipelineId]) {
      return pipelinesById[selectedPipelineId];
    }
    return pipelines[0] ?? null;
  }, [pipelines, pipelinesById, selectedPipelineId]);

  const stageRows = useMemo(() => {
    return STAGE_ORDER.map((stageName, stageIndex) => {
      const event = selectedPipeline?.stages[stageIndex];
      const resolvedName = event?.stageName ?? stageName;
      const label = STAGE_LABELS[resolvedName] ?? resolvedName;
      return {
        stageIndex,
        label,
        status: (event?.status ?? "pending") as StageStatus,
        durationMs: event?.durationMs,
        errorMessage: event?.errorMessage,
      };
    });
  }, [selectedPipeline]);

  if (!hydrated) {
    return (
      <div className="flex min-h-screen items-center justify-center p-8 text-slate-100">
        <div className="glass-panel w-full max-w-md rounded-2xl p-8 text-center">
          <p className="font-mono text-xs uppercase tracking-[0.28em] text-cyan-200">
            ZTA Command Center
          </p>
          <p className="mt-4 text-slate-300">Restoring local session...</p>
        </div>
      </div>
    );
  }

  if (!token || !user) {
    return (
      <AuthSection
        apiBase={apiBase}
        onApiBaseChange={setApiBase}
        status={status}
        toneClasses={toneClasses}
        onHealthCheck={() => {
          void checkHealth();
        }}
        rolePresets={ROLE_PRESETS}
        onLoginWithEmail={(email) => {
          void loginWithEmail(email);
        }}
        authBusy={authBusy}
        loginEmail={loginEmail}
        onLoginEmailChange={setLoginEmail}
      />
    );
  }

  return (
    <div className="min-h-screen px-3 pb-4 pt-3 text-slate-100 md:px-4 md:pt-4">
      <motion.div
        className="mx-auto flex w-full max-w-[1680px] flex-col gap-3"
        initial={{ opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.28, ease: "easeOut" }}
      >
        <header className="glass-panel rounded-2xl px-4 py-4 md:px-5">
          <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
            <div>
              <p className="font-mono text-xs uppercase tracking-[0.24em] text-cyan-200">
                ZTA Campus Runtime
              </p>
              <h1 className="mt-2 text-xl font-semibold tracking-tight md:text-3xl">
                {user.name} :: {user.persona}
              </h1>
              <p className="mt-2 text-sm text-slate-300">{roleHeadline(user.persona)}</p>
            </div>

            <div className="grid gap-2 text-sm md:grid-cols-2 xl:grid-cols-4">
              <label className="flex min-w-[210px] flex-col gap-1 text-[11px] uppercase tracking-[0.18em] text-slate-400">
                API Base
                <input
                  className="rounded-lg border border-slate-600 bg-slate-900/70 px-2 py-1.5 text-sm text-slate-100 outline-none transition focus:border-cyan-300"
                  value={apiBase}
                  onChange={(event) => setApiBase(event.target.value)}
                />
              </label>

              <div className="rounded-lg border border-slate-600 bg-slate-900/60 px-3 py-2">
                <p className="text-[11px] uppercase tracking-[0.17em] text-slate-400">Persona</p>
                <p className="font-medium text-slate-100">{user.persona}</p>
              </div>

              <div className="rounded-lg border border-slate-600 bg-slate-900/60 px-3 py-2">
                <p className="text-[11px] uppercase tracking-[0.17em] text-slate-400">Department</p>
                <p className="font-medium text-slate-100">{user.department ?? "--"}</p>
              </div>

              <div className={`rounded-lg border px-3 py-2 ${toneClasses[status.tone]}`}>
                <p className="text-[11px] uppercase tracking-[0.17em]">Status</p>
                <p className="font-medium">{status.text}</p>
              </div>
            </div>
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-2">
            <button
              type="button"
              className="rounded-lg border border-cyan-300/65 bg-cyan-300/10 px-3 py-1.5 text-sm font-medium text-cyan-100 transition hover:bg-cyan-300/20"
              onClick={() => void refreshToken()}
            >
              Refresh Token
            </button>
            <button
              type="button"
              className="rounded-lg border border-emerald-300/65 bg-emerald-300/10 px-3 py-1.5 text-sm font-medium text-emerald-100 transition hover:bg-emerald-300/20"
              onClick={() => void checkHealth()}
            >
              Health Check
            </button>
            <button
              type="button"
              className="rounded-lg border border-amber-300/65 bg-amber-300/10 px-3 py-1.5 text-sm font-medium text-amber-100 transition hover:bg-amber-300/20"
              onClick={() => {
                if (monitorConnected) {
                  disconnectMonitor();
                } else {
                  connectMonitor();
                }
              }}
            >
              {monitorConnected ? "Disconnect Monitor" : "Connect Monitor"}
            </button>
            <button
              type="button"
              className="rounded-lg border border-rose-300/70 bg-rose-300/10 px-3 py-1.5 text-sm font-medium text-rose-100 transition hover:bg-rose-300/20"
              onClick={() => void logout()}
            >
              Logout
            </button>
          </div>

          <nav className="mt-3 flex flex-wrap gap-2">
            <Link
              href="/chat"
              className={`rounded-lg border px-3 py-1.5 text-sm font-medium transition ${
                activeView === "chat"
                  ? "border-cyan-300/75 bg-cyan-300/20 text-cyan-100"
                  : "border-slate-600 bg-slate-900/50 text-slate-200 hover:border-cyan-300/45"
              }`}
            >
              Chat Workspace
            </Link>
            <Link
              href="/monitor"
              className={`rounded-lg border px-3 py-1.5 text-sm font-medium transition ${
                activeView === "monitor"
                  ? "border-cyan-300/75 bg-cyan-300/20 text-cyan-100"
                  : "border-slate-600 bg-slate-900/50 text-slate-200 hover:border-cyan-300/45"
              }`}
            >
              Pipeline Monitor
            </Link>
            <Link
              href="/admin"
              className={`rounded-lg border px-3 py-1.5 text-sm font-medium transition ${
                activeView === "admin"
                  ? "border-cyan-300/75 bg-cyan-300/20 text-cyan-100"
                  : "border-slate-600 bg-slate-900/50 text-slate-200 hover:border-cyan-300/45"
              }`}
            >
              Admin Console
            </Link>
          </nav>
        </header>

        {activeView === "chat" ? (
          <main className="grid gap-3 xl:grid-cols-[320px_minmax(0,1fr)]">
            <ChatSection
              suggestions={suggestions}
              messages={messages}
              query={query}
              onQueryChange={setQuery}
              isStreaming={isStreaming}
              onSubmitChat={(presetQuery) => {
                void submitChat(presetQuery);
              }}
            />
          </main>
        ) : null}

        {activeView === "monitor" ? (
          <main className="grid gap-3 xl:grid-cols-[minmax(0,1fr)]">
            <MonitorSection
              monitorConnected={monitorConnected}
              pipelines={pipelines}
              selectedPipeline={selectedPipeline}
              onSelectPipeline={setSelectedPipelineId}
              stageRows={stageRows}
              stageClasses={stageClasses}
              monitorFeed={monitorFeed}
            />
          </main>
        ) : null}

        {activeView === "admin" ? (
          <AdminSection
            controls={{
              canAccessAdmin,
              adminBusy,
              adminMessage,
              userSearch,
              blockedOnly,
              killScope,
              killTarget,
              sourceName,
              sourceType,
              importFile,
            }}
            actions={{
              onUserSearchChange: setUserSearch,
              onBlockedOnlyChange: setBlockedOnly,
              onRefreshAdmin: () => {
                void loadAdminSnapshot();
              },
              onKillScopeChange: setKillScope,
              onKillTargetChange: setKillTarget,
              onRunKillSwitch: () => {
                void runKillSwitch();
              },
              onSourceNameChange: setSourceName,
              onSourceTypeChange: setSourceType,
              onCreateSource: () => {
                void createSource();
              },
              onImportFileChange: setImportFile,
              onImportUsersCsv: () => {
                void importUsersCsv();
              },
            }}
            adminUsers={adminUsers}
            adminPolicies={adminPolicies}
            adminSources={adminSources}
            adminAudit={adminAudit}
          />
        ) : null}
      </motion.div>
    </div>
  );
}
