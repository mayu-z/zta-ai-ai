"use client";

import { LogOut, Wifi, WifiOff } from "lucide-react";
import { useRouter } from "next/navigation";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
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
import { PERSONA_BADGE_COLOR } from "@/types";
import { useAuthStore } from "@/stores/authStore";

export function TopBar({ title, connected }: { title: string; connected: boolean }) {
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
    <header className="glass-card flex h-16 items-center justify-between rounded-xl border border-white/10 px-4">
      <div className="min-w-0">
        <h1 className="truncate text-sm font-semibold uppercase tracking-[0.12em] text-text-primary">{title}</h1>
      </div>

      <div className="flex items-center gap-2">
        <Badge variant={connected ? "success" : "danger"} className="gap-1.5">
          {connected ? <Wifi className="h-3 w-3" /> : <WifiOff className="h-3 w-3" />}
          {connected ? "WebSocket Connected" : "WebSocket Disconnected"}
        </Badge>

        {user ? (
          <Badge className={PERSONA_BADGE_COLOR[user.persona]}>{user.persona.replace("_", " ")}</Badge>
        ) : null}

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" className="h-9 w-9 rounded-full border border-white/10 bg-white/5">
              <Avatar className="h-8 w-8">
                <AvatarFallback>{initials}</AvatarFallback>
              </Avatar>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-64">
            <DropdownMenuLabel>
              <div className="flex flex-col">
                <span className="text-sm font-medium text-text-primary">{user?.name || "User"}</span>
                <span className="text-xs text-text-muted">{user?.email || "Not signed in"}</span>
              </div>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              className="cursor-pointer text-red-200 focus:bg-red-500/20"
              onClick={async () => {
                await logout();
                router.replace("/login");
              }}
            >
              <LogOut className="mr-2 h-4 w-4" />
              Logout
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
