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
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-cyan-200">
            Suggestion Deck
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {suggestions.map((suggestion) => (
              <button
                key={suggestion.id}
                type="button"
                className="rounded-xl border border-cyan-300/45 bg-cyan-300/10 px-2.5 py-1.5 text-left text-xs text-cyan-50 transition hover:bg-cyan-300/20"
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
            <p className="font-mono text-xs uppercase tracking-[0.2em] text-cyan-200">
              Session Log
            </p>
            <span className="rounded-full border border-slate-600 bg-slate-900/70 px-2 py-0.5 text-[11px] text-slate-300">
              {messages.length} items
            </span>
          </div>
          <div className="mt-3 flex-1 overflow-y-auto pr-1">
            <div className="flex flex-col gap-2">
              {messages.slice(-12).map((entry) => (
                <div
                  key={entry.id}
                  className="rounded-xl border border-slate-600 bg-slate-900/60 px-3 py-2"
                >
                  <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-slate-400">
                    {entry.role} · {toDisplayTime(entry.createdAt)}
                  </p>
                  <p className="mt-1 line-clamp-2 text-sm text-slate-200">
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
            <p className="font-mono text-xs uppercase tracking-[0.2em] text-cyan-200">
              Conversational Terminal
            </p>
            <p className="mt-1 text-sm text-slate-300">
              WebSocket stream powered by /chat/stream with markdown rendering.
            </p>
          </div>
          <div className="rounded-full border border-slate-600 bg-slate-900/70 px-2 py-0.5 text-[11px] text-slate-300">
            {isStreaming ? "streaming" : "idle"}
          </div>
        </div>

        <div className="mt-4 flex-1 overflow-y-auto rounded-2xl border border-slate-600 bg-slate-950/75 px-3 py-3">
          <div className="flex flex-col gap-3">
            <AnimatePresence initial={false}>
              {messages.map((entry) => (
                <motion.div
                  key={entry.id}
                  className={`max-w-[88%] rounded-2xl border px-3 py-2 ${
                    entry.role === "user"
                      ? "ml-auto border-cyan-300/60 bg-cyan-300/10"
                      : entry.isError
                        ? "border-rose-300/70 bg-rose-300/15"
                        : "border-slate-600 bg-slate-900/70"
                  }`}
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -6 }}
                  transition={{ duration: 0.18 }}
                >
                  <div className="prose prose-invert max-w-none text-sm prose-code:text-cyan-200 prose-pre:bg-slate-900/90">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {entry.content || "..."}
                    </ReactMarkdown>
                  </div>

                  <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-slate-400">
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
            className="flex-1 rounded-xl border border-slate-600 bg-slate-900/80 px-3 py-2 text-sm text-slate-100 outline-none transition focus:border-cyan-300"
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
            className="rounded-xl border border-cyan-300/70 bg-cyan-300/10 px-4 py-2 text-sm font-semibold text-cyan-100 transition hover:bg-cyan-300/20 disabled:cursor-not-allowed disabled:opacity-60"
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
