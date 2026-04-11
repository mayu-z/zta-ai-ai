import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

import { loginPlatformAdmin, loginWithEmail, logoutSession } from "@/lib/api";
import type { AuthResponse, AuthUser, ScopeClaims } from "@/types";

interface AuthState {
  user: AuthUser | null;
  token: string | null;
  scope: ScopeClaims | null;
  hydrated: boolean;
  setSession: (session: AuthResponse) => void;
  clearSession: () => void;
  login: (email: string, options?: { systemAdmin?: boolean }) => Promise<void>;
  logout: () => Promise<void>;
}

function decodeBase64Url(input: string): string {
  const normalized = input.replace(/-/g, "+").replace(/_/g, "/");
  const padded = normalized.padEnd(normalized.length + ((4 - (normalized.length % 4)) % 4), "=");

  if (typeof window !== "undefined" && typeof window.atob === "function") {
    return window.atob(padded);
  }

  return Buffer.from(padded, "base64").toString("utf-8");
}

function decodeScopeClaims(token: string): ScopeClaims | null {
  try {
    const payloadPart = token.split(".")[1];
    if (!payloadPart) {
      return null;
    }

    const payloadRaw = decodeBase64Url(payloadPart);
    const payload = JSON.parse(payloadRaw) as Record<string, unknown>;

    const allowedDomains = Array.isArray(payload.allowed_domains)
      ? payload.allowed_domains.filter((value): value is string => typeof value === "string")
      : [];

    const deniedDomains = Array.isArray(payload.denied_domains)
      ? payload.denied_domains.filter((value): value is string => typeof value === "string")
      : [];

    const maskedFields = Array.isArray(payload.masked_fields)
      ? payload.masked_fields.filter((value): value is string => typeof value === "string")
      : [];

    return {
      session_id: typeof payload.session_id === "string" ? payload.session_id : "",
      role_key: typeof payload.role_key === "string" ? payload.role_key : "",
      allowed_domains: allowedDomains,
      denied_domains: deniedDomains,
      masked_fields: maskedFields,
      chat_enabled: Boolean(payload.chat_enabled),
      aggregate_only: Boolean(payload.aggregate_only),
    };
  } catch {
    return null;
  }
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      token: null,
      scope: null,
      hydrated: false,
      setSession: (session) => {
        set({
          user: session.user,
          token: session.jwt,
          scope: decodeScopeClaims(session.jwt),
        });
      },
      clearSession: () => {
        set({ user: null, token: null, scope: null });
      },
      login: async (email: string, options?: { systemAdmin?: boolean }) => {
        const response = options?.systemAdmin
          ? await loginPlatformAdmin(email)
          : await loginWithEmail(email);
        get().setSession(response);
      },
      logout: async () => {
        const token = get().token;
        if (token) {
          try {
            await logoutSession(token);
          } catch {
            // Session is cleared locally even if backend logout fails.
          }
        }
        get().clearSession();
      },
    }),
    {
      name: "zta-auth-store-v2",
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        user: state.user,
        token: state.token,
        scope: state.scope,
      }),
      onRehydrateStorage: () => {
        return (state) => {
          if (state) {
            state.hydrated = true;
          }
        };
      },
    }
  )
);
