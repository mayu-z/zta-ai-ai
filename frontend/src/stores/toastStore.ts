import { create } from "zustand";

export interface ToastItem {
  id: string;
  message: string;
}

interface ToastState {
  toasts: ToastItem[];
  addError: (message: string) => void;
  removeToast: (id: string) => void;
}

function makeId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
}

export const useToastStore = create<ToastState>((set) => ({
  toasts: [],
  addError: (message) => {
    const id = makeId();
    set((state) => ({
      toasts: [...state.toasts, { id, message }],
    }));

    setTimeout(() => {
      set((state) => ({
        toasts: state.toasts.filter((toast) => toast.id !== id),
      }));
    }, 4000);
  },
  removeToast: (id) => {
    set((state) => ({
      toasts: state.toasts.filter((toast) => toast.id !== id),
    }));
  },
}));
