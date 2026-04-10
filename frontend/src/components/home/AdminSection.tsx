"use client";

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

type KillScope = "all" | "department" | "user";

type AdminControls = {
  canAccessAdmin: boolean;
  adminBusy: boolean;
  adminMessage: string;
  userSearch: string;
  blockedOnly: boolean;
  killScope: KillScope;
  killTarget: string;
  sourceName: string;
  sourceType: string;
  importFile: File | null;
};

type AdminActions = {
  onUserSearchChange: (value: string) => void;
  onBlockedOnlyChange: (value: boolean) => void;
  onRefreshAdmin: () => void;
  onKillScopeChange: (value: KillScope) => void;
  onKillTargetChange: (value: string) => void;
  onRunKillSwitch: () => void;
  onSourceNameChange: (value: string) => void;
  onSourceTypeChange: (value: string) => void;
  onCreateSource: () => void;
  onImportFileChange: (file: File | null) => void;
  onImportUsersCsv: () => void;
};

type AdminSectionProps = {
  controls: AdminControls;
  actions: AdminActions;
  adminUsers: AdminUser[];
  adminPolicies: RolePolicy[];
  adminSources: DataSource[];
  adminAudit: AuditItem[];
};

function toDisplayTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "--";
  }
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export function AdminSection({
  controls,
  actions,
  adminUsers,
  adminPolicies,
  adminSources,
  adminAudit,
}: AdminSectionProps) {
  return (
    <section className="glass-panel rounded-2xl p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-primary-hover">
            Admin Console
          </p>
          <p className="mt-1 text-sm text-text-muted">
            Initial IT-head controls for users, sources, policies, and audit telemetry.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <input
            className="rounded-lg border border-border bg-bg px-2 py-1.5 text-sm text-text outline-none focus:border-primary"
            value={controls.userSearch}
            onChange={(event) => actions.onUserSearchChange(event.target.value)}
            placeholder="Search users"
            disabled={!controls.canAccessAdmin}
          />
          <label className="flex items-center gap-2 rounded-lg border border-border bg-bg px-2 py-1.5 text-sm text-text-muted">
            <input
              type="checkbox"
              checked={controls.blockedOnly}
              onChange={(event) => actions.onBlockedOnlyChange(event.target.checked)}
              disabled={!controls.canAccessAdmin}
            />
            blocked only
          </label>
          <button
            type="button"
            className="rounded-lg border border-primary bg-primary-tint px-3 py-1.5 text-sm font-medium text-primary-hover transition hover:bg-primary-tint disabled:cursor-not-allowed disabled:opacity-60"
            onClick={actions.onRefreshAdmin}
            disabled={!controls.canAccessAdmin || controls.adminBusy}
          >
            {controls.adminBusy ? "Refreshing..." : "Refresh Admin"}
          </button>
        </div>
      </div>

      <p className="mt-3 text-sm text-text-muted">
        {controls.canAccessAdmin
          ? controls.adminMessage || "Admin functions are ready."
          : "Admin endpoints are restricted to IT Head sessions."}
      </p>

      <div className="mt-4 grid gap-3 xl:grid-cols-4">
        <div className="rounded-xl border border-border bg-bg p-3">
          <p className="font-mono text-xs uppercase tracking-[0.16em] text-text-muted">
            Kill Switch
          </p>
          <div className="mt-2 grid gap-2">
            <select
              className="rounded-lg border border-border bg-bg px-2 py-1.5 text-sm text-text"
              value={controls.killScope}
              onChange={(event) =>
                actions.onKillScopeChange(event.target.value as KillScope)
              }
              disabled={!controls.canAccessAdmin}
            >
              <option value="all">all</option>
              <option value="department">department</option>
              <option value="user">user</option>
            </select>
            <input
              className="rounded-lg border border-border bg-bg px-2 py-1.5 text-sm text-text"
              placeholder="target id (if required)"
              value={controls.killTarget}
              onChange={(event) => actions.onKillTargetChange(event.target.value)}
              disabled={!controls.canAccessAdmin}
            />
            <button
              type="button"
              className="rounded-lg border border-primary bg-primary-tint px-2.5 py-1.5 text-sm font-medium text-primary-hover transition hover:bg-primary-tint disabled:cursor-not-allowed disabled:opacity-60"
              onClick={actions.onRunKillSwitch}
              disabled={!controls.canAccessAdmin}
            >
              Apply
            </button>
          </div>
        </div>

        <div className="rounded-xl border border-border bg-bg p-3">
          <p className="font-mono text-xs uppercase tracking-[0.16em] text-text-muted">
            Add Data Source
          </p>
          <div className="mt-2 grid gap-2">
            <input
              className="rounded-lg border border-border bg-bg px-2 py-1.5 text-sm text-text"
              placeholder="source name"
              value={controls.sourceName}
              onChange={(event) => actions.onSourceNameChange(event.target.value)}
              disabled={!controls.canAccessAdmin}
            />
            <select
              className="rounded-lg border border-border bg-bg px-2 py-1.5 text-sm text-text"
              value={controls.sourceType}
              onChange={(event) => actions.onSourceTypeChange(event.target.value)}
              disabled={!controls.canAccessAdmin}
            >
              <option value="sql">sql</option>
              <option value="api">api</option>
              <option value="file">file</option>
              <option value="cache">cache</option>
            </select>
            <button
              type="button"
              className="rounded-lg border border-primary bg-primary-tint px-2.5 py-1.5 text-sm font-medium text-primary-hover transition hover:bg-primary-tint disabled:cursor-not-allowed disabled:opacity-60"
              onClick={actions.onCreateSource}
              disabled={!controls.canAccessAdmin || !controls.sourceName.trim()}
            >
              Create
            </button>
          </div>
        </div>

        <div className="rounded-xl border border-border bg-bg p-3">
          <p className="font-mono text-xs uppercase tracking-[0.16em] text-text-muted">
            Import Users CSV
          </p>
          <div className="mt-2 grid gap-2">
            <input
              type="file"
              accept=".csv"
              onChange={(event) => {
                const file = event.target.files?.[0] ?? null;
                actions.onImportFileChange(file);
              }}
              disabled={!controls.canAccessAdmin}
              className="block w-full text-xs text-text-muted"
            />
            <button
              type="button"
              className="rounded-lg border border-primary bg-primary-tint px-2.5 py-1.5 text-sm font-medium text-primary-hover transition hover:bg-primary-tint disabled:cursor-not-allowed disabled:opacity-60"
              onClick={actions.onImportUsersCsv}
              disabled={!controls.canAccessAdmin || !controls.importFile}
            >
              Upload
            </button>
          </div>
        </div>

        <div className="rounded-xl border border-border bg-bg p-3">
          <p className="font-mono text-xs uppercase tracking-[0.16em] text-text-muted">
            Totals
          </p>
          <div className="mt-2 grid grid-cols-2 gap-2 text-sm">
            <div className="rounded-lg border border-border bg-bg px-2 py-1.5">
              <p className="text-[11px] text-text-muted">Users</p>
              <p className="font-semibold text-text">{adminUsers.length}</p>
            </div>
            <div className="rounded-lg border border-border bg-bg px-2 py-1.5">
              <p className="text-[11px] text-text-muted">Policies</p>
              <p className="font-semibold text-text">{adminPolicies.length}</p>
            </div>
            <div className="rounded-lg border border-border bg-bg px-2 py-1.5">
              <p className="text-[11px] text-text-muted">Sources</p>
              <p className="font-semibold text-text">{adminSources.length}</p>
            </div>
            <div className="rounded-lg border border-border bg-bg px-2 py-1.5">
              <p className="text-[11px] text-text-muted">Audit Rows</p>
              <p className="font-semibold text-text">{adminAudit.length}</p>
            </div>
          </div>
        </div>
      </div>

      <div className="mt-4 grid gap-3 xl:grid-cols-2">
        <div className="rounded-xl border border-border bg-bg p-3">
          <p className="font-mono text-xs uppercase tracking-[0.16em] text-text-muted">
            Users
          </p>
          <div className="mt-2 max-h-60 overflow-y-auto">
            <table className="w-full border-collapse text-left text-xs text-text">
              <thead>
                <tr className="border-b border-border text-text-muted">
                  <th className="py-1.5">Email</th>
                  <th className="py-1.5">Persona</th>
                  <th className="py-1.5">Dept</th>
                  <th className="py-1.5">Status</th>
                </tr>
              </thead>
              <tbody>
                {adminUsers.slice(0, 24).map((row) => (
                  <tr key={row.id} className="border-b border-border">
                    <td className="py-1.5 pr-2">{row.email}</td>
                    <td className="py-1.5 pr-2">{row.persona_type}</td>
                    <td className="py-1.5 pr-2">{row.department ?? "--"}</td>
                    <td className="py-1.5 pr-2">{row.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="rounded-xl border border-border bg-bg p-3">
          <p className="font-mono text-xs uppercase tracking-[0.16em] text-text-muted">
            Audit Feed
          </p>
          <div className="mt-2 max-h-60 overflow-y-auto space-y-2">
            {adminAudit.slice(0, 18).map((item) => (
              <div
                key={item.id}
                className="rounded-lg border border-border bg-bg p-2 text-xs"
              >
                <p className="line-clamp-2 text-text">{item.query_text}</p>
                <p className="mt-1 text-text-muted">
                  {item.was_blocked ? "BLOCKED" : "ALLOWED"} • {item.latency_ms}ms • {toDisplayTime(item.created_at)}
                </p>
                {item.block_reason ? (
                  <p className="mt-1 text-primary-hover">{item.block_reason}</p>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="mt-3 grid gap-3 xl:grid-cols-2">
        <div className="rounded-xl border border-border bg-bg p-3">
          <p className="font-mono text-xs uppercase tracking-[0.16em] text-text-muted">
            Role Policies
          </p>
          <div className="mt-2 max-h-52 overflow-y-auto space-y-2 text-xs">
            {adminPolicies.slice(0, 16).map((policy) => (
              <div
                key={policy.role_key}
                className="rounded-lg border border-border bg-bg p-2"
              >
                <p className="font-semibold text-text">{policy.display_name}</p>
                <p className="mt-0.5 text-text-muted">{policy.role_key}</p>
                <p className="mt-1 text-text-muted line-clamp-2">
                  Domains: {policy.allowed_domains.join(", ") || "none"}
                </p>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-xl border border-border bg-bg p-3">
          <p className="font-mono text-xs uppercase tracking-[0.16em] text-text-muted">
            Data Sources
          </p>
          <div className="mt-2 max-h-52 overflow-y-auto space-y-2 text-xs">
            {adminSources.slice(0, 18).map((source) => (
              <div
                key={source.id}
                className="rounded-lg border border-border bg-bg p-2"
              >
                <p className="font-semibold text-text">{source.name}</p>
                <p className="mt-0.5 text-text-muted">
                  {source.source_type} • {source.status}
                </p>
                <p className="mt-1 text-text-muted">
                  Last sync: {source.last_sync_at ? toDisplayTime(source.last_sync_at) : "--"}
                </p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
