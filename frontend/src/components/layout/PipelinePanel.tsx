"use client";

import { ChevronLeft, ChevronRight, Radio } from "lucide-react";
import { useMemo, useState } from "react";

import { StageGroup } from "@/components/pipeline/StageGroup";
import { Accordion } from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PIPELINE_GROUPS } from "@/types";
import { usePipelineStore } from "@/stores/pipelineStore";

export function PipelinePanel() {
  const [collapsed, setCollapsed] = useState(false);
  const stages = usePipelineStore((state) => state.stages);
  const isActive = usePipelineStore((state) => state.isActive);
  const totalLatencyMs = usePipelineStore((state) => state.totalLatencyMs);

  const grouped = useMemo(() => {
    return PIPELINE_GROUPS.map((group) => ({
      ...group,
      stages: stages.filter((stage) => stage.group === group.id),
    })).filter((group) => group.stages.length > 0);
  }, [stages]);

  if (collapsed) {
    return (
      <aside className="glass-card hidden h-[calc(100vh-2rem)] w-12 shrink-0 items-start justify-center rounded-xl border border-white/10 pt-3 lg:flex">
        <Button
          size="icon"
          variant="ghost"
          className="h-8 w-8 border border-white/10"
          onClick={() => setCollapsed(false)}
          aria-label="Expand pipeline panel"
        >
          <ChevronLeft className="h-4 w-4" />
        </Button>
      </aside>
    );
  }

  return (
    <aside className="glass-card hidden h-[calc(100vh-2rem)] w-[320px] shrink-0 rounded-xl border border-white/10 p-3 lg:flex lg:flex-col">
      <header className="mb-2 flex items-center justify-between gap-2 border-b border-white/10 pb-2">
        <div>
          <h3 className="text-sm font-semibold uppercase tracking-[0.12em] text-text-primary">Pipeline</h3>
          <Badge variant={isActive ? "success" : "default"} className="mt-1 gap-1.5">
            <Radio className={`h-3 w-3 ${isActive ? "animate-pulse-dot" : ""}`} />
            {isActive ? "Live" : "Idle"}
          </Badge>
        </div>
        <Button
          size="icon"
          variant="ghost"
          className="h-8 w-8 border border-white/10"
          onClick={() => setCollapsed(true)}
          aria-label="Collapse pipeline panel"
        >
          <ChevronRight className="h-4 w-4" />
        </Button>
      </header>

      <div className="thin-scroll flex-1 overflow-y-auto pr-1">
        <Accordion type="multiple" defaultValue={PIPELINE_GROUPS.map((group) => group.id)}>
          {grouped.map((group) => (
            <StageGroup
              key={group.id}
              groupId={group.id}
              label={group.label}
              stages={group.stages}
            />
          ))}
        </Accordion>
      </div>

      <div className="mt-3 rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-sm text-text-muted">
        Total latency:{" "}
        <span className="mono-number text-text-primary">
          {typeof totalLatencyMs === "number" ? `${totalLatencyMs}ms` : "--"}
        </span>
      </div>
    </aside>
  );
}
