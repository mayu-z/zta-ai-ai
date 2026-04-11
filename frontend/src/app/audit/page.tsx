"use client";

import { ChevronLeft, ChevronRight, ShieldAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { AuditTable } from "@/components/audit/AuditTable";
import { Sidebar } from "@/components/layout/Sidebar";
import { TopBar } from "@/components/layout/TopBar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { getAuditLog } from "@/lib/api";
import { useAuthStore } from "@/stores/authStore";
import { useToastStore } from "@/stores/toastStore";
import { useWsStore } from "@/stores/wsStore";
import type { AuditLogItem } from "@/types";

export default function AuditPage() {
  const router = useRouter();
  const token = useAuthStore((state) => state.token);
  const user = useAuthStore((state) => state.user);
  const hydrated = useAuthStore((state) => state.hydrated);
  const connected = useWsStore((state) => state.connected);
  const addError = useToastStore((state) => state.addError);

  const [items, setItems] = useState<AuditLogItem[] | null>(null);
  const [page, setPage] = useState(1);
  const [blockedOnly, setBlockedOnly] = useState(false);

  useEffect(() => {
    if (!hydrated) {
      return;
    }
    if (!token) {
      router.replace("/login");
      return;
    }
    if (user?.persona !== "it_head") {
      return;
    }

    getAuditLog(token, page, 25, blockedOnly)
      .then((response) => {
        setItems(response.items);
      })
      .catch((error) => {
        const message =
          error instanceof Error && error.message.trim()
            ? error.message
            : "Failed to load audit logs.";
        addError(message);
        setItems([]);
      });
  }, [addError, blockedOnly, hydrated, page, router, token, user?.persona]);

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

  if (user?.persona !== "it_head") {
    return (
      <main className="flex min-h-screen gap-4 p-4">
        <Sidebar />
        <section className="flex min-w-0 flex-1 flex-col gap-3">
          <TopBar title="Audit Log" connected={connected} />
          <div className="glass-card flex flex-1 items-center justify-center rounded-[14px] p-6">
            <div className="text-center">
              <ShieldAlert className="mx-auto h-8 w-8 text-primary-hover" />
              <p className="mt-2 text-sm text-text-primary">Audit log requires IT Head persona.</p>
              <p className="text-xs text-text-muted">Sign in as an IT Head account to access this page.</p>
            </div>
          </div>
        </section>
      </main>
    );
  }

  return (
    <main className="flex min-h-screen gap-4 p-4">
      <Sidebar />

      <section className="flex min-w-0 flex-1 flex-col gap-3">
        <TopBar title="Audit Log" connected={connected} />

        <div className="glass-card flex items-center justify-between rounded-[14px] px-4 py-3">
          <div>
            <p className="text-sm font-medium text-text-primary">Recent access decisions and policy outcomes</p>
            <p className="text-xs text-text-muted">Live data from /admin/audit-log</p>
          </div>
          <button
            type="button"
            onClick={() => {
              setItems(null);
              setPage(1);
              setBlockedOnly((prev) => !prev);
            }}
            className="rounded-full border border-border bg-primary-tint px-3 py-1.5 text-xs text-text-muted hover:border-primary hover:text-primary-hover"
          >
            {blockedOnly ? "Showing Blocked" : "Showing All"}
          </button>
        </div>

        <div className="glass-card flex-1 rounded-[14px] p-3">
          {items === null ? (
            <div className="space-y-2">
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
            </div>
          ) : items.length === 0 ? (
            <div className="flex h-64 items-center justify-center text-center">
              <div>
                <p className="text-sm text-text-primary">No audit rows for the current filter.</p>
                <p className="text-xs text-text-muted">Try toggling blocked-only or go to another page and trigger requests.</p>
              </div>
            </div>
          ) : (
            <AuditTable items={items} />
          )}
        </div>

        <div className="flex items-center justify-end gap-2">
          <Badge variant="default" className="mono-number px-3 py-1">Page {page}</Badge>
          <Button
            variant="outline"
            size="sm"
            disabled={page <= 1}
            onClick={() => {
              setItems(null);
              setPage((prev) => Math.max(prev - 1, 1));
            }}
            className="border-border bg-primary-tint"
          >
            <ChevronLeft className="mr-1 h-4 w-4" />
            Prev
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setItems(null);
              setPage((prev) => prev + 1);
            }}
            className="border-border bg-primary-tint"
          >
            Next
            <ChevronRight className="ml-1 h-4 w-4" />
          </Button>
        </div>
      </section>
    </main>
  );
}
