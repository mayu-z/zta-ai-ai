"use client";

import { Check, ChevronDown, KeyRound, Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useAuthStore } from "@/stores/authStore";
import { useToastStore } from "@/stores/toastStore";
import { PERSONA_BADGE_COLOR, PERSONA_GROUPS, type PersonaOption } from "@/types";

const defaultPersona = PERSONA_GROUPS[1]?.items[0] ?? PERSONA_GROUPS[0].items[0];

export default function LoginPage() {
  const router = useRouter();
  const login = useAuthStore((state) => state.login);
  const addError = useToastStore((state) => state.addError);

  const [selected, setSelected] = useState<PersonaOption>(defaultPersona);
  const [loading, setLoading] = useState(false);
  const [transitionOut, setTransitionOut] = useState(false);

  const totalPersonas = useMemo(
    () => PERSONA_GROUPS.reduce((sum, group) => sum + group.items.length, 0),
    []
  );

  const onLogin = async () => {
    if (loading) {
      return;
    }

    setLoading(true);
    try {
      await login(selected.email);
      setTransitionOut(true);
      setTimeout(() => {
        router.replace("/chat");
      }, 260);
    } catch (error) {
      const message =
        error instanceof Error && error.message.trim()
          ? error.message
          : "Unable to sign in with selected persona.";
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
      <div className="glass-card w-full max-w-xl rounded-2xl border border-white/10 p-8 backdrop-blur-sm">
        <div className="mb-8 flex items-center gap-3">
          <div className="relative flex h-12 w-12 items-center justify-center rounded-xl border border-indigo-400/35 bg-indigo-500/15">
            <Sparkles className="h-6 w-6 text-indigo-200" />
            <span className="animate-pulse-dot absolute -right-1 -top-1 h-2.5 w-2.5 rounded-full bg-emerald-400" />
          </div>
          <div>
            <h1 className="text-xl font-semibold tracking-wide text-text-primary">ZTA-AI</h1>
            <p className="text-sm text-text-muted">Zero Trust AI Gateway</p>
          </div>
        </div>

        <div className="space-y-4">
          <p className="text-sm text-text-muted">
            Select a seeded persona to authenticate against the live backend.
          </p>

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="outline"
                className="h-12 w-full justify-between border-white/12 bg-surface/70 px-4 text-left text-text-primary hover:bg-surface-elevated"
              >
                <span className="flex flex-col leading-tight">
                  <span className="text-sm font-medium">{selected.name}</span>
                  <span className="text-xs text-text-muted">{selected.email}</span>
                </span>
                <ChevronDown className="h-4 w-4 text-text-muted" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="max-h-[420px] w-[var(--radix-dropdown-menu-trigger-width)] overflow-y-auto">
              {PERSONA_GROUPS.map((group, groupIndex) => (
                <div key={group.title}>
                  <DropdownMenuLabel>{group.title}</DropdownMenuLabel>
                  {group.items.map((persona) => (
                    <DropdownMenuItem
                      key={persona.key}
                      className="flex cursor-pointer items-center justify-between gap-2"
                      onClick={() => setSelected(persona)}
                    >
                      <div className="flex flex-col leading-tight">
                        <span className="text-sm text-text-primary">{persona.name}</span>
                        <span className="text-xs text-text-muted">{persona.email}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge className={PERSONA_BADGE_COLOR[persona.type]}>{persona.type.replace("_", " ")}</Badge>
                        {selected.key === persona.key ? <Check className="h-4 w-4 text-emerald-300" /> : null}
                      </div>
                    </DropdownMenuItem>
                  ))}
                  {groupIndex < PERSONA_GROUPS.length - 1 ? <DropdownMenuSeparator /> : null}
                </div>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>

          <div className="rounded-lg border border-white/10 bg-black/20 p-3 text-xs text-text-muted">
            Personas available: <span className="mono-number">{totalPersonas}</span>
          </div>

          <Button
            onClick={onLogin}
            disabled={loading}
            className="h-11 w-full gap-2 rounded-lg bg-accent text-white hover:bg-accent-hover"
          >
            <KeyRound className="h-4 w-4" />
            {loading ? "Signing in..." : "Login as Selected Persona"}
          </Button>
        </div>
      </div>
    </main>
  );
}
