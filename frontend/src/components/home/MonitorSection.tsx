"use client";

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

type StageRow = {
  stageIndex: number;
  label: string;
  status: StageStatus;
  durationMs?: number;
  errorMessage?: string;
};

type MonitorSectionProps = {
  monitorConnected: boolean;
  pipelines: PipelineRecord[];
  selectedPipeline: PipelineRecord | null;
  onSelectPipeline: (pipelineId: string) => void;
  stageRows: StageRow[];
  stageClasses: Record<StageStatus, string>;
  monitorFeed: string[];
};

function toDisplayTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "--";
  }
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export function MonitorSection({
  monitorConnected,
  pipelines,
  selectedPipeline,
  onSelectPipeline,
  stageRows,
  stageClasses,
  monitorFeed,
}: MonitorSectionProps) {
  return (
    <aside className="flex min-h-[640px] flex-col gap-3">
      <section className="glass-panel rounded-2xl p-4">
        <div className="flex items-center justify-between">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-cyan-200">
            Pipeline Radar
          </p>
          <span
            className={`rounded-full border px-2 py-0.5 text-[11px] ${
              monitorConnected
                ? "border-emerald-300/60 bg-emerald-300/15 text-emerald-100"
                : "border-slate-600 bg-slate-900/70 text-slate-300"
            }`}
          >
            {monitorConnected ? "live" : "offline"}
          </span>
        </div>

        <div className="mt-3 grid gap-2">
          {pipelines.length === 0 ? (
            <div className="rounded-xl border border-slate-600 bg-slate-900/60 px-3 py-2 text-sm text-slate-300">
              No pipeline activity yet.
            </div>
          ) : (
            pipelines.slice(0, 8).map((pipeline) => (
              <button
                type="button"
                key={pipeline.id}
                onClick={() => onSelectPipeline(pipeline.id)}
                className={`rounded-xl border px-3 py-2 text-left transition ${
                  selectedPipeline?.id === pipeline.id
                    ? "border-cyan-300/65 bg-cyan-300/12"
                    : "border-slate-600 bg-slate-900/60 hover:border-cyan-300/45"
                }`}
              >
                <p className="line-clamp-1 text-sm text-slate-100">{pipeline.query}</p>
                <p className="mt-1 text-[11px] text-slate-400">
                  {pipeline.status} • {toDisplayTime(pipeline.startedAt)}
                  {typeof pipeline.totalDurationMs === "number"
                    ? ` • ${pipeline.totalDurationMs}ms`
                    : ""}
                </p>
              </button>
            ))
          )}
        </div>
      </section>

      <section className="glass-panel flex min-h-[250px] flex-col rounded-2xl p-4">
        <p className="font-mono text-xs uppercase tracking-[0.2em] text-cyan-200">
          Pipeline Stages
        </p>
        <div className="mt-3 flex-1 overflow-y-auto">
          <div className="space-y-2">
            {stageRows.map((row) => (
              <div
                key={row.stageIndex}
                className={`rounded-xl border px-2.5 py-2 ${stageClasses[row.status]}`}
              >
                <div className="flex items-center justify-between gap-2">
                  <p className="text-xs font-semibold uppercase tracking-[0.12em]">
                    {row.stageIndex}. {row.label}
                  </p>
                  <span className="font-mono text-[11px]">{row.status}</span>
                </div>
                <p className="mt-1 text-[11px] text-slate-300">
                  {typeof row.durationMs === "number" ? `${row.durationMs}ms` : "--"}
                </p>
                {row.errorMessage ? (
                  <p className="mt-1 text-[11px] text-rose-200">{row.errorMessage}</p>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="glass-panel rounded-2xl p-4">
        <p className="font-mono text-xs uppercase tracking-[0.2em] text-cyan-200">
          Monitor Terminal
        </p>
        <div className="terminal-feed mt-3 h-36 overflow-y-auto rounded-xl border border-slate-700 bg-slate-950/80 p-2 font-mono text-[11px] text-slate-300">
          {monitorFeed.length === 0
            ? "No monitor events yet."
            : monitorFeed.map((line, index) => (
                <p key={`${line}-${index}`} className="leading-5">
                  {line}
                </p>
              ))}
        </div>
      </section>
    </aside>
  );
}
