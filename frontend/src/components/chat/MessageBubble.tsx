import { ShieldAlert } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { ChatMessage } from "@/types";

function highlightNumbers(text: string) {
  const segments = text.split(/(\b\d[\d,.]*(?:\.\d+)?\b)/g);
  return segments.map((segment, index) => {
    const isNumber = /^\b\d[\d,.]*(?:\.\d+)?\b$/.test(segment);
    if (!isNumber) {
      return <span key={`${segment}-${index}`}>{segment}</span>;
    }
    return (
      <span key={`${segment}-${index}`} className="mono-number font-medium">
        {segment}
      </span>
    );
  });
}

function toTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "--";
  }
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  const isBlocked = message.role === "blocked";

  return (
    <div className={cn("flex w-full", isUser ? "justify-end" : "justify-start")}>
      <article
        className={cn(
          "max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed",
          isUser && "bg-indigo-600 text-white",
          !isUser && !isBlocked && "glass-card border border-white/10 bg-surface/65 text-text-primary",
          isBlocked && "border border-red-400/30 bg-red-500/12 text-red-100 backdrop-blur-sm"
        )}
      >
        {isBlocked ? (
          <div className="mb-2 flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-red-200">
            <ShieldAlert className="h-4 w-4" />
            Blocked by Policy
          </div>
        ) : null}

        <p className="whitespace-pre-wrap break-words">{highlightNumbers(message.content)}</p>

        <footer className="mt-2 flex items-center justify-end gap-1.5">
          {!isUser && message.source ? (
            <Badge variant="accent" className="text-[10px] uppercase tracking-wide">
              {message.source}
            </Badge>
          ) : null}
          {!isUser && typeof message.latencyMs === "number" ? (
            <Badge variant="default" className="mono-number text-[10px]">
              {(message.latencyMs / 1000).toFixed(1)}s
            </Badge>
          ) : null}
          <span className={cn("text-[10px]", isUser ? "text-indigo-100/75" : "text-text-faint")}>{toTime(message.createdAt)}</span>
        </footer>
      </article>
    </div>
  );
}
