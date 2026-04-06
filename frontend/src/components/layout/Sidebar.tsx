"use client";

import { Database, LogOut, MessageSquare, Settings, Shield } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/stores/authStore";
import { PERSONA_BADGE_COLOR } from "@/types";

const navItems = [
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/audit", label: "Audit Log", icon: Shield },
  { href: "/sources", label: "Data Sources", icon: Database },
];

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const user = useAuthStore((state) => state.user);
  const logout = useAuthStore((state) => state.logout);

  const initials = user?.name
    ? user.name
        .split(" ")
        .slice(0, 2)
        .map((part) => part[0])
        .join("")
    : "ZT";

  return (
    <>
      <aside className="glass-card hidden h-[calc(100vh-2rem)] w-[240px] shrink-0 flex-col rounded-xl border border-white/10 p-4 lg:flex">
        <div className="mb-6 flex items-center gap-2">
          <span className="animate-pulse-dot h-2.5 w-2.5 rounded-full bg-emerald-400" />
          <h2 className="text-sm font-semibold uppercase tracking-[0.14em] text-text-primary">◈ ZTA-AI</h2>
        </div>

        <nav className="space-y-1.5">
          {navItems.map((item) => {
            const Icon = item.icon;
            const active = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "group flex items-center gap-3 rounded-lg border border-transparent px-3 py-2 text-sm text-text-muted transition-all duration-150",
                  active
                    ? "border-indigo-400/40 bg-indigo-500/15 text-indigo-100"
                    : "hover:border-white/10 hover:bg-white/5 hover:text-text-primary"
                )}
              >
                <Icon className="h-4 w-4" />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>

        <div className="mt-auto space-y-3">
          <button className="flex w-full items-center gap-3 rounded-lg border border-white/10 px-3 py-2 text-sm text-text-muted transition-colors hover:bg-white/5 hover:text-text-primary">
            <Settings className="h-4 w-4" />
            <span>Settings</span>
          </button>

          <div className="rounded-xl border border-white/10 bg-black/25 p-3">
            <div className="flex items-center gap-3">
              <Avatar className="h-10 w-10">
                <AvatarFallback>{initials}</AvatarFallback>
              </Avatar>
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-text-primary">{user?.name || "Guest"}</p>
                {user ? (
                  <Badge className={PERSONA_BADGE_COLOR[user.persona]}>
                    {user.persona.replace("_", " ")}
                  </Badge>
                ) : null}
              </div>
            </div>

            <Button
              variant="ghost"
              className="mt-3 w-full justify-start border border-white/10 bg-white/5 text-text-muted hover:bg-white/10 hover:text-text-primary"
              onClick={async () => {
                await logout();
                router.replace("/login");
              }}
            >
              <LogOut className="mr-2 h-4 w-4" />
              Logout
            </Button>
          </div>
        </div>
      </aside>

      <nav className="glass-card fixed bottom-0 left-0 right-0 z-40 border-t border-white/10 p-2 lg:hidden">
        <div className="grid grid-cols-3 gap-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            const active = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex flex-col items-center gap-1 rounded-lg py-1.5 text-[11px] transition-colors",
                  active ? "bg-indigo-500/20 text-indigo-100" : "text-text-muted hover:bg-white/5"
                )}
              >
                <Icon className="h-4 w-4" />
                <span>{item.label.replace(" Log", "")}</span>
              </Link>
            );
          })}
        </div>
      </nav>
    </>
  );
}
