"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuthStore } from "@/stores/authStore";
import { useToastStore } from "@/stores/toastStore";

type TenantSummary = {
  tenant_id: string;
  tenant_name: string;
  email_domain: string;
  subdomain: string;
  status: string;
  plan_tier: string;
  users_count: number;
  claims_count: number;
  created_at: string;
};

type TenantDetail = TenantSummary & {
  seeded_user_emails: string[];
  notes: string[];
};

function errorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }
  return fallback;
}

export default function SystemAdminPage() {
  const router = useRouter();
  const token = useAuthStore((state) => state.token);
  const user = useAuthStore((state) => state.user);
  const hydrated = useAuthStore((state) => state.hydrated);
  const logout = useAuthStore((state) => state.logout);
  const addError = useToastStore((state) => state.addError);

  const [tenantName, setTenantName] = useState("");
  const [tenantDomain, setTenantDomain] = useState("");
  const [busy, setBusy] = useState(false);
  const [tenants, setTenants] = useState<TenantSummary[]>([]);
  const [lastCreated, setLastCreated] = useState<TenantDetail | null>(null);

  const callApi = useCallback(
    async <T,>(path: string, init: RequestInit = {}): Promise<T> => {
      if (!token) {
        throw new Error("Missing auth token");
      }

      const headers = new Headers(init.headers ?? {});
      headers.set("Authorization", `Bearer ${token}`);
      if (init.body && !headers.has("Content-Type")) {
        headers.set("Content-Type", "application/json");
      }

      const response = await fetch(`/api${path}`, {
        ...init,
        headers,
      });

      const contentType = response.headers.get("content-type") || "";
      const payload: unknown = contentType.includes("application/json")
        ? await response.json()
        : await response.text();

      if (!response.ok) {
        if (typeof payload === "object" && payload !== null) {
          const record = payload as Record<string, unknown>;
          if (typeof record.error === "string" && record.error.trim()) {
            throw new Error(record.error);
          }
        }
        if (typeof payload === "string" && payload.trim()) {
          throw new Error(payload);
        }
        throw new Error(`Request failed (${response.status})`);
      }

      return payload as T;
    },
    [token]
  );

  const refreshTenants = useCallback(async () => {
    try {
      const rows = await callApi<TenantSummary[]>("/system-admin/tenants");
      setTenants(rows);
    } catch (error) {
      addError(errorMessage(error, "Unable to load tenants"));
    }
  }, [addError, callApi]);

  useEffect(() => {
    if (!hydrated) {
      return;
    }
    if (!token) {
      router.replace("/login");
      return;
    }
    if (user?.persona !== "system_admin") {
      router.replace("/chat");
      return;
    }
    refreshTenants();
  }, [hydrated, token, user?.persona, router, refreshTenants]);

  const createTenant = async () => {
    if (!tenantName.trim() || !tenantDomain.trim()) {
      addError("Tenant name and domain are required");
      return;
    }

    setBusy(true);
    try {
      const created = await callApi<TenantDetail>("/system-admin/tenants", {
        method: "POST",
        body: JSON.stringify({
          tenant_name: tenantName.trim(),
          email_domain: tenantDomain.trim(),
          seed_mock_users: true,
          seed_mock_claims: true,
        }),
      });
      setLastCreated(created);
      await refreshTenants();
    } catch (error) {
      addError(errorMessage(error, "Unable to create tenant"));
    } finally {
      setBusy(false);
    }
  };

  if (!hydrated || !token) {
    return null;
  }

  if (user?.persona !== "system_admin") {
    return null;
  }

  return (
    <main className="min-h-screen p-6">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-6">
        <section className="rounded-xl border border-border bg-bg p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h1 className="text-xl font-semibold text-text-primary">Global System Admin Console</h1>
              <p className="mt-1 text-sm text-text-muted">
                Create tenant domains, bootstrap university users, and keep onboarding fully backend-driven.
              </p>
            </div>
            <Button
              variant="outline"
              onClick={async () => {
                await logout();
                router.replace("/login");
              }}
            >
              Logout
            </Button>
          </div>
        </section>

        <section className="rounded-xl border border-border bg-bg p-5">
          <h2 className="text-base font-semibold text-text-primary">Create Tenant</h2>
          <div className="mt-4 grid gap-3 md:grid-cols-3">
            <Input
              value={tenantName}
              onChange={(event) => setTenantName(event.target.value)}
              placeholder="Example University"
            />
            <Input
              value={tenantDomain}
              onChange={(event) => setTenantDomain(event.target.value)}
              placeholder="example.edu"
            />
            <Button onClick={createTenant} disabled={busy}>
              {busy ? "Creating..." : "Create Tenant + Seed Data"}
            </Button>
          </div>
          <p className="mt-2 text-xs text-text-muted">
            Optional seeded data includes baseline student, faculty, executive, and operations personas.
          </p>
        </section>

        {lastCreated ? (
          <section className="rounded-xl border border-border bg-bg p-5">
            <h2 className="text-base font-semibold text-text-primary">Last Created Tenant</h2>
            <p className="mt-1 text-sm text-text-muted">
              Domain: @{lastCreated.email_domain} | Users: {lastCreated.users_count} | Claims: {lastCreated.claims_count}
            </p>
            <div className="mt-3 grid gap-2 md:grid-cols-2">
              {lastCreated.seeded_user_emails.map((email) => (
                <div key={email} className="rounded-md border border-border px-3 py-2 text-xs text-text-primary">
                  {email}
                </div>
              ))}
            </div>
          </section>
        ) : null}

        <section className="rounded-xl border border-border bg-bg p-5">
          <h2 className="text-base font-semibold text-text-primary">Tenants</h2>
          <div className="mt-3 overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead>
                <tr className="text-text-muted">
                  <th className="py-2 pr-4">Tenant</th>
                  <th className="py-2 pr-4">Domain</th>
                  <th className="py-2 pr-4">Plan</th>
                  <th className="py-2 pr-4">Status</th>
                  <th className="py-2 pr-4">Users</th>
                  <th className="py-2 pr-4">Claims</th>
                </tr>
              </thead>
              <tbody>
                {tenants.map((tenant) => (
                  <tr key={tenant.tenant_id} className="border-t border-border text-text-primary">
                    <td className="py-2 pr-4">{tenant.tenant_name}</td>
                    <td className="py-2 pr-4">@{tenant.email_domain}</td>
                    <td className="py-2 pr-4">{tenant.plan_tier}</td>
                    <td className="py-2 pr-4">{tenant.status}</td>
                    <td className="py-2 pr-4">{tenant.users_count}</td>
                    <td className="py-2 pr-4">{tenant.claims_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </main>
  );
}
