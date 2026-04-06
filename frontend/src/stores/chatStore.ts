import { create } from "zustand";

import { getChatHistory, getChatSuggestions } from "@/lib/api";
import { usePipelineStore } from "@/stores/pipelineStore";
import { useToastStore } from "@/stores/toastStore";
import { useWsStore } from "@/stores/wsStore";
import type { ChatMessage, ChatSuggestion, TokenFrame } from "@/types";

interface ChatState {
  sessionId: string;
  messages: ChatMessage[];
  suggestions: ChatSuggestion[];
  isStreaming: boolean;
  activeAssistantId: string | null;
  bootstrap: (token: string, sessionId: string) => Promise<void>;
  setSessionId: (sessionId: string) => void;
  sendMessage: (query: string) => void;
  handleTokenFrame: (frame: TokenFrame) => void;
  clearHistory: () => void;
}

function makeId(prefix: string): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `${prefix}-${crypto.randomUUID()}`;
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
}

function mapHistoryToMessages(history: { role: "user" | "assistant"; content: string; created_at: string }[]): ChatMessage[] {
  return history.map((item) => ({
    id: makeId(item.role),
    role: item.role,
    content: item.content,
    createdAt: item.created_at,
  }));
}

export const useChatStore = create<ChatState>((set, get) => ({
  sessionId: "",
  messages: [],
  suggestions: [],
  isStreaming: false,
  activeAssistantId: null,
  bootstrap: async (token, sessionId) => {
    const [suggestions, history] = await Promise.all([
      getChatSuggestions(token),
      getChatHistory(token),
    ]);

    set({
      sessionId,
      suggestions,
      messages: mapHistoryToMessages(history),
    });
  },
  setSessionId: (sessionId) => {
    set({ sessionId });
  },
  sendMessage: (query) => {
    const trimmed = query.trim();
    if (!trimmed) {
      return;
    }

    const ws = useWsStore.getState();
    const notifyError = useToastStore.getState().addError;

    if (!ws.connected) {
      notifyError("Chat connection is offline. Reconnect and try again.");
      return;
    }

    const userMessage: ChatMessage = {
      id: makeId("user"),
      role: "user",
      content: trimmed,
      createdAt: new Date().toISOString(),
    };

    const assistantMessage: ChatMessage = {
      id: makeId("assistant"),
      role: "assistant",
      content: "",
      createdAt: new Date().toISOString(),
    };

    set((state) => ({
      messages: [...state.messages, userMessage, assistantMessage],
      isStreaming: true,
      activeAssistantId: assistantMessage.id,
    }));

    usePipelineStore.getState().prepareForQuery(trimmed);

    const sent = ws.send({ query: trimmed });
    if (!sent) {
      notifyError("Failed to send message. Socket is not ready.");
      set((state) => ({
        isStreaming: false,
        activeAssistantId: null,
        messages: state.messages.map((message) =>
          message.id === assistantMessage.id
            ? {
                ...message,
                role: "blocked",
                content: "Message could not be sent.",
                blockReason: "SOCKET_NOT_READY",
              }
            : message
        ),
      }));
    }
  },
  handleTokenFrame: (frame) => {
    const activeAssistantId = get().activeAssistantId;

    if (frame.type === "token") {
      if (!activeAssistantId) {
        return;
      }

      set((state) => ({
        messages: state.messages.map((message) =>
          message.id === activeAssistantId
            ? {
                ...message,
                content: `${message.content}${frame.content ?? ""}`,
              }
            : message
        ),
      }));
      return;
    }

    if (frame.type === "done") {
      if (!activeAssistantId) {
        return;
      }

      set((state) => ({
        isStreaming: false,
        activeAssistantId: null,
        messages: state.messages.map((message) =>
          message.id === activeAssistantId
            ? {
                ...message,
                source: frame.source,
                latencyMs: frame.latency_ms,
              }
            : message
        ),
      }));
      return;
    }

    const reason = frame.message || "Request blocked by policy";

    if (!activeAssistantId) {
      set((state) => ({
        isStreaming: false,
        activeAssistantId: null,
        messages: [
          ...state.messages,
          {
            id: makeId("blocked"),
            role: "blocked",
            content: reason,
            blockReason: reason,
            createdAt: new Date().toISOString(),
          },
        ],
      }));
      return;
    }

    set((state) => ({
      isStreaming: false,
      activeAssistantId: null,
      messages: state.messages.map((message) =>
        message.id === activeAssistantId
          ? {
              ...message,
              role: "blocked",
              content: reason,
              blockReason: reason,
            }
          : message
      ),
    }));
  },
  clearHistory: () => {
    set({ messages: [], isStreaming: false, activeAssistantId: null });
  },
}));
