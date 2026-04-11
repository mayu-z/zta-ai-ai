# ZTA-AI: Zero Trust Architecture AI System (SLM-Strict)

**Plan Alignment:** This document is aligned to `ZTA_AI_FINAL_PRODUCT_PRODUCTION_PLAN.md` (v3.0, April 11, 2026). If any section conflicts, the plan file is authoritative. See `docs/PLAN_ALIGNMENT.md`.

**Secure Enterprise AI Platform with Zero Trust Data Isolation**

---

# Deployed Docs - https://zta-ai.netlify.app/

## Overview

ZTA-AI is a **production-grade, deterministic, policy-driven data access platform** that enables natural language querying of company-internal data while enforcing **strict Zero Trust principles**. The platform uses a **sandboxed Small Language Model (SLM)** strictly for presentation — ensuring that no raw data, schemas, credentials, or decision logic are ever exposed to the model layer.

**Core Innovation:** Complete separation of data access, business logic, and natural language generation. The SLM operates as a **stateless, sandboxed rendering component** with no decision-making authority, no tool/function access, and no memory across requests.

---

## Documentation Portal

This repository hosts the interactive documentation and specification pages for the ZTA-AI platform:

| Page | Description |
|------|-------------|
| [System Architecture](zta-ai-architecture.html) | Full layered architecture -- client, zero trust gate, interpreter, compiler, policy engine, claim engine, and sandboxed SLM |
| [RBAC / ABAC Access Control](zta-ai-rbac.html) | Role-based and attribute-based access control engine with department-level data silos |
| [Data Integration Layer](zta-ai-integration.html) | Universal connector architecture -- databases, cloud storage, SaaS tools, and file uploads |
| [Market Scope and Opportunity](zta-ai-market-scope.html) | Market analysis, TAM/SAM/SOM breakdown, competitive landscape, and pricing model |
| [BFSI Vertical Strategy](zta-ai-bfsi-strategy.html) | Banking, Financial Services and Insurance go-to-market strategy, compliance mapping, and sales playbook |

---

## Key Capabilities

- **Zero Trust SLM Boundary** -- The Small Language Model is fundamentally untrusted and fully sandboxed. It receives only pre-approved, structured claim payloads — no database access, no tool calling, no memory.
- **Claim-Based Data Model** -- All data is represented as immutable, versioned claims with full provenance, sensitivity classification, and compliance tags.
- **RBAC + ABAC Enforcement** -- Department-level data silos with attribute-based dynamic conditions (time, location, sensitivity, anomaly detection).
- **Context Governance Layer** -- Data minimization, redaction, and sanitization before any model interaction.
- **Output Validation** -- All SLM outputs are validated against input claims to detect hallucinations and ensure schema compliance.
- **Immutable Audit Trail** -- Every query, policy decision, and data access event is logged with full traceability.
- **Multi-Tenant SaaS Architecture** -- Org-level isolation with support for on-premises deployment.
- **Performance Hardening Target** -- Production hardening target is `<1000ms P95` as defined in the plan; lower latency claims require benchmark validation per environment.

---

## Architecture Principles

1. **Zero Trust SLM Boundary** -- The SLM is fundamentally untrusted and sandboxed. It never queries databases, calls tools/functions, decides what data to fetch, or maintains state across requests.
2. **Claim-Based Truth Model** -- All company data is represented as immutable, versioned claims with full provenance tracking, sensitivity classification, and compliance tags.
3. **Deterministic Control Plane** -- The Compiler is the central authority. All decisions are deterministic and testable.
4. **Context Governance** -- Strict data minimization and sanitization before any model interaction.
5. **Separation of Trust Boundaries** -- Strict network and logical isolation between trusted (data/policy) and untrusted (SLM) zones.
6. **Output Validation** -- All SLM outputs are validated for fact consistency and hallucination detection.
7. **Fail-Safe Degradation** -- System degrades gracefully without compromising security.
8. **Auditability First** -- Complete audit trail for every access, decision, and action.

---

## Target Verticals

- **BFSI** -- Banks, insurance, fintechs (RBI FREE-AI, DPDP Act, SEBI compliance)
- **Healthcare** -- HIPAA, HL7/FHIR compliant clinical and administrative data isolation
- **Government / Defense** -- NSA Zero Trust mandate, classified data handling, on-prem deployment
- **Large Enterprise** -- Complex RBAC across 5,000-100,000+ employees
- **Legal** -- Attorney-client privilege enforcement, matter-level data silos
- **SMB** -- Enterprise-grade security with no-code setup and flat pricing

---

## Compliance Coverage

| Framework | Scope |
|-----------|-------|
| RBI FREE-AI | AI governance, bias monitoring, explainability |
| DPDP Act 2023 | Consent flows, data principal rights, breach notification |
| SEBI Cybersecurity | Zero trust access, KYC isolation, vulnerability assessment |
| GDPR | Right to erasure, data minimization, cross-border controls |
| SOC 2 Type II | Security, availability, confidentiality |
| ISO 27001 | Information security management |
| HIPAA | Protected health information isolation |

---

## Technical Specification

Refer to [ZTA-AI_COMPLETE_SPECIFICATION.md](ZTA-AI_COMPLETE_SPECIFICATION.md) for the full system specification covering:

- Data model and claim lifecycle
- Component specifications (ingestion, derivation, query orchestrator, policy engine)
- Coding standards and technology stack
- Deployment, monitoring, and performance targets
- Edge cases and operational procedures

---

## Deployment

This documentation site is deployed via [Netlify](https://www.netlify.com/) with automatic deployments from the main branch.

---

**Version:** 1.0.0
**Classification:** Internal -- Production System Specification

## Local Full-Stack Docker Run

From the repository root:

```bash
docker compose up --build -d
```

Services:

- Frontend: http://localhost:8080
- Backend API: http://localhost:8000
- PostgreSQL: localhost:5432
- Redis: localhost:6379

Notes:

- A one-time `db-init` container automatically seeds baseline tenants/users/claims when the database is empty.
- If data already exists, seeding is skipped and runtime config backfill is applied.
- To force a destructive reseed on startup:

```bash
ZTA_FORCE_RESEED=true ZTA_SEED_PROFILE=full docker compose up --build -d
```

- To fully reset data and reseed from scratch:

```bash
docker compose down -v
docker compose up --build -d
```

To stop:

```bash
docker compose down
```
