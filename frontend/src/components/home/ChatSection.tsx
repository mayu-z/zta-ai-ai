"use client";

import { AnimatePresence, motion } from "framer-motion";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

type ChatSuggestion = {
  id: string;
  text: string;
};

type ChatMessage = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  createdAt: string;
  source?: string;
  latencyMs?: number;
  isError?: boolean;
};

type ChatSectionProps = {
  suggestions: ChatSuggestion[];
  messages: ChatMessage[];
  query: string;
  onQueryChange: (value: string) => void;
  isStreaming: boolean;
  onSubmitChat: (presetQuery?: string) => void;
};

function toDisplayTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "--";
  }
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export function ChatSection({
  suggestions,
  messages,
  query,
  onQueryChange,
  isStreaming,
  onSubmitChat,
}: ChatSectionProps) {
  return (
    <>
      <aside className="flex min-h-[420px] flex-col gap-3">
        <section className="glass-panel rounded-2xl p-4">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-primary-hover">
            Suggestion Deck
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {suggestions.map((suggestion) => (
              <button
                key={suggestion.id}
                type="button"
                className="rounded-xl border border-primary bg-primary-tint px-2.5 py-1.5 text-left text-xs text-primary-hover transition hover:bg-primary-tint"
                onClick={() => {
                  onQueryChange(suggestion.text);
                  onSubmitChat(suggestion.text);
                }}
                disabled={isStreaming}
              >
                {suggestion.text}
              </button>
            ))}
          </div>
        </section>

        <section className="glass-panel flex min-h-[320px] flex-1 flex-col rounded-2xl p-4">
          <div className="flex items-center justify-between">
            <p className="font-mono text-xs uppercase tracking-[0.2em] text-primary-hover">
              Session Log
            </p>
            <span className="rounded-full border border-border bg-bg px-2 py-0.5 text-[11px] text-text-muted">
              {messages.length} items
            </span>
          </div>
          <div className="mt-3 flex-1 overflow-y-auto pr-1">
            <div className="flex flex-col gap-2">
              {messages.slice(-12).map((entry) => (
                <div
                  key={entry.id}
                  className="rounded-xl border border-border bg-bg px-3 py-2"
                >
                  <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-text-muted">
                    {entry.role} · {toDisplayTime(entry.createdAt)}
                  </p>
                  <p className="mt-1 line-clamp-2 text-sm text-text">
                    {entry.content || "..."}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </section>
      </aside>

      <section className="glass-panel flex min-h-[640px] flex-col rounded-2xl p-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="font-mono text-xs uppercase tracking-[0.2em] text-primary-hover">
              Conversational Terminal
            </p>
            <p className="mt-1 text-sm text-text-muted">
              WebSocket stream powered by /chat/stream with markdown rendering.
            </p>
          </div>
          <div className="rounded-full border border-border bg-bg px-2 py-0.5 text-[11px] text-text-muted">
            {isStreaming ? "streaming" : "idle"}
          </div>
        </div>

        <div className="mt-4 flex-1 overflow-y-auto rounded-2xl border border-border bg-bg px-3 py-3">
          <div className="flex flex-col gap-3">
            <AnimatePresence initial={false}>
              {messages.map((entry) => (
                <motion.div
                  key={entry.id}
                  className={`max-w-[88%] rounded-2xl border px-3 py-2 ${
                    entry.role === "user"
                      ? "ml-auto border-primary bg-primary-tint"
                      : entry.isError
                        ? "border-primary bg-primary-tint"
                        : "border-border bg-bg"
                  }`}
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -6 }}
                  transition={{ duration: 0.18 }}
                >
                  <div className="prose  max-w-none text-sm prose-code:text-primary-hover prose-pre:bg-bg">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {entry.content || "..."}
                    </ReactMarkdown>
                  </div>

                  <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-text-muted">
                    <span>{entry.role}</span>
                    <span>•</span>
                    <span>{toDisplayTime(entry.createdAt)}</span>
                    {entry.source ? (
                      <>
                        <span>•</span>
                        <span>source: {entry.source}</span>
                      </>
                    ) : null}
                    {typeof entry.latencyMs === "number" ? (
                      <>
                        <span>•</span>
                        <span>{entry.latencyMs}ms</span>
                      </>
                    ) : null}
                  </div>
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        </div>

        <div className="mt-3 flex flex-col gap-2 sm:flex-row">
          <input
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
            className="flex-1 rounded-xl border border-border bg-bg px-3 py-2 text-sm text-text outline-none transition focus:border-primary"
            placeholder="Ask a campus question..."
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                onSubmitChat();
              }
            }}
            disabled={isStreaming}
          />
          <button
            type="button"
            className="rounded-xl border border-primary bg-primary-tint px-4 py-2 text-sm font-semibold text-primary-hover transition hover:bg-primary-tint disabled:cursor-not-allowed disabled:opacity-60"
            onClick={() => onSubmitChat()}
            disabled={isStreaming || !query.trim()}
          >
            {isStreaming ? "Streaming..." : "Send"}
          </button>
        </div>
      </section>
    </>
  );
}
