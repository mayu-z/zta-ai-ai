"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { InputBar } from "@/components/chat/InputBar";
import { MessageList } from "@/components/chat/MessageList";
import { SuggestionChips } from "@/components/chat/SuggestionChips";
import { PipelinePanel } from "@/components/layout/PipelinePanel";
import { Sidebar } from "@/components/layout/Sidebar";
import { TopBar } from "@/components/layout/TopBar";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuthStore } from "@/stores/authStore";
import { useChatStore } from "@/stores/chatStore";
import { usePipelineStore } from "@/stores/pipelineStore";
import { useToastStore } from "@/stores/toastStore";
import { useWsStore } from "@/stores/wsStore";

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

  const connected = useWsStore((state) => state.connected);
  const monitorConnected = useWsStore((state) => state.monitorConnected);
  const connect = useWsStore((state) => state.connect);
  const disconnect = useWsStore((state) => state.disconnect);
  const connectMonitor = useWsStore((state) => state.connectMonitor);
  const disconnectMonitor = useWsStore((state) => state.disconnectMonitor);

  const addError = useToastStore((state) => state.addError);
  const [bootSessionId, setBootSessionId] = useState<string | null>(null);

  useEffect(() => {
    if (!hydrated) {
      return;
    }
    if (!token) {
      router.replace("/login");
    }
  }, [hydrated, token, router]);

  useEffect(() => {
    const sessionId = scope?.session_id;
    if (!token || !sessionId) {
      return;
    }

    let mounted = true;

    bootstrap(token, sessionId)
      .catch((error) => {
        const message =
          error instanceof Error && error.message.trim()
            ? error.message
            : "Unable to load chat history.";
        addError(message);
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
      (frame) => handleMonitorFrame(frame, user?.id),
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
    user?.id,
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
    <main className="flex min-h-screen gap-4 p-4">
      <Sidebar />

      <section className="flex min-w-0 flex-1 flex-col gap-3">
        <TopBar title="Chat" connected={connected && monitorConnected} />

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
    </main>
  );
}
