"use client";

import { X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useToastStore } from "@/stores/toastStore";

export function ToastHost() {
  const toasts = useToastStore((state) => state.toasts);
  const removeToast = useToastStore((state) => state.removeToast);

  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-[100] flex w-full max-w-sm flex-col gap-2">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className="pointer-events-auto flex items-start gap-2 rounded-lg border border-primary bg-primary-tint px-3 py-2 text-sm text-primary-hover backdrop-blur"
        >
          <div className="flex-1">{toast.message}</div>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => removeToast(toast.id)}
            className="h-6 w-6 text-primary-hover hover:bg-primary-tint"
            aria-label="Dismiss error"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      ))}
    </div>
  );
}
