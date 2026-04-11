# ZTA-AI: Technical Architecture & System Structure (SLM-Strict)

**Plan Alignment:** This technical architecture document is aligned to `ZTA_AI_FINAL_PRODUCT_PRODUCTION_PLAN.md` (v3.0, April 11, 2026). If there is any mismatch, the production plan is the source of truth. See `docs/PLAN_ALIGNMENT.md`.

## System Overview

ZTA-AI is a **distributed, deterministic, policy-driven system** designed around strict **Zero Trust principles**.
The architecture is composed of **isolated, independently deployable components**, each with clearly defined responsibilities and trust boundaries.

The system enforces **unidirectional, controlled data flow** and ensures that **all sensitive operations occur within trusted layers**, while the **SLM operates in a fully sandboxed, non-authoritative environment**.

---

## High-Level System Topology

```id="zt_topology"
[ Client / UI Layer ]
        ↓
[ Zero Trust Gate ]
        ↓
[ Interpreter Layer ]
        ↓
[ Compiler (Control Plane) ]
        ↓
[ Policy Engine ]
        ↓
[ Tool / Function Layer ]
        ↓
[ Claim Engine (Fact Store) ]
        ↓
[ Context Governance Layer ]
        ↓
[ SLM (Sandboxed Runtime) ]
        ↓
[ Output Validation Layer ]
        ↓
[ Response Renderer ]
```

---

## Core Components

---

### 1. Client / UI Layer

**Role:** User interaction interface

**Responsibilities:**

* Accept natural language queries
* Display structured or rendered responses
* Handle authentication tokens (JWT/OAuth)

**Constraints:**

* No direct access to backend data
* No business logic execution

---

### 2. Zero Trust Gate

**Role:** Entry point enforcing identity and access validation

**Responsibilities:**

* Authentication (JWT, OAuth2, SSO)
* RBAC (Role-Based Access Control)
* ABAC (Attribute-Based Access Control)
* Risk scoring (device, location, behavior)
* Request validation

**Output:**

* Verified identity context
* Access scope metadata

---

### 3. Interpreter Layer

**Role:** Deterministic intent parsing

**Responsibilities:**

* Convert natural language → structured intent
* Validate query against allowed intent schemas
* Reject ambiguous or unsupported queries

**Constraints:**

* No LLM/SLM usage
* Strict schema-based parsing

**Output Example:**

```id="intent_schema"
{
  "action": "FETCH_EXPENSES",
  "filters": {
    "amount_gt": 5000,
    "department": "finance"
  }
}
```

---

### 4. Compiler (Control Plane)

**Role:** Central orchestrator and authority of the system

**Responsibilities:**

* Translate intent → execution plan
* Enforce policy constraints
* Orchestrate downstream components
* Control data flow between layers
* Maintain execution trace

**Key Properties:**

* Deterministic
* Stateless per request
* Fully auditable

---

### 5. Policy Engine

**Role:** Access control and compliance enforcement

**Responsibilities:**

* Evaluate RBAC rules
* Evaluate ABAC conditions (time, location, sensitivity)
* Apply compliance constraints (GDPR, DPDP, AML)
* Enforce row-level and field-level security

**Output:**

* Allowed / Denied decision
* Filtered query scope

---

### 6. Tool / Function Layer

**Role:** Controlled data access abstraction

**Responsibilities:**

* Provide strictly defined APIs for data access
* Enforce schema-bound queries
* Prevent arbitrary query execution

**Examples:**

* `getClaimsByEntity(entity_type, filters)`
* `getAggregatedMetrics(params)`

**Constraints:**

* No dynamic query generation
* No direct DB exposure

---

### 7. Claim Engine (Immutable Fact Store)

**Role:** Core data layer

**Responsibilities:**

* Store all data as immutable, versioned claims
* Maintain provenance and lineage
* Enforce tenant isolation

**Claim Structure:**

