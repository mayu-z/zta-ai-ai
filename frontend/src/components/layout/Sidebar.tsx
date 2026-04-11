"use client";

import { Database, GitBranch, LogOut, MessageSquare, Shield } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/stores/authStore";
import { PERSONA_BADGE_COLOR } from "@/types";

const tenantAdminNavItems = [
  { href: "/tenant-admin", label: "Dashboard", icon: GitBranch },
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/sources", label: "Data Sources", icon: Database },
  { href: "/audit", label: "Audit Log", icon: Shield },
];

const endUserNavItems = [{ href: "/chat", label: "Chat", icon: MessageSquare }];

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const user = useAuthStore((state) => state.user);
  const logout = useAuthStore((state) => state.logout);
  const isTenantAdmin = user?.persona === "it_head";
  const navItems = isTenantAdmin ? tenantAdminNavItems : endUserNavItems;

  const initials = user?.name
    ? user.name
        .split(" ")
        .slice(0, 2)
        .map((part) => part[0])
        .join("")
    : "ZT";

  return (
    <>
      <aside
        className="hidden h-[calc(100vh-2rem)] w-[240px] shrink-0 flex-col border-r border-border bg-bg p-4 lg:flex"
        style={{ borderRightWidth: "0.5px" }}
      >
        <div className="mb-6 flex items-center gap-2">
          <span className="animate-pulse-dot h-2.5 w-2.5 rounded-full bg-primary" />
          <h2 className="text-sm font-medium uppercase tracking-[0.14em] text-text-primary">◈ ZTA-AI</h2>
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
                  "group flex items-center gap-3 rounded-md border border-transparent border-l-2 border-l-transparent px-3 py-2 text-sm text-text-muted transition-all duration-150",
                  active
                    ? "border-border border-l-primary bg-primary-tint text-primary-hover"
                    : "hover:border-border hover:bg-primary-tint hover:text-text-primary"
                )}
              >
                <Icon className="h-4 w-4" />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>

        <div className="mt-auto space-y-3">
          <div className="rounded-xl border border-border bg-bg p-3">
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
              className="mt-3 w-full justify-start border border-border bg-primary-tint text-text-muted hover:bg-primary-tint hover:text-text-primary"
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

      <nav className="fixed bottom-0 left-0 right-0 z-40 border-t border-border bg-bg p-2 lg:hidden">
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
                  active ? "bg-primary-tint text-primary-hover" : "text-text-muted hover:bg-primary-tint"
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
