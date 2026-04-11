"use client";

import { CheckCircle2, Sparkles, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { InputBar } from "@/components/chat/InputBar";
import { MessageList } from "@/components/chat/MessageList";
import { SuggestionChips } from "@/components/chat/SuggestionChips";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuthStore } from "@/stores/authStore";
import { useChatStore } from "@/stores/chatStore";
import { usePipelineStore } from "@/stores/pipelineStore";
import { useToastStore } from "@/stores/toastStore";
import { useWsStore } from "@/stores/wsStore";
import type { ChatSuggestion } from "@/types";

function parseError(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }
  return fallback;
}

export default function ChatPage() {
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
  const isPipelineActive = usePipelineStore((state) => state.isActive);
  const pipelineLatency = usePipelineStore((state) => state.totalLatencyMs);

  const connected = useWsStore((state) => state.connected);
  const monitorConnected = useWsStore((state) => state.monitorConnected);
  const connect = useWsStore((state) => state.connect);
  const disconnect = useWsStore((state) => state.disconnect);
  const connectMonitor = useWsStore((state) => state.connectMonitor);
  const disconnectMonitor = useWsStore((state) => state.disconnectMonitor);

  const addError = useToastStore((state) => state.addError);
  const [bootSessionId, setBootSessionId] = useState<string | null>(null);
  const [pendingTemplate, setPendingTemplate] = useState<ChatSuggestion | null>(null);

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
    if (user?.persona === "it_head") {
      router.replace("/tenant-admin");
    }
  }, [hydrated, router, token, user?.persona]);

  useEffect(() => {
    const sessionId = scope?.session_id;
    if (!token || !sessionId) {
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
    scope?.session_id,
    token,
  ]);

  const booting = Boolean(token && scope?.session_id && bootSessionId !== scope.session_id);

  if (!hydrated || !token) {
    return (
      <main className="flex min-h-screen items-center justify-center px-6">
        <div className="w-full max-w-2xl space-y-3">
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-80 w-full" />
          <Skeleton className="h-20 w-full" />
        </div>
      </main>
    );
  }

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-5xl flex-col gap-3 px-4 py-4">
      <header className="glass-card rounded-[14px] p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <p className="text-xs uppercase tracking-[0.16em] text-text-muted">Assistant</p>
            <h1 className="mt-1 text-lg font-semibold text-text-primary">
              Welcome, {user?.name || "User"}
            </h1>
            <p className="mt-1 text-sm text-text-muted">
              Ask questions in natural language. Approved templates below can be inserted with confirmation.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="default">{connected ? "Chat Connected" : "Chat Offline"}</Badge>
            <Badge variant="default">
              {monitorConnected ? "Pipeline Stream On" : "Pipeline Stream Off"}
            </Badge>
            <Badge variant="default">
              {isPipelineActive
                ? "Pipeline Active"
                : `Pipeline Idle${typeof pipelineLatency === "number" ? ` • ${pipelineLatency}ms` : ""}`}
            </Badge>
          </div>
        </div>
      </header>

      <section className="glass-card rounded-[14px] p-3">
        <p className="mb-2 text-xs uppercase tracking-[0.14em] text-text-muted">Template Directory</p>
        <SuggestionChips
          suggestions={suggestions}
          onPick={(text) => {
            const selected = suggestions.find((item) => item.text === text) || null;
            setPendingTemplate(selected);
          }}
        />

        {pendingTemplate ? (
          <div className="mt-3 rounded-lg border border-border bg-bg p-3">
            <p className="text-xs uppercase tracking-[0.14em] text-text-muted">Template Confirmation</p>
            <p className="mt-2 text-sm text-text-primary">{pendingTemplate.text}</p>
            <div className="mt-3 flex gap-2">
              <Button
                type="button"
                onClick={() => {
                  sendMessage(pendingTemplate.text);
                  setPendingTemplate(null);
                }}
                className="gap-2"
              >
                <CheckCircle2 className="h-4 w-4" /> Use Template
              </Button>
              <Button
                type="button"
                variant="outline"
                className="gap-2 border-border bg-primary-tint"
                onClick={() => setPendingTemplate(null)}
              >
                <XCircle className="h-4 w-4" /> Dismiss
              </Button>
            </div>
          </div>
        ) : (
          <p className="mt-2 inline-flex items-center gap-1.5 text-xs text-text-muted">
            <Sparkles className="h-3 w-3" /> Select a template above to preview and confirm before sending.
          </p>
        )}
      </section>

      <section className="min-h-0 flex-1">
        {booting ? (
          <div className="space-y-3">
            <Skeleton className="h-14 w-4/5" />
            <Skeleton className="h-20 w-2/3" />
            <Skeleton className="h-14 w-3/5" />
          </div>
        ) : (
          <MessageList messages={messages} isStreaming={isStreaming} />
        )}
      </section>

      <InputBar
        disabled={isStreaming}
        onSend={(value) => {
          setPendingTemplate(null);
          sendMessage(value);
        }}
        onClear={() => {
          setPendingTemplate(null);
          clearHistory();
        }}
      />
    </main>
  );
}