```id="claim_structure"
{
  "id": "uuid",
  "tenant_id": "uuid",
  "entity_type": "expense",
  "entity_id": "expense_123",
  "claim_type": "amount",
  "value": 7500,
  "timestamp": "ISO8601",
  "version": 3,
  "provenance": "source_system",
  "sensitivity": "confidential",
  "compliance_tags": ["DPDP", "AML"]
}
```

---

### 8. Context Governance Layer

**Role:** Data minimization and sanitization layer

**Responsibilities:**

* Filter claims based on access scope
* Redact sensitive fields
* Aggregate or summarize data
* Enforce compliance constraints
* Prevent inference attacks

**Output:**

* Sanitized, minimal claim payload

---

### 9. SLM Runtime (Sandboxed)

**Role:** Natural language rendering engine

**Environment:**

* Isolated container / microservice
* No network access to internal systems
* No persistent storage
* Stateless execution

**Responsibilities:**

* Convert structured claims → structured output
* Generate explanations and summaries

**Constraints:**

* No decision-making
* No data retrieval
* No tool/function access

**Input:**

* Approved, sanitized claims only

**Output Example:**

```id="slm_output"
{
  "summary": "Total expenses exceed threshold.",
  "details": "Finance department recorded multiple expenses above 5000.",
  "confidence": 0.93
}
```

---

### 10. Output Validation Layer

**Role:** Ensure response integrity

**Responsibilities:**

* Validate output against input claims
* Detect hallucinations or unsupported facts
* Enforce schema compliance
* Reject invalid outputs

---

### 11. Response Renderer

**Role:** Final presentation formatting

**Responsibilities:**

* Convert structured output → UI-ready format
* Apply templates and formatting rules
* Ensure consistency across responses

---

## Data Flow Characteristics

---

### 1. Unidirectional Flow

* Data flows strictly **top → down**
* No backward data propagation from SLM

---

### 2. Stateless Processing

* Each request is independent
* No session memory in SLM or interpreter

---

### 3. Controlled Interfaces

* All interactions occur via **explicit APIs**
* No implicit data sharing

---

### 4. Isolation Boundaries

| Layer         | Isolation Type              |
| ------------- | --------------------------- |
| Data Layer    | Network + logical isolation |
| Policy Engine | Execution isolation         |
| SLM Runtime   | Full sandbox (no trust)     |

---

## Deployment Architecture

---

### Microservices Structure

* API Gateway / Zero Trust Gate
* Interpreter Service
* Compiler Service
* Policy Engine Service
* Tool Layer Services
* Claim Engine (DB + storage)
* Context Governance Service
* SLM Service
* Validation & Rendering Service

---

### Infrastructure Considerations

* Containerized services (Docker/Kubernetes)
* Internal VPC with segmented subnets
* Strict firewall rules between layers
* Horizontal scaling for stateless components

---

## Observability & Audit

---

### Logging

* Every request logged with trace ID
* Full execution path recorded
* SLM input/output logged

---

### Metrics

* Latency (p95, p99)
* Policy evaluation time
* Claim retrieval time
* SLM response time

---

### Audit Guarantees

* 100% traceability
* Immutable logs
* Reproducible execution paths

---

## Failure Handling

---

### Fail-Safe Principles

* Deny by default
* Graceful degradation
* No fallback to unsafe paths

---

### Example Failures

| Failure             | Behavior                 |
| ------------------- | ------------------------ |
| Policy violation    | Request rejected         |
| Claim fetch failure | Partial response or fail |
| SLM failure         | Template-based fallback  |
| Validation failure  | Response rejected        |

---

## Performance Targets

* p95 latency: < 500ms
* Policy evaluation: < 50ms
* Claim retrieval: < 100ms
* SLM inference: < 200ms

---

## Final Statement

ZTA-AI technical architecture is designed as a **strictly layered, deterministic, and isolated system** where:

* All critical operations occur in trusted layers
* All data access is controlled via explicit interfaces
* The SLM operates as a **sandboxed, stateless rendering component**

This ensures **security, compliance, scalability, and operational reliability** in production environments.
