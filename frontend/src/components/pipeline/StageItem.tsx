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
    dotClass: "bg-[#D0CCC0]",
    icon: Circle,
    iconClass: "text-text-muted",
  },
  running: {
    dotClass: "bg-[#F1C04B] animate-pulse-dot",
    icon: Loader2,
    iconClass: "text-[#9B6D00] animate-spin",
  },
  success: {
    dotClass: "bg-[#3E9B4F]",
    icon: CheckCircle2,
    iconClass: "text-[#2D7F3E]",
  },
  failed: {
    dotClass: "bg-[#D84A3F]",
    icon: AlertTriangle,
    iconClass: "text-[#B3261E]",
  },
  skipped: {
    dotClass: "bg-[#F1C04B]",
    icon: SkipForward,
    iconClass: "text-[#9B6D00]",
  },
};

export function StageItem({ stage, index }: { stage: PipelineStage; index: number }) {
  const visual = stageVisualMap[stage.state];
  const Icon = visual.icon;

  return (
    <div
      className="animate-slide-in-right grid grid-cols-[auto_1fr_auto] items-center gap-2 rounded-lg border border-border bg-bg px-2.5 py-2"
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
