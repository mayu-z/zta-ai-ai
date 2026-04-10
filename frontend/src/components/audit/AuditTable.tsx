"use client";

import { ChevronDown, ChevronUp } from "lucide-react";
import { Fragment } from "react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { getLatencyFlag } from "@/lib/api";
import type { AuditLogItem } from "@/types";

function statusVariant(blocked: boolean): "success" | "danger" {
  return blocked ? "danger" : "success";
}

function latencyVariant(flag: "suspicious" | "normal" | "high"): "warning" | "success" | "accent" {
  if (flag === "suspicious") {
    return "warning";
  }
  if (flag === "high") {
    return "accent";
  }
  return "success";
}

function formatTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "--";
  }
  return date.toLocaleString();
}

export function AuditTable({ items }: { items: AuditLogItem[] }) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  return (
    <div className="thin-scroll overflow-x-auto">
      <table className="w-full min-w-[960px] border-collapse text-left text-sm">
        <thead>
          <tr className="bg-surface text-xs uppercase tracking-wide text-text-muted">
            <th className="px-3 py-2 font-medium">Time</th>
            <th className="px-3 py-2 font-medium">User</th>
            <th className="px-3 py-2 font-medium">Queryyy</th>
            <th className="px-3 py-2 font-medium">Domains</th>
            <th className="px-3 py-2 font-medium">Status</th>
            <th className="px-3 py-2 font-medium">Latency</th>
            <th className="px-3 py-2 font-medium">Latency Flag</th>
            <th className="px-3 py-2 text-right font-medium">Expand</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => {
            const latencyFlag = getLatencyFlag(item.latency_ms);
            const expanded = expandedId === item.id;

            return (
                <Fragment key={item.id}>
                  <tr className="border-b border-border text-text-primary transition-colors hover:bg-primary-tint">
                  <td className="px-3 py-2 text-xs text-text-muted">{formatTime(item.created_at)}</td>
                  <td className="px-3 py-2 text-xs">{item.user_id}</td>
                  <td className="max-w-[300px] truncate px-3 py-2">{item.query_text}</td>
                  <td className="px-3 py-2 text-xs text-text-muted">
                    {item.domains_accessed?.length ? item.domains_accessed.join(", ") : "--"}
                  </td>
                  <td className="px-3 py-2">
                    <Badge variant={statusVariant(item.was_blocked)}>
                      {item.was_blocked ? "blocked" : "allowed"}
                    </Badge>
                  </td>
                  <td className="px-3 py-2">
                    <span className="mono-number">{item.latency_ms}ms</span>
                  </td>
                  <td className="px-3 py-2">
                    <Badge variant={latencyVariant(latencyFlag)}>{latencyFlag}</Badge>
                  </td>
                  <td className="px-3 py-2 text-right">
                    <Button
                      type="button"
                      size="icon"
                      variant="ghost"
                      className="h-8 w-8 border border-border"
                      onClick={() => setExpandedId(expanded ? null : item.id)}
                      aria-label="Toggle row details"
                    >
                      {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                    </Button>
                  </td>
                </tr>
                {expanded ? (
                  <tr className="text-xs text-text-muted">
                    <td colSpan={8} className="px-3 pb-3">
                      <div className="rounded-lg border border-border bg-bg p-3">
                        <p className="mb-1 text-text-primary">
                          <span className="font-semibold">Full query:</span> {item.query_text}
                        </p>
                        <p>
                          <span className="font-semibold text-text-primary">Block reason:</span>{" "}
                          {item.block_reason || "--"}
                        </p>
                      </div>
                    </td>
                  </tr>
                ) : null}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
