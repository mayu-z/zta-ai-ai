import { create } from "zustand";

import {
  PIPELINE_STAGE_DEFINITIONS,
  type PipelineMonitorFrame,
  type PipelineStage,
  type PipelineStageState,
} from "@/types";

interface PipelineState {
  stages: PipelineStage[];
  currentPipelineId: string | null;
  expectedQuery: string | null;
  isActive: boolean;
  totalLatencyMs: number | null;
  prepareForQuery: (query: string) => void;
  reset: () => void;
  handleMonitorFrame: (frame: PipelineMonitorFrame, userId?: string) => void;
}

function createInitialStages(): PipelineStage[] {
  return PIPELINE_STAGE_DEFINITIONS.map((definition) => ({
    key: definition.key,
    group: definition.group,
    name: definition.name,
    state: "idle",
    latencyMs: null,
    badge: undefined,
    error: undefined,
  }));
}

function normalizeStageState(status: "started" | "completed" | "error" | "skipped"): PipelineStageState {
  if (status === "started") {
    return "running";
  }
  if (status === "completed") {
    return "success";
  }
  if (status === "error") {
    return "failed";
  }
  return "skipped";
}

function normalizedQuery(query: string): string {
  return query.trim().toLowerCase();
}

function mapBackendStageToKeys(stageName: string): string[] {
  return PIPELINE_STAGE_DEFINITIONS.filter((definition) =>
    definition.backendStages.includes(stageName)
  ).map((definition) => definition.key);
}

export const usePipelineStore = create<PipelineState>((set) => ({
  stages: createInitialStages(),
  currentPipelineId: null,
  expectedQuery: null,
  isActive: false,
  totalLatencyMs: null,
  prepareForQuery: (query) => {
    set({
      stages: createInitialStages(),
      currentPipelineId: null,
      expectedQuery: query,
      isActive: true,
      totalLatencyMs: null,
    });
  },
  reset: () => {
    set({
      stages: createInitialStages(),
      currentPipelineId: null,
      expectedQuery: null,
      isActive: false,
      totalLatencyMs: null,
    });
  },
  handleMonitorFrame: (frame, userId) => {
    set((state) => {
      if (frame.type === "pipeline_start") {
        if (userId && frame.data.user_id !== userId) {
          return state;
        }

        if (
          state.expectedQuery &&
          normalizedQuery(frame.data.query_text) !== normalizedQuery(state.expectedQuery)
        ) {
          return state;
        }

        return {
          ...state,
          currentPipelineId: frame.data.pipeline_id,
          isActive: true,
          totalLatencyMs: null,
        };
      }

      if (frame.type === "stage_event") {
        if (!state.currentPipelineId || frame.data.pipeline_id !== state.currentPipelineId) {
          return state;
        }

        const stageKeys = mapBackendStageToKeys(frame.data.stage_name);
        if (stageKeys.length === 0) {
          return state;
        }

        const nextState = normalizeStageState(frame.data.status);
        const nextStages = state.stages.map((stage) => {
          if (!stageKeys.includes(stage.key)) {
            return stage;
          }

          return {
            ...stage,
            state: nextState,
            latencyMs: typeof frame.data.duration_ms === "number" ? frame.data.duration_ms : stage.latencyMs,
            error: frame.data.error_message ?? stage.error,
          };
        });

        if (frame.data.stage_name === "slm_render") {
          const cacheBadge = frame.data.status === "skipped" ? "cache hit" : "rendered";
          for (const stage of nextStages) {
            if (stage.key === "slm_render") {
              stage.badge = cacheBadge;
            }
            if (stage.key === "interpretation_intent_cache") {
              stage.badge = frame.data.status === "skipped" ? "hit" : "miss";
            }
          }
        }

        return {
          ...state,
          stages: nextStages,
        };
      }

      if (frame.type === "pipeline_complete") {
        if (!state.currentPipelineId || frame.data.pipeline_id !== state.currentPipelineId) {
          return state;
        }

        return {
          ...state,
          isActive: false,
          totalLatencyMs: frame.data.total_duration_ms,
        };
      }

      if (frame.type === "error") {
        return {
          ...state,
          isActive: false,
        };
      }

      return state;
    });
  },
}));
