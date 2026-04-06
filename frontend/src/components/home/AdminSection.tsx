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
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-cyan-200">
            Admin Console
          </p>
          <p className="mt-1 text-sm text-slate-300">
            Initial IT-head controls for users, sources, policies, and audit telemetry.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <input
            className="rounded-lg border border-slate-600 bg-slate-900/70 px-2 py-1.5 text-sm text-slate-100 outline-none focus:border-cyan-300"
            value={controls.userSearch}
            onChange={(event) => actions.onUserSearchChange(event.target.value)}
            placeholder="Search users"
            disabled={!controls.canAccessAdmin}
          />
          <label className="flex items-center gap-2 rounded-lg border border-slate-600 bg-slate-900/60 px-2 py-1.5 text-sm text-slate-300">
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
            className="rounded-lg border border-cyan-300/65 bg-cyan-300/10 px-3 py-1.5 text-sm font-medium text-cyan-100 transition hover:bg-cyan-300/20 disabled:cursor-not-allowed disabled:opacity-60"
            onClick={actions.onRefreshAdmin}
            disabled={!controls.canAccessAdmin || controls.adminBusy}
          >
            {controls.adminBusy ? "Refreshing..." : "Refresh Admin"}
          </button>
        </div>
      </div>

      <p className="mt-3 text-sm text-slate-300">
        {controls.canAccessAdmin
          ? controls.adminMessage || "Admin functions are ready."
          : "Admin endpoints are restricted to IT Head sessions."}
      </p>

      <div className="mt-4 grid gap-3 xl:grid-cols-4">
        <div className="rounded-xl border border-slate-600 bg-slate-900/60 p-3">
          <p className="font-mono text-xs uppercase tracking-[0.16em] text-slate-300">
            Kill Switch
          </p>
          <div className="mt-2 grid gap-2">
            <select
              className="rounded-lg border border-slate-600 bg-slate-950/70 px-2 py-1.5 text-sm text-slate-100"
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
              className="rounded-lg border border-slate-600 bg-slate-950/70 px-2 py-1.5 text-sm text-slate-100"
              placeholder="target id (if required)"
              value={controls.killTarget}
              onChange={(event) => actions.onKillTargetChange(event.target.value)}
              disabled={!controls.canAccessAdmin}
            />
            <button
              type="button"
              className="rounded-lg border border-rose-300/70 bg-rose-300/10 px-2.5 py-1.5 text-sm font-medium text-rose-100 transition hover:bg-rose-300/20 disabled:cursor-not-allowed disabled:opacity-60"
              onClick={actions.onRunKillSwitch}
              disabled={!controls.canAccessAdmin}
            >
              Apply
            </button>
          </div>
        </div>

        <div className="rounded-xl border border-slate-600 bg-slate-900/60 p-3">
          <p className="font-mono text-xs uppercase tracking-[0.16em] text-slate-300">
            Add Data Source
          </p>
          <div className="mt-2 grid gap-2">
            <input
              className="rounded-lg border border-slate-600 bg-slate-950/70 px-2 py-1.5 text-sm text-slate-100"
              placeholder="source name"
              value={controls.sourceName}
              onChange={(event) => actions.onSourceNameChange(event.target.value)}
              disabled={!controls.canAccessAdmin}
            />
            <select
              className="rounded-lg border border-slate-600 bg-slate-950/70 px-2 py-1.5 text-sm text-slate-100"
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
              className="rounded-lg border border-emerald-300/70 bg-emerald-300/10 px-2.5 py-1.5 text-sm font-medium text-emerald-100 transition hover:bg-emerald-300/20 disabled:cursor-not-allowed disabled:opacity-60"
              onClick={actions.onCreateSource}
              disabled={!controls.canAccessAdmin || !controls.sourceName.trim()}
            >
              Create
            </button>
          </div>
        </div>

        <div className="rounded-xl border border-slate-600 bg-slate-900/60 p-3">
          <p className="font-mono text-xs uppercase tracking-[0.16em] text-slate-300">
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
              className="block w-full text-xs text-slate-300"
            />
            <button
              type="button"
              className="rounded-lg border border-cyan-300/70 bg-cyan-300/10 px-2.5 py-1.5 text-sm font-medium text-cyan-100 transition hover:bg-cyan-300/20 disabled:cursor-not-allowed disabled:opacity-60"
              onClick={actions.onImportUsersCsv}
              disabled={!controls.canAccessAdmin || !controls.importFile}
            >
              Upload
            </button>
          </div>
        </div>

        <div className="rounded-xl border border-slate-600 bg-slate-900/60 p-3">
          <p className="font-mono text-xs uppercase tracking-[0.16em] text-slate-300">
            Totals
          </p>
          <div className="mt-2 grid grid-cols-2 gap-2 text-sm">
            <div className="rounded-lg border border-slate-600 bg-slate-950/70 px-2 py-1.5">
              <p className="text-[11px] text-slate-400">Users</p>
              <p className="font-semibold text-slate-100">{adminUsers.length}</p>
            </div>
            <div className="rounded-lg border border-slate-600 bg-slate-950/70 px-2 py-1.5">
              <p className="text-[11px] text-slate-400">Policies</p>
              <p className="font-semibold text-slate-100">{adminPolicies.length}</p>
            </div>
            <div className="rounded-lg border border-slate-600 bg-slate-950/70 px-2 py-1.5">
              <p className="text-[11px] text-slate-400">Sources</p>
              <p className="font-semibold text-slate-100">{adminSources.length}</p>
            </div>
            <div className="rounded-lg border border-slate-600 bg-slate-950/70 px-2 py-1.5">
              <p className="text-[11px] text-slate-400">Audit Rows</p>
              <p className="font-semibold text-slate-100">{adminAudit.length}</p>
            </div>
          </div>
        </div>
      </div>

      <div className="mt-4 grid gap-3 xl:grid-cols-2">
        <div className="rounded-xl border border-slate-600 bg-slate-900/60 p-3">
          <p className="font-mono text-xs uppercase tracking-[0.16em] text-slate-300">
            Users
          </p>
          <div className="mt-2 max-h-60 overflow-y-auto">
            <table className="w-full border-collapse text-left text-xs text-slate-200">
              <thead>
                <tr className="border-b border-slate-600 text-slate-400">
                  <th className="py-1.5">Email</th>
                  <th className="py-1.5">Persona</th>
                  <th className="py-1.5">Dept</th>
                  <th className="py-1.5">Status</th>
                </tr>
              </thead>
              <tbody>
                {adminUsers.slice(0, 24).map((row) => (
                  <tr key={row.id} className="border-b border-slate-700/70">
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

        <div className="rounded-xl border border-slate-600 bg-slate-900/60 p-3">
          <p className="font-mono text-xs uppercase tracking-[0.16em] text-slate-300">
            Audit Feed
          </p>
          <div className="mt-2 max-h-60 overflow-y-auto space-y-2">
            {adminAudit.slice(0, 18).map((item) => (
              <div
                key={item.id}
                className="rounded-lg border border-slate-700 bg-slate-950/70 p-2 text-xs"
              >
                <p className="line-clamp-2 text-slate-200">{item.query_text}</p>
                <p className="mt-1 text-slate-400">
                  {item.was_blocked ? "BLOCKED" : "ALLOWED"} • {item.latency_ms}ms • {toDisplayTime(item.created_at)}
                </p>
                {item.block_reason ? (
                  <p className="mt-1 text-rose-200">{item.block_reason}</p>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="mt-3 grid gap-3 xl:grid-cols-2">
        <div className="rounded-xl border border-slate-600 bg-slate-900/60 p-3">
          <p className="font-mono text-xs uppercase tracking-[0.16em] text-slate-300">
            Role Policies
          </p>
          <div className="mt-2 max-h-52 overflow-y-auto space-y-2 text-xs">
            {adminPolicies.slice(0, 16).map((policy) => (
              <div
                key={policy.role_key}
                className="rounded-lg border border-slate-700 bg-slate-950/70 p-2"
              >
                <p className="font-semibold text-slate-100">{policy.display_name}</p>
                <p className="mt-0.5 text-slate-400">{policy.role_key}</p>
                <p className="mt-1 text-slate-300 line-clamp-2">
                  Domains: {policy.allowed_domains.join(", ") || "none"}
                </p>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-xl border border-slate-600 bg-slate-900/60 p-3">
          <p className="font-mono text-xs uppercase tracking-[0.16em] text-slate-300">
            Data Sources
          </p>
          <div className="mt-2 max-h-52 overflow-y-auto space-y-2 text-xs">
            {adminSources.slice(0, 18).map((source) => (
              <div
                key={source.id}
                className="rounded-lg border border-slate-700 bg-slate-950/70 p-2"
              >
                <p className="font-semibold text-slate-100">{source.name}</p>
                <p className="mt-0.5 text-slate-400">
                  {source.source_type} • {source.status}
                </p>
                <p className="mt-1 text-slate-300">
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
