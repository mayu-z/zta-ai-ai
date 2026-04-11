"use client";

import { KeyRound, ShieldCheck, Sparkles, UserCircle2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuthStore } from "@/stores/authStore";
import { useToastStore } from "@/stores/toastStore";

export default function LoginPage() {
  const router = useRouter();
  const login = useAuthStore((state) => state.login);
  const addError = useToastStore((state) => state.addError);

  const [email, setEmail] = useState("");
  const [loginMode, setLoginMode] = useState<"tenant_user" | "platform_admin">(
    "tenant_user"
  );
  const [loading, setLoading] = useState(false);
  const [transitionOut, setTransitionOut] = useState(false);

  const onLogin = async () => {
    if (loading) {
      return;
    }

    const normalizedEmail = email.trim().toLowerCase();
    if (!normalizedEmail.includes("@")) {
      addError("Enter a valid organization email.");
      return;
    }

    setLoading(true);
    try {
      const isSystemAdmin = loginMode === "platform_admin";
      await login(normalizedEmail, { systemAdmin: isSystemAdmin });
      setTransitionOut(true);
      setTimeout(() => {
        router.replace(isSystemAdmin ? "/system-admin" : "/chat");
      }, 260);
    } catch (error) {
      const message =
        error instanceof Error && error.message.trim()
          ? error.message
          : "Unable to sign in right now.";
      addError(message);
      setLoading(false);
    }
  };

  return (
    <main
      className={`relative flex min-h-screen items-center justify-center px-5 py-10 transition-opacity duration-300 ${
        transitionOut ? "opacity-0" : "opacity-100"
      }`}
    >
      <div className="glass-card w-full max-w-xl rounded-2xl p-8">
        <div className="mb-8 flex items-center gap-3">
          <div className="relative flex h-12 w-12 items-center justify-center rounded-xl border border-primary bg-primary-tint">
            <Sparkles className="h-6 w-6 text-primary-hover" />
            <span className="animate-pulse-dot absolute -right-1 -top-1 h-2.5 w-2.5 rounded-full bg-primary" />
          </div>
          <div>
            <h1 className="text-xl font-medium tracking-wide text-text-primary">ZTA-AI</h1>
            <p className="text-sm text-text-muted">Zero Trust AI Gateway</p>
          </div>
        </div>

        <div className="space-y-4">
          <p className="text-sm text-text-muted">
            Sign in with your organization email. Tenant admins get the full governance dashboard; other users get a focused chat workspace.
          </p>
          <p className="text-xs text-text-muted">
            Tenant-admin access is inferred from your account profile and routed automatically.
          </p>

          <Input
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="you@yourcollege.edu"
            className="h-12 border-border bg-bg"
            autoComplete="email"
          />

          <div className="grid gap-2 sm:grid-cols-2">
            <button
              type="button"
              onClick={() => setLoginMode("tenant_user")}
              className={`rounded-lg border px-3 py-2 text-left transition ${
                loginMode === "tenant_user"
                  ? "border-primary bg-primary-tint text-primary-hover"
                  : "border-border bg-bg text-text-muted"
              }`}
            >
              <span className="flex items-center gap-2 text-sm font-medium">
                <UserCircle2 className="h-4 w-4" /> Tenant User
              </span>
              <span className="mt-1 block text-xs">Simple assistant experience.</span>
            </button>
            <button
              type="button"
              onClick={() => setLoginMode("platform_admin")}
              className={`rounded-lg border px-3 py-2 text-left transition ${
                loginMode === "platform_admin"
                  ? "border-primary bg-primary-tint text-primary-hover"
                  : "border-border bg-bg text-text-muted"
              }`}
            >
              <span className="flex items-center gap-2 text-sm font-medium">
                <ShieldCheck className="h-4 w-4" /> Platform Admin
              </span>
              <span className="mt-1 block text-xs">Global tenant onboarding console.</span>
            </button>
          </div>

          <Button
            onClick={onLogin}
            disabled={loading}
            className="h-11 w-full gap-2 rounded-lg bg-accent text-white hover:bg-accent-hover"
          >
            <KeyRound className="h-4 w-4" />
            {loading ? "Signing in..." : "Sign in"}
          </Button>
        </div>
      </div>
    </main>
  );
}
