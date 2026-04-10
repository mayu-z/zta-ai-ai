"use client";

import { ArrowUp, Eraser } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

const MAX_SOFT_LIMIT = 600;

export function InputBar({
  disabled,
  onSend,
  onClear,
}: {
  disabled?: boolean;
  onSend: (value: string) => void;
  onClear: () => void;
}) {
  const [value, setValue] = useState("");

  const submit = () => {
    if (!value.trim()) {
      return;
    }
    onSend(value);
    setValue("");
  };

  return (
    <div className="glass-card sticky bottom-0 rounded-[14px] bg-bg p-3">
      <div className="flex gap-2">
        <Textarea
          value={value}
          onChange={(event) => setValue(event.target.value.slice(0, MAX_SOFT_LIMIT))}
          rows={2}
          disabled={disabled}
          placeholder="Ask ZTA-AI anything within your policy scope..."
          className="max-h-36 min-h-[52px] resize-y border-border bg-bg"
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              submit();
            }
          }}
        />
        <div className="flex flex-col gap-2">
          <Button
            type="button"
            onClick={submit}
            disabled={disabled || !value.trim()}
            className="h-11 w-11 rounded-lg"
            aria-label="Send message"
          >
            <ArrowUp className="h-4 w-4" />
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              setValue("");
              onClear();
            }}
            className="h-11 w-11 rounded-lg border-border bg-primary-tint"
            aria-label="Clear chat"
          >
            <Eraser className="h-4 w-4" />
          </Button>
        </div>
      </div>
      <div className="mt-2 flex items-center justify-between text-xs text-text-faint">
        <span>Enter to send, Shift+Enter for newline</span>
        {value.length > 400 ? (
          <span className="mono-number text-primary-hover">{value.length}/{MAX_SOFT_LIMIT}</span>
        ) : (
          <span />
        )}
      </div>
    </div>
  );
}
