# ZTA-AI — System Architecture (SLM-Strict)
**Zero Trust Architecture — Internal AI Assistant Platform**

---

## 01 — Architectural Layers

ZTA-AI is a **distributed, deterministic, policy-driven system** designed around strict **Zero Trust principles**. The architecture ensures that **all sensitive operations occur within trusted layers**, while the **SLM operates in a fully sandboxed, non-authoritative environment**. Data flows strictly **top → down** with no backward propagation from the SLM.

### Layer 1: Clients (The Interface)
The entry point for all users. No business logic resides here.
*   **Web Client**: Browser-based chat interface for employees (HTTPS/TLS 1.3).
*   **Mobile Client**: iOS / Android native app with device binding (mTLS).
*   **API Client**: Programmatic access for internal systems (API KEY + JWT).
*   **Enterprise SSO**: SAML 2.0 / OIDC integration with corporate identity providers.

### Layer 2: Zero Trust Gate (The Entry Policy)
Every request is re-verified; there is no implicit trust based on network location.
*   **Identity Verifier**: Continuous MFA. No session is implicitly trusted.
*   **Device Trust**: Posture checks, certificate validation, and OS compliance.
*   **RBAC + ABAC Engine**: Role-based and attribute-based access enforcement (time, location, sensitivity, risk scoring).
*   **Audit Logger**: Immutable logs of every prompt, query, and response with user attribution.

### Layer 3: Interpreter (Deterministic Intent Parsing)
Translates natural language into a safe, structured format. **No SLM/LLM usage**.
*   **Prompt Sanitizer**: Strips PII, removes injection attempts, and detects prompt attacks.
*   **Intent Mapper**: Converts natural language into structured intent objects (schema-based parsing).
*   **Context Abstractor**: Replaces schema, table, and field names with abstract aliases.
*   **Scope Validator**: Validates query against allowed intent schemas, rejects ambiguous queries.

> **[!] ISOLATION BOUNDARY:** The SLM has zero knowledge of database schemas, table names, real field names, or raw data. It only receives pre-approved, sanitized claim payloads.

### Layer 4: Compiler (Central Control Plane)
The **central authority** of the system. Deterministic, stateless, fully auditable.
*   **Execution Planner**: Translates intent → execution plan.
*   **Policy Enforcer**: Enforces policy constraints before any data access.
*   **Orchestrator**: Controls data flow between all downstream layers.
*   **Trace Maintainer**: Maintains full execution trace for auditability.

### Layer 5: Policy Engine (Access Enforcement)
*   **RBAC Evaluator**: Role-based access control rules.
*   **ABAC Evaluator**: Attribute-based conditions (time, location, sensitivity).
*   **Compliance Enforcer**: Applies GDPR, DPDP, AML constraints.
*   **Row/Field Security**: Enforces row-level and field-level security.

### Layer 6: Tool / Function Layer (Controlled Data Access)
Provides strictly defined APIs for data access. **No dynamic query generation**.
*   **Schema-Bound Queries**: All queries follow predefined schemas.
*   **API Contracts**: `getClaimsByEntity(entity_type, filters)`, `getAggregatedMetrics(params)`.
*   **No Direct DB Exposure**: All access via controlled interfaces.

### Layer 7: Claim Engine (Immutable Fact Store)
The core data layer storing all data as **immutable, versioned claims**.
*   **Claim Structure**: ID, tenant_id, entity_type, value, timestamp, version, provenance, sensitivity, compliance_tags.
*   **Provenance Tracking**: Full lineage for every claim.
*   **Tenant Isolation**: Hard isolation between tenants.

### Layer 8: Context Governance Layer (Data Minimization)
Enforces **strict data minimization and sanitization** before any model interaction.
*   **Claim Filtering**: Filters claims based on access scope.
*   **Redaction Engine**: Redacts sensitive fields.
*   **Aggregation**: Aggregates or summarizes data as needed.
*   **Compliance Constraints**: Prevents inference attacks.
*   **Output**: Sanitized, minimal claim payload for SLM.

### Layer 9: SLM Runtime (Sandboxed, Untrusted)
The Small Language Model operates as a **stateless rendering engine** in a fully isolated environment.

**Environment:**
*   Isolated container / microservice.
*   No network access to internal systems.
*   No persistent storage.
*   Stateless execution per request.

