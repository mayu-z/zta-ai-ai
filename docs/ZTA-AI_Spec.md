# ZTA-AI Campus Platform — Engineering Specification (SLM-Strict)
**Version 1.0 • March 2026 • CONFIDENTIAL — INTERNAL USE ONLY**

---

## 1. What We Are Building
ZTA-AI Campus is a secure, AI-powered internal assistant for universities. It allows every person affiliated with a campus (approx. 20,000 users) to ask natural language questions about university data and receive accurate, access-controlled answers in real-time.

### The One Rule That Cannot Be Broken
The Small Language Model (SLM) that composes answers **never sees real data values, real table names, real column names, or real identifiers**. It receives only pre-approved, structured claim payloads and produces structured JSON output. The SLM is **fundamentally untrusted** — it has no tool/function access, no memory, no database access, and no decision-making authority. Real values are injected after the SLM has completed its work by a separate, trusted **Compiler layer**.

### Non-Negotiable Principles
*   **SLM-blind data**: Structural enforcement of aliased schemas and abstract intent. SLM receives only sanitized claims.
*   **SLM Sandboxing**: SLM runs in isolated environment with no network access, no persistent storage, no tool calling.
*   **Per-user data scope**: Enforced at the compiler layer with mandatory user ID filters.
*   **Claim-based data model**: All data represented as immutable, versioned claims with provenance.
*   **Output validation**: All SLM outputs validated against input claims for hallucination detection.
*   **Tenant isolation**: Separate namespaces per university at every layer.
*   **Sub-200ms intent cache**: Critical for high-volume results days.
*   **Immutable audit log**: Append-only log of every query and security event.
*   **India data residency**: All inference runs on Azure in Central India.

---

## 2. Architecture Overview
ZTA-AI is a **distributed, deterministic, policy-driven system** where every layer is stateless and independently scalable. The SLM operates in a **fully sandboxed, non-authoritative environment**.

1.  **L1 Client Layer**: PWA interface, handles SSO login and streams tokens.
2.  **L2 Zero Trust Gate**: Validates OAuth tokens, builds signed JWT with user persona/scope, enforces RBAC+ABAC.
3.  **L3 Interpreter**: Deterministic intent parsing. Aliases schema, sanitizes prompts, and extracts structured intent. No SLM usage.
4.  **L4 Compiler (Control Plane)**: Central authority. Translates intent → execution plan, enforces policies, orchestrates downstream components.
5.  **L5 Policy Engine**: Evaluates RBAC/ABAC rules, applies compliance constraints, enforces row/field-level security.
6.  **L6 Tool / Function Layer**: Controlled data access via strictly defined APIs. No dynamic query generation.
7.  **L7 Claim Engine**: Immutable fact store. All data as versioned claims with provenance and compliance tags.
8.  **L8 Context Governance**: Data minimization, redaction, filtering before SLM interaction.
9.  **L9 SLM Runtime (Sandboxed)**: Receives only approved claims. Converts structured data → structured output. No tools, no memory, no decisions.
10. **L10 Output Validation**: Validates SLM output against input claims, detects hallucinations, enforces schema compliance.
11. **L11 Response Renderer**: Final formatting for UI delivery.
12. **L12 Admin Dashboard**: Exclusive tool for IT heads to manage users, sources, and policies.

---

## 3. Technology Stack

### Backend Services
*   **Language**: Python 3.11+
*   **Framework**: FastAPI
*   **Task Queue**: Celery + Redis (for sync and async logging)
*   **Cache**: Redis (Intent cache, session cache)
*   **Primary DB**: PostgreSQL 15 (RDS or Cloud SQL)
*   **Vector DB**: Pinecone or Weaviate (for document search / RAG path)
*   **SLM**: Sandboxed Small Language Model (Azure / Self-hosted) — isolated container, no external access
*   **ORM**: SQLAlchemy 2.0 with Alembic

### Frontend & Infrastructure
*   **Frontend**: Next.js 14 (App Router) with Tailwind CSS + shadcn/ui.
*   **State Management**: Zustand.
*   **Infrastructure**: AWS (ECS Fargate) or GCP (Cloud Run).
*   **CI/CD**: GitHub Actions.
*   **Monitoring**: Sentry (errors), Datadog/Grafana (metrics).

---

## 4. Sprint Plan Summary (Phase 1–3)

### Phase 1: Foundation (Sprints 1–4)
*   **Sprint 1**: Auth, Identity, and Zero Trust Gate Foundation (Google OAuth, JWT signing, RBAC+ABAC).
*   **Sprint 2**: Interpreter — Deterministic Intent Parsing (Domain gate, prompt sanitizer, schema aliaser).
*   **Sprint 3**: Compiler, Policy Engine, and Claim Engine (Central authority, parameterized queries, immutable claims).
*   **Sprint 4**: Context Governance, SLM Runtime, and Output Validation (Data minimization, sandboxed SLM, hallucination detection).

### Phase 2: Campus Features (Sprints 5–7)
*   **Sprint 5**: Tool/Function Layer and Data Connectors (ERPNext, Sheets, MySQL — strict API contracts).
*   **Sprint 6**: Chat Interface and Streaming Frontend (PWA, role-aware home screen, structured output rendering).
*   **Sprint 7**: Admin Dashboard (User management, schema manager, audit viewer, policy config).

### Phase 3: Scale and Polish (Sprints 8–10)
*   **Sprint 8**: Performance and Scale Testing (2,000 simultaneous queries, cache optimization).
*   **Sprint 9**: Security Hardening and Penetration Testing (Cross-tenant/Cross-user testing).
*   **Sprint 10**: Launch Readiness, UAT, and Go-Live.

---

## 5. Definition of Done (Product Level)
*   All 10 sprint acceptance criteria pass in production.
*   P95 latency under 5 seconds for 2,000 concurrent users.
*   Security pen test complete with zero critical/high findings.
*   SLM isolation verified — no tool access, no memory, no raw data exposure.
*   Output validation catches 100% of simulated hallucination attacks.
*   IT heads can onboard their campus without ZTA-AI team help.
*   5 users from each of the 6 persona types complete UAT without critical issues.
*   Data backup and recovery tested with a successful restore drill.
