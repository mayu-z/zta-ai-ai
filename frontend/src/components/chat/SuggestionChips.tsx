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
            "group shrink-0 rounded-full border border-[#81B78A] bg-[#EEF7EF] px-3 py-1.5 text-xs text-[#1F6B2A] transition-all duration-150",
            "hover:border-[#2E7D32] hover:bg-[#E4F2E6] hover:text-[#17541F]"
          )}
        >
          <span className="inline-flex items-center gap-1.5">
            <Sparkles className="h-3 w-3 text-[#2E7D32]" />
            {suggestion.text}
          </span>
        </button>
      ))}
    </div>
  );
}