**Responsibilities:**
*   Convert structured claims → structured output (JSON).
*   Generate explanations and summaries.
*   Apply tone and formatting.

**Constraints (The SLM MUST NEVER):**
*   Access databases (directly or indirectly).
*   See raw company data or schemas.
*   Decide what data to retrieve.
*   Execute business logic or computations.
*   Call tools, APIs, or functions.
*   Maintain memory or state across requests.

**Output Format:**
```json
{
  "summary": "Total expenses exceed threshold.",
  "details": "Finance department recorded multiple expenses above 5000.",
  "confidence": 0.93
}
```

### Layer 10: Output Validation Layer
Ensures response integrity before delivery.
*   **Fact Validator**: Validates output against input claims.
*   **Hallucination Detector**: Detects unsupported facts or entities.
*   **Schema Enforcer**: Ensures output matches expected schema.
*   **Rejection Handler**: Rejects invalid outputs.

### Layer 11: Response Renderer
Final presentation formatting.
*   **Format Converter**: Converts structured output → UI-ready format.
*   **Template Applier**: Applies templates and formatting rules.
*   **Consistency Enforcer**: Ensures consistency across responses.

---

## 02 — Full Request Lifecycle (End-to-End Flow)

1.  **User Prompt**
2.  **Zero Trust Gate** (Identity + Device + RBAC/ABAC check)
3.  **Interpreter** (Deterministic intent parsing, schema aliasing)
4.  **Compiler** (Execution plan, policy enforcement)
5.  **Policy Engine** (RBAC + ABAC + Compliance evaluation)
6.  **Tool / Function Layer** (Controlled API calls)
7.  **Claim Engine** (Immutable claim retrieval)
8.  **Context Governance** (Filtering + Redaction + Minimization)
9.  **SLM Runtime** (Sandboxed rendering — structured output)
10. **Output Validation** (Fact check + Hallucination detection)
11. **Response Renderer** (UI-ready formatting)
12. **User Response** (With full audit trail)

---

## 03 — Zero Trust Principles Applied

| Principle | Implementation |
| :--- | :--- |
| **01 // NEVER TRUST** | **Verify Every Request**: No session is implicitly trusted. Every API call re-verifies identity and posture. SLM is fundamentally untrusted. |
| **02 // LEAST PRIVILEGE** | **Minimal Data Exposure**: The SLM only receives pre-approved, sanitized claims. No raw data, no schemas, no tool access. |
| **03 // MICRO-SEGMENT** | **Hard Isolation Layers**: Interpreter, Compiler, Policy Engine, Claim Engine, and SLM run in isolated execution zones. |
| **04 // ASSUME BREACH** | **Continuous Monitoring**: All layers emit to a central SIEM with anomaly detection. SLM outputs validated for hallucinations. |
| **05 // UNIDIRECTIONAL FLOW** | **Top → Down Only**: Data flows strictly top → down. No backward data propagation from SLM. |
| **06 // STATELESS PROCESSING** | **No Memory**: Each request is independent. No session memory in SLM or interpreter. |

---

## 04 — Layer Color Legend (Technical Map)
*   **Yellow**: Zero Trust Gate / Authentication
*   **Purple**: Interpreter / Deterministic Parsing
*   **Blue**: Compiler / Control Plane / Policy Engine
*   **Green**: Claim Engine / Immutable Fact Store
*   **Cyan**: Context Governance / Data Minimization
*   **Orange**: SLM Runtime (Sandboxed, Untrusted)
*   **Red**: Output Validation / Hallucination Detection

---

## 05 — Isolation Boundaries

| Layer | Isolation Type |
| :--- | :--- |
| Data Layer (Claims) | Network + logical isolation |
| Policy Engine | Execution isolation |
| SLM Runtime | Full sandbox (no trust) |

---

## 06 — Failure Handling

### Fail-Safe Principles
* Deny by default
* Graceful degradation
* No fallback to unsafe paths

### Example Failures

| Failure | Behavior |
| :--- | :--- |
| Policy violation | Request rejected |
| Claim fetch failure | Partial response or fail |
| SLM failure | Template-based fallback |
| Validation failure | Response rejected |

---

## 07 — Performance Targets

* p95 latency: < 500ms
* Policy evaluation: < 50ms
* Claim retrieval: < 100ms
* SLM inference: < 200ms
