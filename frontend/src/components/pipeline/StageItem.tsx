import type { ComponentType } from "react";

import { AlertTriangle, CheckCircle2, Circle, Loader2, SkipForward } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { PipelineStage } from "@/types";

type StageVisual = {
  dotClass: string;
  icon: ComponentType<{ className?: string }>;
  iconClass: string;
};

const stageVisualMap: Record<PipelineStage["state"], StageVisual> = {
  idle: {
    dotClass: "bg-slate-500/70",
    icon: Circle,
    iconClass: "text-slate-400",
  },
  running: {
    dotClass: "bg-amber-400 animate-pulse-dot",
    icon: Loader2,
    iconClass: "text-amber-300 animate-spin",
  },
  success: {
    dotClass: "bg-emerald-400",
    icon: CheckCircle2,
    iconClass: "text-emerald-300",
  },
  failed: {
    dotClass: "bg-red-400",
    icon: AlertTriangle,
    iconClass: "text-red-300",
  },
  skipped: {
    dotClass: "bg-sky-400",
    icon: SkipForward,
    iconClass: "text-sky-300",
  },
};

export function StageItem({ stage, index }: { stage: PipelineStage; index: number }) {
  const visual = stageVisualMap[stage.state];
  const Icon = visual.icon;

  return (
    <div
      className="animate-slide-in-right grid grid-cols-[auto_1fr_auto] items-center gap-2 rounded-lg border border-white/8 bg-black/20 px-2.5 py-2"
      style={{ animationDelay: `${index * 35}ms` }}
    >
      <span className={cn("h-2.5 w-2.5 rounded-full", visual.dotClass)} />
      <div className="flex min-w-0 items-center gap-2">
        <Icon className={cn("h-3.5 w-3.5 shrink-0", visual.iconClass)} />
        <span className="truncate text-xs text-text-primary">{stage.name}</span>
        {stage.badge ? (
          <Badge variant="accent" className="ml-1 px-1.5 py-0 text-[10px] uppercase tracking-wide">
            {stage.badge}
          </Badge>
        ) : null}
      </div>
      <span className="mono-number text-[11px] text-text-muted">
        {stage.latencyMs !== null ? `${stage.latencyMs}ms` : "--"}
      </span>
    </div>
  );
}
