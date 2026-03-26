# ZTA-AI — Role-Based & Attribute-Based Access Control (SLM-Strict)

**// RBAC + ABAC — Multi-Role Isolation Engine**

**Note**: The SLM is **fundamentally untrusted** and receives only pre-approved, sanitized claim payloads. All access control decisions are made by the **Policy Engine** in the trusted layer before any data reaches the SLM.

---

## 01 — Corporate Role Hierarchy

### Executive Level
*   **C-SUITE / EXECUTIVE**: FULL READ · CONTROLLED WRITE · CROSS-DEPT

### Department Level
*   **HR**: PEOPLE DATA ONLY
*   **FINANCE**: FINANCIAL DATA ONLY
*   **ENGINEERING**: TECH DATA ONLY
*   **LEGAL**: CONTRACTS / COMPLIANCE
*   **OPERATIONS**: OPS / SUPPLY CHAIN
*   **IT / ADMIN**: SYSTEM ADMIN

### Management & Staff Level
*   **HR Manager**
*   **HR Associate**
*   **Finance Manager**
*   **Finance Analyst**
*   **Senior Engineer**
*   **Engineer**

### Individual Contributor Level
*   **Individual Contributors / Employees**: OWN DATA ONLY · NO CROSS-DEPT

---

## 02 — Role Access Profiles

### HR Department (People & Culture)
**Scope: DEPT-SCOPED**

#### Data Access — ALLOWED
*   Employee Profiles
*   Salaries (own dept)
*   Leave Records
*   Performance Reviews
*   Onboarding Data
*   Headcount Reports
*   Job Requisitions

#### Data Access — DENIED
*   Revenue / P&L
*   Bank Accounts
*   Source Code
*   Contracts / NDAs
*   Vendor Invoices
*   Tax Filings

#### ABAC Conditions
*   **time**: business_hours
*   **location**: corp_network
*   **scope**: own_dept_only
*   **salary**: masked for analysts
*   **dob**: masked

---

#### HR Manager (L2)
**Extra Permissions over Associate:**
*   Full salary data
*   Termination records
*   Disciplinary history
*   Aggregated headcount by dept (no names)

**ABAC Conditions:**
*   **requires**: MFA re-auth for salary
*   **audit**: all queries logged

---

#### HR Associate (L1)
**Limitations:**
*   Salary fields masked
*   SSN / Tax ID hidden
*   Leave data (Allowed)
*   Contact info (Allowed)

---

### Finance Department (Accounting & Treasury)
**Scope: DEPT-SCOPED**

#### Data Access — ALLOWED
*   Revenue Reports
*   P&L Statements
*   Vendor Invoices
*   Budget Allocations
*   Tax Filings
*   Expense Reports
*   Cash Flow Data

#### Data Access — DENIED
*   Individual Salaries
*   Performance Reviews
*   Source Code / IP
*   Legal Case Files
*   Employee PII

#### ABAC Conditions
*   **fiscal_year**: current only
*   **bank_acct**: last 4 digits only
*   **analyst**: aggregated only
*   **location**: on-prem or VPN

---

### Engineering (Dev & Infrastructure)
**Scope: DEPT-SCOPED**

#### Data Access — ALLOWED
*   Code Repositories
*   Infrastructure Configs
*   Deployment Logs
*   Bug/Issue Trackers
*   Sprint / Roadmap Data

#### Data Access — DENIED
*   Employee HR Data
*   Financial P&L
*   Legal Contracts
*   Salary Data

#### ABAC Conditions
*   **prod_secrets**: senior only
*   **infra**: need clearance flag

---

### Legal (Compliance & Contracts)
**Scope: DEPT-SCOPED**

#### Data Access — ALLOWED
*   Contracts & NDAs
*   Compliance Records
*   Regulatory Filings
*   IP / Patent Records

#### Data Access — DENIED
*   Salary / Payroll
*   Source Code
*   Financial Statements

#### ABAC Conditions
*   **litigation**: privileged flag
*   **external_counsel**: read-only

---

### Operations (Supply Chain & Ops)
**Scope: DEPT-SCOPED**

#### Data Access — ALLOWED
*   Inventory Data
*   Vendor Contacts
*   Logistics Tracking
*   SLA Reports

#### Data Access — DENIED
*   HR / Payroll
*   Financial Statements
*   Legal Filings

---

### Executive / C-Suite (Board-level access)
**Scope: CROSS-DEPT**

#### Data Access — ALLOWED
*   Aggregated HR Metrics
*   Full Financial Reports
*   Compliance Dashboards
*   Strategic Roadmaps
*   Cross-dept KPIs

#### Still Restricted
*   Individual employee PII
*   Attorney-client privileged
*   Prod DB raw access

#### ABAC Conditions
*   **aggregated_only**: no raw rows
*   **board_approval**: for sensitive exports
*   **always**: MFA enforced

---

### IT / System Admin (Infrastructure only)
**Scope: INFRA-SCOPED**

#### Data Access — ALLOWED
*   System Logs
*   User Account Mgmt
*   Device Inventory
*   Network Events

