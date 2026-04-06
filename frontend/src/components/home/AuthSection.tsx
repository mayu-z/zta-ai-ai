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
    <div className="min-h-screen px-4 py-6 text-slate-100 md:px-8 md:py-8">
      <motion.div
        className="mx-auto flex w-full max-w-7xl flex-col gap-6"
        initial={{ opacity: 0, y: 22 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35, ease: "easeOut" }}
      >
        <header className="glass-panel rounded-2xl p-5 md:p-6">
          <p className="font-mono text-xs uppercase tracking-[0.26em] text-cyan-200">
            Zero Trust AI Platform
          </p>
          <h1 className="mt-3 text-2xl font-semibold tracking-tight text-slate-100 md:text-4xl">
            Campus Security Command Console
          </h1>
          <p className="mt-3 max-w-3xl text-sm text-slate-300 md:text-base">
            Sign in with any seeded role to test RBAC, scoped chat responses,
            policy enforcement, and live pipeline telemetry in one place.
          </p>

          <div className="mt-5 grid gap-3 md:grid-cols-[1fr_auto_auto]">
            <label className="flex flex-col gap-1 text-xs uppercase tracking-[0.18em] text-slate-400">
              API Base URL
              <input
                className="rounded-xl border border-slate-600 bg-slate-900/70 px-3 py-2 text-sm text-slate-100 outline-none transition focus:border-cyan-300"
                value={apiBase}
                onChange={(event) => onApiBaseChange(event.target.value)}
                placeholder="http://localhost:8000"
              />
            </label>
            <button
              className="rounded-xl border border-cyan-300/70 bg-cyan-300/10 px-4 py-2 text-sm font-semibold text-cyan-100 transition hover:bg-cyan-300/20"
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
              className="glass-panel rounded-2xl border border-slate-600/80 p-4 text-left transition hover:border-cyan-300/70 hover:bg-cyan-200/5"
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.045, duration: 0.25 }}
              onClick={() => onLoginWithEmail(preset.email)}
              disabled={authBusy}
            >
              <p className="font-mono text-xs uppercase tracking-[0.22em] text-cyan-200/90">
                {preset.label}
              </p>
              <p className="mt-2 text-base font-semibold text-slate-100">
                {preset.email}
              </p>
              <p className="mt-2 text-sm text-slate-300">{preset.note}</p>
            </motion.button>
          ))}
        </section>

        <section className="glass-panel rounded-2xl p-5 md:p-6">
          <p className="text-xs uppercase tracking-[0.2em] text-slate-400">
            Custom role login
          </p>
          <div className="mt-3 flex flex-col gap-3 md:flex-row">
            <input
              className="flex-1 rounded-xl border border-slate-600 bg-slate-900/70 px-3 py-2 text-sm text-slate-100 outline-none transition focus:border-cyan-300"
              placeholder="example: dean@ipeds.local"
              value={loginEmail}
              onChange={(event) => onLoginEmailChange(event.target.value)}
            />
            <button
              type="button"
              className="rounded-xl border border-emerald-300/70 bg-emerald-300/10 px-4 py-2 text-sm font-semibold text-emerald-100 transition hover:bg-emerald-300/20 disabled:cursor-not-allowed disabled:opacity-60"
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
