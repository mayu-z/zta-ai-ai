"use client";

import { MessageSquareMore } from "lucide-react";
import { useEffect, useRef } from "react";

import { MessageBubble } from "@/components/chat/MessageBubble";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { ChatMessage } from "@/types";

export function MessageList({
  messages,
  isStreaming,
}: {
  messages: ChatMessage[];
  isStreaming: boolean;
}) {
  const anchorRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    anchorRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, isStreaming]);

  if (messages.length === 0) {
    return (
      <div className="glass-card flex h-full items-center justify-center rounded-[14px]">
        <div className="text-center">
          <MessageSquareMore className="mx-auto h-8 w-8 text-text-faint" />
          <p className="mt-2 text-sm text-text-muted">No messages yet</p>
          <p className="text-xs text-text-faint">Ask a query to begin the pipeline.</p>
        </div>
      </div>
    );
  }

  return (
    <ScrollArea className="glass-card h-full rounded-[14px]">
      <div className="space-y-3 p-3">
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}

        {isStreaming ? (
          <div className="flex justify-start">
            <div className="glass-card rounded-2xl px-3 py-2">
              <div className="flex items-center gap-1.5">
                <span className="h-2 w-2 animate-bounce rounded-full bg-primary [animation-delay:-0.25s]" />
                <span className="h-2 w-2 animate-bounce rounded-full bg-primary [animation-delay:-0.12s]" />
                <span className="h-2 w-2 animate-bounce rounded-full bg-primary" />
              </div>
            </div>
          </div>
        ) : null}
        <div ref={anchorRef} />
      </div>
    </ScrollArea>
  );
}
