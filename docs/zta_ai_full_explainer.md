# ZTA-AI — Complete Explainer (SLM-Strict)

**Plan Alignment:** This explainer is aligned to `ZTA_AI_FINAL_PRODUCT_PRODUCTION_PLAN.md` (v3.0, April 11, 2026). The plan file is authoritative for production scope and phase outcomes. See `docs/PLAN_ALIGNMENT.md`.

**Secure Enterprise AI Platform with Zero Trust Data Isolation**

---

## 01 — The Core Idea: The AI is Kept Blind and Sandboxed

Most companies are hesitant to use internal AI because an assistant connected to a database could accidentally expose sensitive information. ZTA-AI solves this by keeping the Small Language Model (SLM) **completely isolated from raw data** and treating it as **fundamentally untrusted**.

### The SLM MUST NEVER:
* Access databases (directly or indirectly)
* See raw company data or schemas
* Decide what data to retrieve
* Execute business logic or computations
* Call tools, APIs, or functions
* Maintain memory or state across requests

### The Request Lifecycle
1.  **Employee types a question**: e.g., "What is our current NPL ratio by branch?"
2.  **Zero Trust Gate**: Every request re-verifies identity, role, device posture, and applies RBAC+ABAC.
3.  **Interpreter**: Deterministic intent parsing — converts natural language to structured intent. No SLM usage. Replaces real names with aliases.
4.  **Compiler (Control Plane)**: Central authority — creates execution plan, enforces policies, orchestrates downstream components.
5.  **Policy Engine**: Evaluates RBAC/ABAC rules, applies compliance constraints (GDPR, DPDP, AML).
6.  **Tool / Function Layer**: Controlled data access via strictly defined APIs — no dynamic queries.
7.  **Claim Engine**: Retrieves immutable, versioned claims with provenance and compliance tags.
8.  **Context Governance**: Filters, redacts, and minimizes claims based on access scope. Prevents inference attacks.
9.  **SLM Runtime (Sandboxed)**: Receives ONLY pre-approved, sanitized claims. Converts structured data → structured JSON output.
10. **Output Validation**: Validates output against input claims, detects hallucinations, enforces schema compliance.
11. **Response Renderer**: Formats for UI delivery.
12. **Employee receives response**: A clean, structured response with a full, tamper-proof audit trail.

---

## 02 — RBAC / ABAC: Access Control

Every query is attached to a signed JWT token ("digital badge") that defines exactly what data the user can access. **All access control is enforced BEFORE the SLM receives any data.**

### Role-Based Access Control (RBAC)
*   **HR Manager**: Access to salaries, leave, and performance. No access to revenue or source code.
*   **Finance Analyst**: Access to revenue and P&L. No access to individual salaries or legal files.
*   **Senior Engineer**: Access to code repos and logs. No access to HR or financial data.
*   **C-Suite**: Access to aggregated cross-dept KPIs. No access to individual PII or raw DB.

### Attribute-Based Access Control (ABAC)
*   **Time**: Access for certain roles is blocked outside of business hours (9 am – 7 pm).
*   **Location**: Sensitive data access requires a corporate network or VPN.
*   **Sensitivity**: Fields like SSN or bank accounts are always masked for analyst roles.
*   **Anomaly**: Rapid querying of sensitive data triggers automatic session revocation.

**The SLM receives only sanitized claims that have already passed through the Policy Engine and Context Governance Layer.**

---

## 03 — Data Integration

ZTA-AI connects to virtually any enterprise data source through three main paths:
1.  **No-code UI**: A dashboard wizard for non-technical admins.
2.  **SDK / API**: Full control for developers (Python, Node, Java).
3.  **On-prem Agent**: A Docker container for air-gapped or highly regulated environments.

### Supported Sources
*   **Databases**: PostgreSQL, MySQL, MSSQL, Oracle, Snowflake, MongoDB.
*   **Cloud Storage**: AWS S3, Google Cloud, Azure Blob, BigQuery.
*   **SaaS Tools**: Slack, Jira, Salesforce, SAP, Microsoft 365, Google Workspace.
*   **Files**: PDF, Excel/CSV, Word, JSON/XML.

### Data Flow (Claim-Based Architecture)
All data is converted to **immutable, versioned claims** with provenance, sensitivity classification, and compliance tags. The SLM never sees raw data — only pre-approved, sanitized claims filtered by the Context Governance Layer.

---

## 04 — Market Scope & Opportunity

ZTA-AI addresses a $133B combined market of Conversational AI and Zero Trust Security.

### Target Verticals
1.  **BFSI**: Banks and fintechs (Highest priority due to RBI/SEBI compliance). Sandboxed SLM addresses data leak fears.
2.  **Healthcare**: HIPAA-compliant patient/billing data isolation. Output validation prevents hallucinated medical info.
3.  **Government**: NSA Zero Trust mandates and on-prem requirements. Deterministic architecture for auditability.
4.  **Legal**: Attorney-client privilege and matter-level silos. SLM has no memory across requests.

### Pricing Model
*   **Starter ($199/mo)**: Up to 50 users, 2 sources.
*   **Business ($999/mo)**: Up to 500 users, 10 sources, full RBAC/ABAC.
*   **Enterprise (Custom)**: Unlimited users, on-prem deployment, SLAs.

---

## 05 — BFSI Strategy: Starting with Banking

Banks have the highest willingness to pay and the strictest regulatory requirements (RBI FREE-AI 2025, DPDP Act 2023). ZTA-AI's **sandboxed SLM with no tool/function access** directly addresses their concerns about AI data leakage.

### Internal Use Cases
*   **Risk Analyst**: Querying NPL ratios across branches — SLM receives pre-approved claims only.
*   **Compliance Officer**: Detecting AML threshold breaches — SLM outputs validated against input claims.
*   **Treasury Desk**: Monitoring ALM gaps and SLR/CRR concerns — SLM has no access to raw treasury data.

### Sales Strategy
The pitch focuses on **SLM sandboxing** (no tools, no memory, no decisions), **deterministic architecture** with full audit trails, and guaranteed compliance. The roadmap targets NBFCs and fintechs first, moving upstream to private and public banks.

---

## 06 — Key Differentiator

ZTA-AI does not treat AI as a system authority.

> **AI is not part of the trust boundary.**
> **AI is a stateless, sandboxed rendering layer over a deterministic system.**

The SLM:
* Has no tool or function access
* Has no memory or state across requests
* Receives only pre-approved, structured claims
* Outputs structured JSON validated against input claims
* Runs in an isolated container with no network access to internal systems

This architecture ensures **enterprise-grade security, regulatory compliance, and production reliability** without relying on AI for critical system behavior.
