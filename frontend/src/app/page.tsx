"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { Skeleton } from "@/components/ui/skeleton";
import { useAuthStore } from "@/stores/authStore";

export default function RootPage() {
  const router = useRouter();
  const token = useAuthStore((state) => state.token);
  const hydrated = useAuthStore((state) => state.hydrated);

  useEffect(() => {
    if (!hydrated) {
      return;
    }
    if (token) {
      router.replace("/chat");
      return;
    }
    router.replace("/login");
  }, [hydrated, token, router]);

  return (
    <main className="flex min-h-screen items-center justify-center px-6">
      <div className="w-full max-w-md space-y-3">
        <Skeleton className="h-8 w-44" />
        <Skeleton className="h-24 w-full" />
      </div>
    </main>
  );
}
