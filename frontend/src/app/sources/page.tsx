"use client";

import { AlertTriangle, Database, PauseCircle } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { Sidebar } from "@/components/layout/Sidebar";
import { TopBar } from "@/components/layout/TopBar";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { getDataSources } from "@/lib/api";
import { useAuthStore } from "@/stores/authStore";
import { useToastStore } from "@/stores/toastStore";
import { useWsStore } from "@/stores/wsStore";
import type { DataSourceItem } from "@/types";

function statusTone(status: DataSourceItem["status"]): "success" | "warning" | "danger" | "default" {
  if (status === "connected") {
    return "success";
  }
  if (status === "paused") {
    return "warning";
  }
  if (status === "error") {
    return "danger";
  }
  return "default";
}

function statusDot(status: DataSourceItem["status"]): string {
  if (status === "connected") {
    return "bg-emerald-400";
  }
  if (status === "paused") {
    return "bg-amber-400";
  }
  if (status === "error") {
    return "bg-red-400";
  }
  return "bg-slate-400";
}

function lastSyncText(value: string | null): string {
  if (!value) {
    return "No sync yet";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "Unknown";
  }
  return parsed.toLocaleString();
}

export default function SourcesPage() {
  const router = useRouter();
  const token = useAuthStore((state) => state.token);
  const hydrated = useAuthStore((state) => state.hydrated);
  const connected = useWsStore((state) => state.connected);
  const addError = useToastStore((state) => state.addError);

  const [sources, setSources] = useState<DataSourceItem[] | null>(null);

  useEffect(() => {
    if (!hydrated) {
      return;
    }
    if (!token) {
      router.replace("/login");
      return;
    }

    getDataSources(token)
      .then((result) => {
        setSources(result);
      })
      .catch((error) => {
        const message =
          error instanceof Error && error.message.trim()
            ? error.message
            : "Failed to load data sources.";
        addError(message);
        setSources([]);
      });
  }, [addError, hydrated, router, token]);

  const summary = useMemo(() => {
    const safeSources = sources ?? [];
    return {
      connected: safeSources.filter((source) => source.status === "connected").length,
      paused: safeSources.filter((source) => source.status === "paused").length,
      errors: safeSources.filter((source) => source.status === "error").length,
    };
  }, [sources]);

  if (!hydrated || !token) {
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
        <TopBar title="Data Sources" connected={connected} />

        <div className="glass-card flex flex-wrap items-center gap-2 rounded-xl border border-white/10 px-4 py-3">
          <Badge variant="success">Connected: {summary.connected}</Badge>
          <Badge variant="warning">Paused: {summary.paused}</Badge>
          <Badge variant="danger">Errors: {summary.errors}</Badge>
        </div>

        {sources === null ? (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
            <Skeleton className="h-36 w-full" />
            <Skeleton className="h-36 w-full" />
            <Skeleton className="h-36 w-full" />
          </div>
        ) : sources.length === 0 ? (
          <div className="glass-card flex flex-1 items-center justify-center rounded-xl border border-white/10 p-6 text-center">
            <div>
              <Database className="mx-auto h-8 w-8 text-text-faint" />
              <p className="mt-2 text-sm text-text-primary">No data sources configured</p>
              <p className="text-xs text-text-muted">Create one in backend admin endpoints to see it here.</p>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
            {sources.map((source) => (
              <article
                key={source.id}
                className="glass-card rounded-xl border border-white/10 p-4 transition-colors duration-150 hover:border-white/20"
              >
                <div className="mb-2 flex items-start justify-between gap-2">
                  <div>
                    <h3 className="text-sm font-semibold text-text-primary">{source.name}</h3>
                    <p className="text-xs text-text-muted">{source.id}</p>
                  </div>
                  <Badge variant={statusTone(source.status)}>{source.status}</Badge>
                </div>

                <div className="mb-3 flex items-center gap-2 text-xs text-text-muted">
                  <span className={`h-2.5 w-2.5 rounded-full ${statusDot(source.status)}`} />
                  <span>{source.source_type}</span>
                </div>

                <div className="rounded-lg border border-white/10 bg-black/20 p-2 text-xs text-text-muted">
                  Last sync: <span className="mono-number">{lastSyncText(source.last_sync_at)}</span>
                </div>

                {(source.status === "paused" || source.status === "error") && (
                  <div className="mt-2 flex items-center gap-1.5 text-xs text-text-faint">
                    {source.status === "paused" ? (
                      <PauseCircle className="h-3.5 w-3.5 text-amber-300" />
                    ) : (
                      <AlertTriangle className="h-3.5 w-3.5 text-red-300" />
                    )}
                    {source.status === "paused"
                      ? "Source is paused. Resume from admin controls."
                      : "Source reports errors. Verify connector settings."}
                  </div>
                )}
              </article>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
