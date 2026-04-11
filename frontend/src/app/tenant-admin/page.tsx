"use client";

import { Database, GitBranch, ListChecks, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { InputBar } from "@/components/chat/InputBar";
import { MessageList } from "@/components/chat/MessageList";
import { SuggestionChips } from "@/components/chat/SuggestionChips";
import { Sidebar } from "@/components/layout/Sidebar";
import { TopBar } from "@/components/layout/TopBar";
import { PipelinePanel } from "@/components/layout/PipelinePanel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  getActionTemplates,
  getDataSources,
  getGraphOverview,
  rebuildGraph,
} from "@/lib/api";
import { useAuthStore } from "@/stores/authStore";
import { useChatStore } from "@/stores/chatStore";
import { usePipelineStore } from "@/stores/pipelineStore";
import { useToastStore } from "@/stores/toastStore";
import { useWsStore } from "@/stores/wsStore";
import type { ActionTemplateItem, DataSourceItem, GraphOverviewResponse } from "@/types";

function parseError(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }
  return fallback;
}

export default function TenantAdminPage() {
  const router = useRouter();

  const token = useAuthStore((state) => state.token);
  const user = useAuthStore((state) => state.user);
  const scope = useAuthStore((state) => state.scope);
  const hydrated = useAuthStore((state) => state.hydrated);

  const messages = useChatStore((state) => state.messages);
  const suggestions = useChatStore((state) => state.suggestions);
  const isStreaming = useChatStore((state) => state.isStreaming);
  const bootstrap = useChatStore((state) => state.bootstrap);
  const sendMessage = useChatStore((state) => state.sendMessage);
  const handleTokenFrame = useChatStore((state) => state.handleTokenFrame);
  const clearHistory = useChatStore((state) => state.clearHistory);

  const handleMonitorFrame = usePipelineStore((state) => state.handleMonitorFrame);

  const connected = useWsStore((state) => state.connected);
  const monitorConnected = useWsStore((state) => state.monitorConnected);
  const connect = useWsStore((state) => state.connect);
  const disconnect = useWsStore((state) => state.disconnect);
  const connectMonitor = useWsStore((state) => state.connectMonitor);
  const disconnectMonitor = useWsStore((state) => state.disconnectMonitor);

  const addError = useToastStore((state) => state.addError);

  const [bootSessionId, setBootSessionId] = useState<string | null>(null);
  const [sources, setSources] = useState<DataSourceItem[]>([]);
  const [graphOverview, setGraphOverview] = useState<GraphOverviewResponse | null>(null);
  const [templates, setTemplates] = useState<ActionTemplateItem[]>([]);
  const [loadingAdminData, setLoadingAdminData] = useState(false);
  const [rebuildingGraph, setRebuildingGraph] = useState(false);

  const isTenantAdmin = user?.persona === "it_head";

  useEffect(() => {
    if (!hydrated) {
      return;
    }
    if (!token) {
      router.replace("/login");
      return;
    }
    if (user?.persona === "system_admin") {
      router.replace("/system-admin");
      return;
    }
    if (!isTenantAdmin) {
      router.replace("/chat");
    }
  }, [hydrated, isTenantAdmin, router, token, user?.persona]);

  useEffect(() => {
    const sessionId = scope?.session_id;
    if (!token || !sessionId || !isTenantAdmin) {
      return;
    }

    let mounted = true;

    bootstrap(token, sessionId)
      .catch((error) => {
        addError(parseError(error, "Unable to load chat history."));
      })
      .finally(() => {
        if (mounted) {
          setBootSessionId(sessionId);
        }
      });

    connect(
      token,
      (frame) => handleTokenFrame(frame),
      (message) => addError(message)
    );

    connectMonitor(
      token,
      (frame) => handleMonitorFrame(frame),
      (message) => addError(message)
    );

    return () => {
      mounted = false;
      disconnect();
      disconnectMonitor();
    };
  }, [
    addError,
    bootstrap,
    connect,
    connectMonitor,
    disconnect,
    disconnectMonitor,
    handleMonitorFrame,
    handleTokenFrame,
    isTenantAdmin,
    scope?.session_id,
    token,
  ]);

  const loadDashboardData = useCallback(async () => {
    if (!token || !isTenantAdmin) {
      return;
    }

    setLoadingAdminData(true);
    const [sourceResult, graphResult, templatesResult] = await Promise.allSettled([
      getDataSources(token),
      getGraphOverview(token, 30),
      getActionTemplates(token),
    ]);

    if (sourceResult.status === "fulfilled") {
      setSources(sourceResult.value);
    } else {
      addError(parseError(sourceResult.reason, "Failed to load data sources."));
    }

    if (graphResult.status === "fulfilled") {
      setGraphOverview(graphResult.value);
    } else {
      addError(parseError(graphResult.reason, "Failed to load graph overview."));
    }

    if (templatesResult.status === "fulfilled") {
      setTemplates(templatesResult.value.templates);
    } else {
      addError(parseError(templatesResult.reason, "Failed to load action templates."));
    }

    setLoadingAdminData(false);
  }, [addError, isTenantAdmin, token]);

  const runGraphRebuild = useCallback(async () => {
    if (!token || !isTenantAdmin) {
      return;
    }

    setRebuildingGraph(true);
    try {
      await rebuildGraph(token);
      await loadDashboardData();
    } catch (error) {
      addError(parseError(error, "Failed to rebuild control graph."));
    } finally {
      setRebuildingGraph(false);
    }
  }, [addError, isTenantAdmin, loadDashboardData, token]);

  useEffect(() => {
    if (!token || !isTenantAdmin) {
      return;
    }
    void loadDashboardData();
  }, [isTenantAdmin, loadDashboardData, token]);

  const booting = Boolean(token && scope?.session_id && bootSessionId !== scope.session_id);

  const enabledTemplates = useMemo(
    () => templates.filter((template) => template.enabled !== false),
    [templates]
  );

  if (!hydrated || !token || !isTenantAdmin) {
    return (
      <main className="flex min-h-screen items-center justify-center px-6">
        <div className="w-full max-w-3xl space-y-3">
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-96 w-full" />
        </div>
      </main>
    );
  }

  return (
    <main className="flex min-h-screen gap-4 p-4">
      <Sidebar />

      <section className="flex min-w-0 flex-1 flex-col gap-3">
        <TopBar title="Tenant Admin Dashboard" connected={connected && monitorConnected} />

        <div className="grid gap-3 md:grid-cols-4">
          <article className="glass-card rounded-[14px] p-3">
            <p className="text-xs uppercase tracking-[0.16em] text-text-muted">Data Sources</p>
            <p className="mt-2 text-xl font-semibold text-text-primary">{sources.length}</p>
            <p className="mt-1 text-xs text-text-muted">Connected + external connectors</p>
          </article>

          <article className="glass-card rounded-[14px] p-3">
            <p className="text-xs uppercase tracking-[0.16em] text-text-muted">Graph Nodes</p>
            <p className="mt-2 text-xl font-semibold text-text-primary">
              {graphOverview?.summary.total_nodes ?? 0}
            </p>
            <p className="mt-1 text-xs text-text-muted">Control-plane metadata entities</p>
          </article>

          <article className="glass-card rounded-[14px] p-3">
            <p className="text-xs uppercase tracking-[0.16em] text-text-muted">Graph Edges</p>
            <p className="mt-2 text-xl font-semibold text-text-primary">
              {graphOverview?.summary.total_edges ?? 0}
            </p>
            <p className="mt-1 text-xs text-text-muted">Policy + lineage relationships</p>
          </article>

          <article className="glass-card rounded-[14px] p-3">
            <p className="text-xs uppercase tracking-[0.16em] text-text-muted">Action Templates</p>
            <p className="mt-2 text-xl font-semibold text-text-primary">{enabledTemplates.length}</p>
            <p className="mt-1 text-xs text-text-muted">Approved operational automations</p>
          </article>
        </div>

        <div className="grid gap-3 xl:grid-cols-3">
          <article className="glass-card rounded-[14px] p-3">
            <div className="mb-2 flex items-center justify-between">
              <p className="text-sm font-medium text-text-primary">Connector Health</p>
              <Database className="h-4 w-4 text-text-muted" />
            </div>
            <div className="space-y-2 text-xs">
              {sources.slice(0, 8).map((source) => (
                <div key={source.id} className="rounded-lg border border-border bg-bg px-2 py-2">
                  <p className="font-medium text-text-primary">{source.name}</p>
                  <p className="mt-0.5 text-text-muted">
                    {source.source_type} • {source.status}
                  </p>
                </div>
              ))}
              {sources.length === 0 ? (
                <p className="text-text-muted">No connectors configured for this tenant.</p>
              ) : null}
            </div>
          </article>

          <article className="glass-card rounded-[14px] p-3">
            <div className="mb-2 flex items-center justify-between">
              <p className="text-sm font-medium text-text-primary">Knowledge Graph Lineage</p>
              <GitBranch className="h-4 w-4 text-text-muted" />
            </div>
            <div className="space-y-2 text-xs">
              {(graphOverview?.data_lineage ?? []).slice(0, 8).map((item) => (
                <div key={`${item.domain}:${item.data_source_id ?? item.source_type}`} className="rounded-lg border border-border bg-bg px-2 py-2">
                  <p className="font-medium text-text-primary">{item.domain}</p>
                  <p className="mt-0.5 text-text-muted">
                    {item.source_type}
                    {item.data_source_name ? ` • ${item.data_source_name}` : ""}
                  </p>
                </div>
              ))}
              {(graphOverview?.data_lineage ?? []).length === 0 ? (
                <p className="text-text-muted">No lineage bindings found yet.</p>
              ) : null}
            </div>
          </article>

          <article className="glass-card rounded-[14px] p-3">
            <div className="mb-2 flex items-center justify-between">
              <p className="text-sm font-medium text-text-primary">Template Directory</p>
              <ListChecks className="h-4 w-4 text-text-muted" />
            </div>
            <div className="space-y-2 text-xs">
              {enabledTemplates.slice(0, 8).map((template) => (
                <div key={template.action_id} className="rounded-lg border border-border bg-bg px-2 py-2">
                  <p className="font-medium text-text-primary">{template.action_id}</p>
                  <p className="mt-0.5 text-text-muted">
                    {template.risk_classification} risk • {template.trigger}
                  </p>
                </div>
              ))}
              {enabledTemplates.length === 0 ? (
                <p className="text-text-muted">No enabled templates available.</p>
              ) : null}
            </div>
          </article>
        </div>

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs text-text-muted">
            <Badge variant="default">Recent proofs: {graphOverview?.recent_policy_proofs.length ?? 0}</Badge>
            <Badge variant="default">Role map entries: {graphOverview?.role_map.length ?? 0}</Badge>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              className="border-border bg-primary-tint"
              onClick={() => {
                void runGraphRebuild();
              }}
              disabled={rebuildingGraph || loadingAdminData}
            >
              <RefreshCw className={`mr-2 h-4 w-4 ${rebuildingGraph ? "animate-spin" : ""}`} />
              {rebuildingGraph ? "Rebuilding Graph" : "Rebuild Graph"}
            </Button>
            <Button
              variant="outline"
              className="border-border bg-primary-tint"
              onClick={() => {
                void loadDashboardData();
              }}
              disabled={loadingAdminData || rebuildingGraph}
            >
              <RefreshCw className={`mr-2 h-4 w-4 ${loadingAdminData ? "animate-spin" : ""}`} />
              {loadingAdminData ? "Refreshing" : "Refresh Dashboard"}
            </Button>
          </div>
        </div>

        <div className="grid gap-3 xl:grid-cols-2">
          <article className="glass-card rounded-[14px] p-3">
            <p className="text-sm font-medium text-text-primary">Role Map</p>
            <div className="mt-2 max-h-56 space-y-2 overflow-y-auto text-xs">
              {(graphOverview?.role_map ?? []).slice(0, 20).map((role) => (
                <div key={role.role_key} className="rounded-lg border border-border bg-bg px-2 py-2">
                  <p className="font-medium text-text-primary">{role.display_name}</p>
                  <p className="mt-0.5 text-text-muted">{role.role_key}</p>
                  <p className="mt-1 text-text-muted">
                    Domains: {role.allowed_domains.join(", ") || "none"}
                  </p>
                  <p className="mt-0.5 text-text-muted">
                    Aggregate: {role.aggregate_only ? "yes" : "no"} • Chat: {role.chat_enabled ? "yes" : "no"}
                  </p>
                </div>
              ))}
              {(graphOverview?.role_map ?? []).length === 0 ? (
                <p className="text-text-muted">No role map records available.</p>
              ) : null}
            </div>
          </article>

          <article className="glass-card rounded-[14px] p-3">
            <p className="text-sm font-medium text-text-primary">Recent Policy Proofs</p>
            <div className="mt-2 max-h-56 space-y-2 overflow-y-auto text-xs">
              {(graphOverview?.recent_policy_proofs ?? []).slice(0, 20).map((proof) => (
                <div key={proof.proof_id} className="rounded-lg border border-border bg-bg px-2 py-2">
                  <p className="font-medium text-text-primary">{proof.domain} • {proof.source_type}</p>
                  <p className="mt-0.5 text-text-muted">{proof.proof_id.slice(0, 16)}...</p>
                  <p className="mt-1 text-text-muted">
                    Masked fields: {proof.masked_fields.length} • {new Date(proof.created_at).toLocaleString()}
                  </p>
                </div>
              ))}
              {(graphOverview?.recent_policy_proofs ?? []).length === 0 ? (
                <p className="text-text-muted">No policy proofs recorded yet.</p>
              ) : null}
            </div>
          </article>
        </div>

        <div className="grid min-h-0 flex-1 gap-3 xl:grid-cols-[minmax(0,1fr)_320px]">
          <section className="flex min-h-0 flex-col gap-3">
            <SuggestionChips
              suggestions={suggestions}
              onPick={(text) => {
                sendMessage(text);
              }}
            />

            <div className="min-h-0 flex-1">
              {booting ? (
                <div className="space-y-3">
                  <Skeleton className="h-14 w-4/5" />
                  <Skeleton className="h-20 w-2/3" />
                  <Skeleton className="h-14 w-3/5" />
                </div>
              ) : (
                <MessageList messages={messages} isStreaming={isStreaming} />
              )}
            </div>

            <InputBar
              disabled={isStreaming}
              onSend={(value) => sendMessage(value)}
              onClear={() => clearHistory()}
            />
          </section>

          <PipelinePanel />
        </div>
      </section>
    </main>
  );
}