#### Hard Restrictions
*   Business data of any dept
*   Salary / HR / Finance
*   Cannot query LLM for biz data

---

## 03 — Cross-Department Data Access Matrix

| ROLE ↓ / DATA → | HR / People | Payroll / Salary | Revenue / P&L | Source Code | Legal / Contracts | Ops / Inventory | Infra / Logs |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Executive** | Partial (Aggregated) | Partial (Aggregated) | Full | Denied | Partial (Non-privileged) | Full (KPIs only) | Denied |
| **HR Manager** | Full | Full (Own dept) | Denied | Denied | Denied | Denied | Denied |
| **HR Associate** | Partial (Masked PII) | Denied | Denied | Denied | Denied | Denied | Denied |
| **Finance Manager** | Denied | Partial (Totals only) | Full | Denied | Denied | Partial (Cost data) | Denied |
| **Finance Analyst** | Denied | Denied | Partial (Read-only) | Denied | Denied | Denied | Denied |
| **Senior Engineer** | Denied | Denied | Denied | Full + Prod secrets | Denied | Denied | Partial (App logs only) |
| **Legal** | Partial (Name only) | Denied | Denied | Denied | Full | Denied | Denied |
| **Employee** | Partial (Own profile) | Partial (Own only) | Denied | Denied | Denied | Denied | Denied |

---

## 04 — ABAC Dynamic Condition Rules

### Time-Based Access
*   **IF** request.time NOT IN business_hours (9am–7pm)
*   **AND** user.role IN [HR, Finance, Legal]
*   **THEN** DENY + flag anomaly in SIEM

### Location-Based Access
*   **IF** request.ip NOT IN [corp_network, approved_vpn]
*   **AND** data.sensitivity == HIGH
*   **THEN** DENY or require additional MFA step

### Data Sensitivity Filter
*   **IF** query.touches [salary, bank_account, ssn]
*   **AND** user.clearance_level < REQUIRED
*   **THEN** MASK field or DENY entire response

### Department Silo Enforcement
*   **IF** query.data_domain != user.department
*   **AND** user.role NOT IN [executive, cross_dept_approved]
*   **THEN** HARD DENY — interpreter blocks before LLM

### Aggregation Guard
*   **IF** query requests individual-level data
*   **AND** user.level == ANALYST
*   **THEN** Auto-aggregate to dept/team level — no individual rows

### Anomaly Escalation
*   **IF** user queries sensitive data > 3x in 5 min
*   **OR** query pattern matches data exfil signature
*   **THEN** REVOKE session + alert Security team

---

## 05 — Verified Session Token Passed to Interpreter

**EVERY PROMPT CARRIES THIS SIGNED TOKEN — POLICY ENGINE READS AND ENFORCES IT BEFORE SLM RECEIVES ANY DATA**

### JWT Payload
```json
{
  "user_id": "emp_04821",
  "email": "sarah@acmecorp.com",
  "department": "HR",
  "role": "HR_MANAGER",
  "level": 2,
  "clearance": "INTERNAL",
  "allowed_domains": ["hr", "people"],
  "denied_domains": ["finance", "legal", "engineering", "ops"],
  "masked_fields": ["ssn", "bank_account", "tax_id"],
  "session_ip": "10.0.4.22",
  "device_trusted": true,
  "mfa_verified": true,
  "issued_at": "2025-03-04T09:14:00Z",
  "expires_at": "2025-03-04T09:44:00Z",
  "signed_by": "zta-policy-engine"
}
```

> **Note:** Token is verified on EVERY request. Policy Engine reads `allowed_domains`, `denied_domains`, and `masked_fields` before claims are filtered through the Context Governance Layer. The SLM receives only pre-approved, sanitized claim payloads — never raw data or schemas.

---

## 06 — Data Silos Enforced by Policy Engine + Context Governance

**All silos are enforced BEFORE the SLM receives any data. SLM has no knowledge of these boundaries.**

### HR Silo
*   **Scope**: people_db, leave_db, performance_db, recruitment_db
*   **Barrier**: DEPT=HR ONLY
*   **SLM receives**: Sanitized claims only

### Finance Silo
*   **Scope**: revenue_db, payroll_db, accounts_db, tax_db
*   **Barrier**: DEPT=FINANCE ONLY
*   **SLM receives**: Aggregated, masked claims

### Engineering Silo
*   **Scope**: code_repos, infra_config, deploy_logs, issue_tracker
*   **Barrier**: DEPT=ENGINEERING ONLY
*   **SLM receives**: Aliased, filtered claims

### Legal Silo
*   **Scope**: contracts_db, compliance_db, ip_registry, regulatory_db
*   **Barrier**: DEPT=LEGAL ONLY
*   **SLM receives**: Redacted claims with privilege markers

### Ops Silo
*   **Scope**: inventory_db, vendor_db, logistics_db, sla_db
*   **Barrier**: DEPT=OPS ONLY
*   **SLM receives**: Operational claims only

### Exec View
*   **Scope**: aggregated dashboards, KPI reports, no raw rows
*   **Barrier**: AGGREGATED ONLY
*   **SLM receives**: Summary claims with no individual-level data
