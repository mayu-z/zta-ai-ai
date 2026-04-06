"use client";

import { Sparkles } from "lucide-react";

import { cn } from "@/lib/utils";
import type { ChatSuggestion } from "@/types";

export function SuggestionChips({
  suggestions,
  onPick,
}: {
  suggestions: ChatSuggestion[];
  onPick: (value: string) => void;
}) {
  if (suggestions.length === 0) {
    return null;
  }

  return (
    <div className="thin-scroll flex w-full gap-2 overflow-x-auto pb-1">
      {suggestions.slice(0, 4).map((suggestion) => (
        <button
          key={suggestion.id}
          type="button"
          onClick={() => onPick(suggestion.text)}
          className={cn(
            "group shrink-0 rounded-full border border-white/12 bg-white/5 px-3 py-1.5 text-xs text-text-muted transition-all duration-150",
            "hover:border-indigo-400/45 hover:bg-indigo-500/12 hover:text-indigo-100"
          )}
        >
          <span className="inline-flex items-center gap-1.5">
            <Sparkles className="h-3 w-3 text-indigo-300/85" />
            {suggestion.text}
          </span>
        </button>
      ))}
    </div>
  );
}
