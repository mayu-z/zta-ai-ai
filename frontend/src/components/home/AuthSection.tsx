"use client";

import { motion } from "framer-motion";

type Tone = "idle" | "loading" | "ok" | "error";

type StatusMessage = {
  tone: Tone;
  text: string;
  at: string;
};

type RolePreset = {
  label: string;
  email: string;
  note: string;
};

type AuthSectionProps = {
  apiBase: string;
  onApiBaseChange: (value: string) => void;
  status: StatusMessage;
  toneClasses: Record<Tone, string>;
  onHealthCheck: () => void;
  rolePresets: RolePreset[];
  onLoginWithEmail: (email: string) => void;
  authBusy: boolean;
  loginEmail: string;
  onLoginEmailChange: (value: string) => void;
};

export function AuthSection({
  apiBase,
  onApiBaseChange,
  status,
  toneClasses,
  onHealthCheck,
  rolePresets,
  onLoginWithEmail,
  authBusy,
  loginEmail,
  onLoginEmailChange,
}: AuthSectionProps) {
  return (
    <div className="min-h-screen px-4 py-6 text-text md:px-8 md:py-8">
      <motion.div
        className="mx-auto flex w-full max-w-7xl flex-col gap-6"
        initial={{ opacity: 0, y: 22 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35, ease: "easeOut" }}
      >
        <header className="glass-panel rounded-2xl p-5 md:p-6">
          <p className="font-mono text-xs uppercase tracking-[0.26em] text-primary-hover">
            Zero Trust AI Platform
          </p>
          <h1 className="mt-3 text-2xl font-semibold tracking-tight text-text md:text-4xl">
            Campus Security Command Console
          </h1>
          <p className="mt-3 max-w-3xl text-sm text-text-muted md:text-base">
            Sign in with any seeded role to test RBAC, scoped chat responses,
            policy enforcement, and live pipeline telemetry in one place.
          </p>

          <div className="mt-5 grid gap-3 md:grid-cols-[1fr_auto_auto]">
            <label className="flex flex-col gap-1 text-xs uppercase tracking-[0.18em] text-text-muted">
              API Base URL
              <input
                className="rounded-xl border border-border bg-bg px-3 py-2 text-sm text-text outline-none transition focus:border-primary"
                value={apiBase}
                onChange={(event) => onApiBaseChange(event.target.value)}
                placeholder="http://3.106.161.114:8000"
              />
            </label>
            <button
              className="rounded-xl border border-primary bg-primary-tint px-4 py-2 text-sm font-semibold text-primary-hover transition hover:bg-primary-tint"
              onClick={onHealthCheck}
              type="button"
            >
              Check Health
            </button>
            <div
              className={`rounded-xl border px-3 py-2 text-sm ${toneClasses[status.tone]}`}
            >
              {status.text}
            </div>
          </div>
        </header>

        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {rolePresets.map((preset, index) => (
            <motion.button
              key={preset.email}
              type="button"
              className="glass-panel rounded-2xl border border-border p-4 text-left transition hover:border-primary hover:bg-primary-tint"
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.045, duration: 0.25 }}
              onClick={() => onLoginWithEmail(preset.email)}
              disabled={authBusy}
            >
              <p className="font-mono text-xs uppercase tracking-[0.22em] text-primary-hover">
                {preset.label}
              </p>
              <p className="mt-2 text-base font-semibold text-text">
                {preset.email}
              </p>
              <p className="mt-2 text-sm text-text-muted">{preset.note}</p>
            </motion.button>
          ))}
        </section>

        <section className="glass-panel rounded-2xl p-5 md:p-6">
          <p className="text-xs uppercase tracking-[0.2em] text-text-muted">
            Custom role login
          </p>
          <div className="mt-3 flex flex-col gap-3 md:flex-row">
            <input
              className="flex-1 rounded-xl border border-border bg-bg px-3 py-2 text-sm text-text outline-none transition focus:border-primary"
              placeholder="example: dean@ipeds.local"
              value={loginEmail}
              onChange={(event) => onLoginEmailChange(event.target.value)}
            />
            <button
              type="button"
              className="rounded-xl border border-primary bg-primary-tint px-4 py-2 text-sm font-semibold text-primary-hover transition hover:bg-primary-tint disabled:cursor-not-allowed disabled:opacity-60"
              onClick={() => onLoginWithEmail(loginEmail)}
              disabled={authBusy}
            >
              {authBusy ? "Signing in..." : "Sign in"}
            </button>
          </div>
        </section>
      </motion.div>
    </div>
  );
}
