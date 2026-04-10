# ZTA-AI Final Product Production Plan
## The Authoritative Single Source of Truth

---

**Document Version:** 3.0 (Complete - Production Ready)  
**Status:** ✓ Ready for Phase 1 Execution  
**Last Updated:** April 11, 2026  
**Owner:** Product & Engineering Leadership  

**What This Document Is:**
- The single source of truth for ZTA-AI's production-grade product specification
- Executable by engineering teams across all functions (backend, frontend, infrastructure, operations)
- **Complete in scope:** All product pillars defined (backend, frontend, deployment, compliance, operations, security)
- **Gated for Phase 1:** Outstanding work items correctly placed as Phase 1 Architecture Freeze deliverables

**What Has Been Specified (v3 - Complete):**
- ✓ Backend architecture (all 6 layers: experience, interpretation, policy, execution, compliance, reliability)
- ✓ Frontend and mobile UX (home screen, query input, results, offline mode, workspace routing)
- ✓ Deployment architecture (cloud SaaS topology, on-prem topology, artifact structure)
- ✓ Multi-tenant routing (workspace code → pod selection, on-prem association)
- ✓ Compliance operations (DSAR, erasure, breach investigation, audit evidence)
- ✓ System admin console (fleet health, per-customer deep dive, churn prediction, cost optimization)
- ✓ Action registry structure (rigorous JSON schema, DSAR example, all 12 templates listed)
- ✓ Connector plugin interface (8 required methods, implementation requirements, error codes)
- ✓ LLM strategy (multi-mode: cloud SaaS + local on-prem, air-gapped download)
- ✓ Performance targets and optimization path (5200ms baseline → 1000ms target)
- ✓ Security threat model (3 major threats with mitigations and residual risk)
- ✓ Operational readiness (deployment, monitoring, runbooks, incident response)

**What Remains (Phase 1 Architecture Freeze Work):**
- 11 additional action template schemas (follow DSAR_EXECUTE pattern)
- Connector plugin interface implementation guide
- Frontend engineering spec as companion document

**Recommendation for Phase 1:**
- Start architecture work immediately from this specification
- Use the explicitly marked [CRITICAL] deliverables in Phase 1 as gating criteria
- Ensure action registry schemas and connector interface are completed before Phase 4 proceeds
- Frontend engineering spec can be created in parallel with front-end team onboarding

---

## Document Purpose

This document is the **single source of truth** for ZTA-AI's final production-grade product.

It defines what ZTA-AI must do, how it works, what it controls, and how success is measured.

- **No feature cuts. No compromises. No scope reduction.**
- **Domain-agnostic.** Applicable to any regulated enterprise (banking, healthcare, insurance, manufacturing, professional services).
- **Fully detailed.** Every feature explained with concrete examples. Every use case illustrated. Every architecture component clarified.
- **Implementation-focused.** Phase gates, acceptance criteria, risk mitigation, quality gates—ready for execution.

This plan unifies Product, Engineering, Security, Compliance, Legal, and Operations to one reference document.

---

## Executive Vision

**ZTA-AI** is a compliance-first, zero-trust, agentic enterprise data assistant that:

- **Runs on customer infrastructure** (on-prem, private cloud, customer-managed accounts)
- **Enables natural language data access** with policy-safe automatic scoping
- **Automates business workflows** with deterministic, reversible, fully auditable actions
- **Never learns from or exfiltrates customer data** (zero-learning guarantee)
- **Enforces policy at every layer:** role-based (RBAC), attribute-based (ABAC), row-level (RLS), field-level (FLS), time-based, risk-based
- **Is production-ready for compliance** with HIPAA, GDPR, DPDP from Day 1
- **Provides complete forensic auditability** for every query, action, and policy decision

## Non-Negotiable Product Guarantees

1. **Data Custody:** Customer data remains physically and logically under customer control at all times
2. **Zero Learning:** Model inference never uses customer data for training, fine-tuning, or learning
3. **Policy Scoping:** Every result proves its authorization through detailed scope and access rationale
4. **On-Premise First:** Core functionality operates unchanged on customer infrastructure without external dependencies
5. **Compliance Native:** HIPAA, GDPR, DPDP controls are Day 1 capabilities, not add-ons
6. **Deterministic Automation:** Workflows are bounded by policy, fully auditable, reversible/rollback-capable
7. **Production SLAs:** Latency, reliability, and observability meet enterprise standards from launch

---

## Current MVP Reality

The MVP is an excellent proof-of-concept but is **not production-ready:**

1. **Incomplete connectors** — SQL works; ERP, Sheets, Warehouse, Analytics connectors are stubs (raise `SOURCE_CONNECTOR_NOT_ENABLED`)
2. **Hardcoded domain logic** — Intent extraction, persona mapping, field classification are baked for one specific domain; generalization layer missing
3. **Placeholder templates** — 12 baseline action templates defined but not operationalized; no workflow orchestrator, no trigger engine
4. **Mock authentication** — OAuth with trust-on-first-use; no SAML, OIDC, MFA, service mTLS
5. **Performance gap** — ~5000ms baseline latency (1.8s model, 1s schema queries, 260ms interpreter); target <1000ms P95
6. **Incomplete compliance** — Audit logging works; DSAR, erasure, consent, retention workflows missing
7. **Missing admin surfaces** — No tenant or system admin consoles; governance requires engineering

**This plan closes every gap.**

---

## Domain-Agnostic Product Definition

ZTA-AI serves **any regulated organization with policy-governed data and workflows.**

### What ZTA-AI Is
- A policy-governed semantic query and execution engine
- A conversational interface to enterprise data with automatic scope enforcement
- A workflow automation platform with deterministic, reversible, auditable actions
- A compliance operations product (DSAR, erasure, breach, audit evidence)

### What ZTA-AI Is NOT
- A generic AI chatbot with SQL backend
- A model training pipeline fed by customer records
- A system whose policies can be bypassed by prompt phrasing
- Cloud-hosted SaaS for customer data
- A replacement for specialized software (ERP, HCM, CRM)

---

## Personas: Domain-Agnostic but Concrete

ZTA-AI serves diverse personas across organizations. These are **generic by design** but illustrated across **banking, healthcare, manufacturing, insurance, and professional services.**

### End User Persona: Data Analyst / Operational Analyst

**Profile:**
- Needs business questions answered using structured data
- Understands data concepts but may lack SQL knowledge
- Works across multiple systems (ERP, data warehouse, business apps)
- Creates reports, dashboards, exports

**Banking Example:**
A commercial loan analyst asks: *"Show me all commercial loan applications from the automotive sector in Q4 2024 where the applicant has been a customer for less than 2 years, and give me their credit score distribution and default rate benchmarks."*

**ZTA-AI Processing:**
1. **Intent:** `FILTERED_AGGREGATION(Loan Applications, filter={sector:"automotive", date_range:"Q4_2024", tenure:"<2yrs"}, metrics={credit_score_distribution, default_rates})`
2. **Scope validation:** Checks role allows commercial loan analyst access (not consumer loans)
3. **Policy enforcement:** Commercial analyst cannot see pricing terms (confidential)
4. **Query compilation:** Optimal SQL across loan_applications, applicant_profiles, credit_bureau with necessary joins
5. **Result:** 47 defaulted applications, $340M exposure, credit score distribution (Excellent 15%, Good 28%, Fair 45%, Poor 12%), default rate 3.2%
6. **Explainability:** "See this because: (1) Commercial Loan Analyst role, (2) Automotive portfolio authority, (3) No PII in result (only aggregated, de-identified metrics)"

**Healthcare Example:**
A hospital operations analyst asks: *"Which clinical departments have the highest variance in average patient wait times between morning and evening appointments in February 2026?"*

**ZTA-AI Processing:**
1. **Intent:** `AGGREGATION(Appointments, group_by:department, calculation:variance(wait_time), partition:time_of_day, filter:{month:Feb2026})`
2. **Policy:** Operations analyst role, no access to primary diagnosis or patient identifiers
3. **Query:** Group by department, filter date range, calculate variance across AM/PM cohorts
4. **Result:** ED has 45-minute AM variance vs. 18-minute PM variance (staffing pattern); Oncology consistent
5. **Explanation:** This is aggregated wait time data, no patient details visible per your operational role

**Manufacturing Example:**
A supply chain analyst asks: *"Which suppliers have we been paying late (beyond 45 days) in the last quarter, and what impact on component stock levels?"*

**ZTA-AI Processing:**
1. **Intent:** `CORRELATE(Payments {late_days:>45}, Inventory_Impact, date_range:Q4_2025, calculate:stock_variance)`
2. **Policy:** Supply chain analyst, can see supplier payment terms and inventory; cannot see supplier bank details or negotiated pricing
3. **Query:** Late AP transactions, supplier master, inventory variance, with temporal correlation
4. **Result:** 8 suppliers with late payments >45 days; 4 caused inventory shortages (stock-out incidents); avg $340K impact per late-paying supplier
5. **Explanation:** Sourced from AP and Inventory systems, you have analyst access to these domains

---

### End User Persona: Knowledge Worker / Operational User

**Profile:**
- Performs everyday business tasks (approvals, status checks, next actions)
- Needs quick answers to routine questions
- Requests automations to reduce manual work
- Limited technical knowledge

**Professional Services Example:**
A project manager asks: *"What's the status of the Client X engagement? Who's assigned, utilization vs. planned, what's due this sprint?"*

**ZTA-AI Provides:**
```
CLIENT X PROJECT STATUS

Status: 81% Complete
Team (3 assigned):
  • Sarah: Senior Consultant, 92% utilization (vs. 90% plan) ✓
  • Marcus: Consultant, 78% utilization (vs. 85% plan) ⚠️ Under-utilized
  • Intern: Junior, 45% utilization (vs. 40% plan) ✓

Upcoming Sprint (Next 2 weeks):
  • Deliverable A: Due 3/12 (Assigned: Sarah) - On track
  • Deliverable B: Due 3/15 (Assigned: Marcus) - At risk (85% complete, time 87% consumed)
  • Deliverable C: Due 3/18 (Assigned: Intern) - On track

Proactive Flags:
  • Marcus is below utilization; recommend task rebalancing
  • Deliverable B may slip; suggest daily standups with Marcus
  • Billable hours trending $45K (95% of estimated budget)

Available Actions:
  [✓] Adjust Marcus's task load  [✓] Send team status email  [✓] Create risk log entry  [✓] Request budget increase
```

**Insurance Example:**
A claims processor asks: *"Show me all open claims assigned to me where the claimant hasn't responded to our last request for 20+ days."*

**ZTA-AI Provides:**
```
STALE CLAIMS REQUIRING ACTION

Total claims with no response >20 days: 12

🔴 URGENT (2 claims - escalate immediately):
  • Claim #CLM-20872: Medical emergency vehicle claim, $245K exposure, claimant silent 28 days
    Last request: Medical opinion from orthopedist, vital for settlement
    Recommended action: Call claimant + send certified notice (reserve expiry approaching)
    
  • Claim #CLM-20891: Large loss specialty property claim, $3.2M exposure, broker silent 32 days
    Last request: Replacement cost estimate from insured
    Recommended action: Call broker + contact policyholder directly

🟡 MODERATE (6 claims):
  • Claim #CLM-20877, #CLM-20888, etc. [Listed with follow-up actions]

🟢 LOW PRIORITY (4 claims):
  • [Listed with routine follow-up timing]

One-Click Actions:
  [Send escalation notices] [Schedule phone calls] [File penalties] [Create follow-up tasks] [Mark for manager review]
```

**Retail Example:**
A store manager asks: *"Which SKUs from dairy section didn't hit forecast this week? Markdown suggestions?"*

**ZTA-AI Provides:**
```
DAIRY UNDERPERFORMANCE ANALYSIS

Products missing forecast (Week ending 3/8/2026):

SKU: Yogurt Variety Pack (Product #YOGI-24OZ)
  • Forecasted: 240 units | Actual: 198 units | Variance: -17.5% (-42 units)
  • Overstock: 180 units in inventory
  • Markdown suggestion: 12% reduction (based on price elasticity model)
  • Action: [Approve Markdown] - Projected recovery rate 82% based on historical patterns

SKU: Greek Yogurt Single (Product #GYOG-5.3OZ)
  • Forecasted: 180 units | Actual: 205 units | Variance: +13.9% (performing well ✓)

SKU: Kefir (Product #KEF-16OZ)
  • Forecasted: 90 units | Actual: 54 units | Variance: -40% (significant miss)
  • Suggestion: Different issue—out of stock 2-3 days during week
  • Action: [Increase order quantity for next week]

Summary:
• 3 products underperforming (all dairy category)
• 1 out-of-stock issue (replenishment problem, not demand issue)
• Estimated impact: $1,850 lost revenue if not corrected
• Recommended actions: 1 markdown + 1 reorder adjustment
```

---

### Administrative Persona: Tenant Administrator  

**Profile:**
- Responsible for data security, policy enforcement, user provisioning
- Manages roles, access policies, field masking, sensitive data controls
- Controls data source connectors and credentials
- Owns compliance operations (DSAR, audit reports, policy changes)

**Healthcare Scenario:** Hospital CIO sets up ZTA-AI for 2,000-person organization

**User Provisioning:** Defines roles (Doctor, Nurse, Admin, Billing, Research) with permission matrices
- Doctors can see full patient records for assigned patients (all fields)
- Nurses see clinical fields only (no billing/financial responsibility)
- Billing see financial fields only (no clinical details)
- Research accesses de-identified cohort data only

**Policy Configuration:**
```
Role: Clinical_Provider (Doctor)
Scope:
  • Patients: Assigned patients (from schedule/clinic assignment)
  • Fields: All clinical data (diagnosis, medications, lab results, imaging)
  • Cannot see: Financial responsibility, insurance details, payment history
  • Row-level: WHERE department=user.assigned_dept AND provider_id=user.id
  • Time-based: Normal business hours + on-call escalations (logged)

Audit:
  • All PHI access logged (regulatory requirement)
  • Break-glass access (emergency override) requires justification and post-access review
  • Retention: 6 years (HIPAA requirement)
```

**Connector Setup:** Connects EHR (Epic), Accounting (SAP), Lab (Cerner), Pharmacy (McKesson)
- Tests connectivity, verifies schema mapping, confirms field metadata
- Configures auto-refresh (hourly) and schema change detection
- Sets up credentials in tenant vault (never exposed, auto-rotated)

**Compliance Settings:**
- Enables HIPAA mode (requires MFA, logs all PHI access, enables BAA terms)
- Configures retention: PHI audit logs retained 6 years (regulatory)
- Maps fields to PHI classification: Patient name = BareMinimum → Masked; SSN = Protected → Cannot export

---

### Administrative Persona: Compliance and Security Officer

**Profile:**
- Ensures ZTA-AI operates within legal and security boundaries
- Manages DSAR execution, erasure workflows, breach response, audit evidence
- Proves compliance to regulators and auditors
- Responds to privacy incidents

**Healthcare Scenario: HIPAA Compliance Officer**

**Daily Operations:**
- Runs automated report: "All BAA-required PHI access (last 7 days)" with requestor, scope, justification
- Reviews unusual access patterns (e.g., doctor accessing 500+ patient records in one query) and approves or blocks
- Receives alerts from policy enforcement system (blocked access attempts, policy violations)

**Incident Response Example:**
```
BREACH INVESTIGATION SCENARIO
Initial alert: Unauthorized attempt to export all patient SSNs on 3/15/2026

Investigation initiated: Compliance Officer requests forensic export
  "All database access logs (3/10-3/15) with user, query, results count, policy decisions"

ZTA-AI generates tamper-proof forensic report:
  Timestamp: 3/15 14:22
  User: John Doe (IT Staff)
  Query: SELECT patient_id, ssn FROM patient_master
  Policy decision: BLOCKED (John Doe is ITStaff, not authorized for patient data export)
  Rationale: SSN field marked PHI - FieldLevel restriction applied
  Audit log: Query blocked, policy rule [RLS-PatientData], no data returned

Executive Summary:
  ✓ No patient records were actually exported (policy enforcement worked)
  ✓ Access denial was automatic and logged
  ✓ No data exfiltration occurred
  
Compliance Officer's conclusion:
  "This attempted breach was prevented by policy controls. No breach notification required.
   Recommend: Review John Doe's access permissions (should not have patient scope);
   disable his access, log the incident, and notify IT leadership."
```

**DSAR Execution Example:**
```
DSAR Request Intake:
Request ID: DSAR_2026_0347
Subject: Mr. John Smith (Patient since 2020)
Request: "Send me all records you hold about me"
Legal deadline: 30 calendar days (GDPR requirement)

ZTA-AI Automated Processing:
  Step 1: Identify - Query all systems where John Smith records exist
    • EHR system: 145 clinical visit records
    • Billing system: 8 invoices, 4 payment records
    • Lab system: 32 lab result records
    • Pharmacy: 18 prescription/medication records
    • Analytics: Inferred preferences (website behavior tracking, app usage)
    Total: 207 records across 5 systems

  Step 2: Aggregate - Collect into staging area, organize by system

  Step 3: Redact - Remove records mentioning OTHER patients that reference John Smith

  Step 4: Organize - Structure human-readable format
    {
      "medical_records": [145 visits with dates, diagnoses, treatments],
      "billing": [8 invoices with amounts, dates],
      "lab_results": [32 results with test names, values, dates],
      "prescriptions": [18 prescriptions with drug names, dosages],
      "analytics": [behavioral data: 1,247 website visits, 340 app sessions]
    }

  Step 5: Deliver - Export encrypted file, deliver via secure portal

  Step 6: Document - Complete audit trail
    Request received: 3/1/2026
    Processing completed: 3/8/2026 (7 days, well within 30-day deadline)
    Delivered: 3/8/2026 via secure portal
    Proof: Signed receipt, access logs

Verification: Mr. Smith downloaded export 3/8 at 10:15am
Compliance record: DSAR_2026_0347 - COMPLETE, documented
```

---

## Use Cases by Domain: Detailed Walkthroughs

### Banking: Loan Portfolio Risk Management

**Setup:** Commercial bank, $50B portfolio, 200 credit analysts, systems: LOS, Credit scoring DB, LADS
**Configured for:** SQL connectors, schemas mapped (loans, obligor_profiles, guarantors, collateral, payments)

**Use Case 1: Stress Testing for CCAR Submission**

Risk officer asks:
```
"Show me our commercial real estate (CRE) portfolio distribution by property type, 
occupancy, LTV, and interest rate sensitivity. 
Impact of +200bp rate shock and -10% property value shock?"
```

**ZTA-AI Execution:**
1. Intent: PORTFOLIO_STRESS_TEST with multi-dimensional analysis
2. Scope check: Risk Manager role, CRE portfolio authorized
3. Compiles SQL: GROUP BY property_type, SUM(exposure), AVG(ltv), duration analysis
4. Returns:
   ```
   CRE Portfolio: $8.2B (16.4% of total)
   
   By Property Type:
   • Office: $2.1B (26%), avg LTV 62%, avg occupancy 78%
   • Retail: $1.8B (22%), avg LTV 58%, avg occupancy 82%
   • Industrial: $2.4B (29%), avg LTV 55%, avg occupancy 94%
   • Specialty: $1.9B (23%), avg LTV 65%, avg occupancy 71%
   
   Rate Sensitivity: $3.2B floating rate (39%)
   +200bp shock: Est. +$12.8M annual income (but rate-reset risk for obligors)
   
   Stress Scenario (+200bp, -10% property values):
   • LTVs increase ~5%
   • Loans >85% LTV: +47 loans ($580M)
   • Estimated additional loss: ~$28M
   
   Policy validation: ✓ You can see this (Risk Manager, portfolio-level aggregation)
   ```

**Use Case 2: Early Warning System—Delinquency Detection**

Analyst asks:
```
"Which obligors have deteriorated credit indicators in last 30 days? 
Show credit score drops, missed payments, covenant violations, industry downgrades."
```

**Result:**
```
EARLY WARNING ALERTS (30-day window)

CRITICAL (7 obligors—immediate action required):
  • BigBox Retail Chain: Moody's downgrade Baa1→Ba1, $45M exposure
  • Hospitality Corp: 2 missed payments, 60 DPD status, $12M

HIGH (19 obligors—credit committee review):
  • Manufacturing recession cohort: PMI <48, 12 firms affected
  • Regional bank peer exposure: 5 firms, $234M aggregate

MEDIUM (34 obligors—quarterly monitoring):
  • Credit score drops 20-50 points
  • Covenant headroom narrowed

Recommended actions:
  • 7 critical: Obligor contact, assess restructuring options
  • 19 high: Weekly credit committee review
  • 34 medium: Quarterly review cycle

This data is sourced from LOS (payment), Credit Bureau (scores), Covenant tracking system.
You have analyst access to all these systems.
```

**Use Case 3: Loan Modification Workflow with Approvals**

Deal team asks:
```
"Modify Acme Corp $200M facility: extend maturity +3yr, reduce rate 50bp, loosen covenants.
Show approval requirements and risk impacts."
```

**ZTA-AI Triggers Workflow:**
```
MODIFICATION REQUEST SUMMARY

Facility: Acme Corp $200M Revolver + Term
Changes: +3yr maturity, -50bp rate, 2.5x→3.0x leverage covenant
Risk impact: KD Rank 12→18 (higher risk category)
NPV impact: +$8.4M (favorable)

REQUIRED APPROVALS:
  ☐ Credit Risk Approver (VP level) - PENDING
  ☐ Treasury (rate/liquidity) - PENDING
  ☐ Compliance - NOT REQUIRED (rate cut improves credit)

Once approved, system automatically:
  1. Generates updated legal documents
  2. Runs covenant audit
  3. Updates loan accounting system
  4. Logs to audit trail (compliance record)
  5. Notifies obligor and legal counsel
```

Upon VP approval, workflow executes automatically with full audit trail documented.

---

### Healthcare: Patient Care and Compliance

**Setup:** 5 hospitals, 200+ clinics, EHR (Epic), Lab, Pharmacy, Billing, HR

**Use Case 1: Patient Safety—Sepsis Risk Alert**

Nurse at bedside asks: *"Sepsis warning signs for my assigned patients? Fever + elevated WBC + low BP or high lactate?"*

**Real-time Response:**
```
SEPSIS ALERT SUMMARY

🔴 CRITICAL RISK (1 patient):
  Robert M. (Room 412A)
  • Vitals: T=103.2°F, HR=128, BP=88/52, RR=24
  • Labs: WBC=18.2↑, Lactate=4.1↑, Creatinine=1.9↑
  • qSOFA: 3/3 (HIGH RISK)
  • Recommendation: PAGE PHYSICIAN NOW; initiate sepsis protocol
  • Action: Alert escalated to attending + charge nurse

🟡 ELEVATED RISK (3 patients):
  • Maria G. (Room 410): T=101.8, WBC=15.1, BP=92/60
  • James K. (Room 415): T=100.4, WBC=13.2, Lactate=2.8

🟢 LOW RISK (8 patients): Normal

Confidence: HIGH for current vitals; labs max 1hr old
```

**Use Case 2: Readmission Risk Assessment**

Care coordinator asks: *"Discharged patients (last 30 days) at highest 6-month readmission risk? Show risk factors, post-discharge meds, appointments."*

**Response:**
```
HIGH READMISSION RISK COHORT (Predicted 6-mo readmission >40%):

Rank 1: Ruth W. (Discharged 3/5/2026)
  • Condition: COPD exacerbation
  • Risk: 68% predicted readmission
  • Contributing: Age 78, multiple comorbidities, adherence concerns
  • Post-discharge: Prednisone (compliance risk), Albuterol inhaler
  • Follow-up: PCP scheduled 3/19 ✓
  • Interventions: (1) Daily home health week 1 (2) Auto drug refill (3) Telephonic case management 3/10
  • Status: [Ready for approval]

Rank 2: George M. (Discharged 3/8/2026)
  • Condition: CHF acute decompensation
  • Risk: 52% predicted readmission
  • Problem: EF 32%, no PCP scheduled (risk!)
  • Action: [Expedite PCP to <7 days] [Home health for daily weights/vitals]

[12 more high-risk cases]

Opportunity: Implementing interventions could prevent ~6 readmissions (save ~$180K)
```

**Use Case 3: Compliance—Unauthorized Access Investigation**

Privacy Officer asks: *"Surgical tech accessed patient records not on her schedule. What did she see? Was it justified? Policy violations?"*

**Forensic Report:**
```
UNAUTHORIZED ACCESS INVESTIGATION

User: Sarah C. (Surgical Tech, OR-West)
Date/Time: March 12, 2026, 14:47
Patient: Michael T. (MRN XXXX5678)

Access Details:
  • Full clinical record: ALL fields accessed
  • Imaging reports: 4 CTs reviewed
  • Pathology reports: 3 reviewed

Claim: "Colleague asked for care plan info"
Actual requirement: Sarah NOT scheduled for this patient

Policy Evaluation:
  ❌ Policy Violation: Full clinical record access without assignment
  ⚠️ Mitigating: Surgical staff have some patient-access permissions
  ❌ But: Scope excessive (imaging/pathology not needed for "care plan")

Risk: LOW-MEDIUM
  • No data export detected
  • Isolated incident (not recurring pattern)
  • Patient not VIP/celebrity/litigation-involved

Recommended actions:
  1. IMMEDIATE: Interview Sarah, document justification
  2. REVIEW: Check if she accessed other non-assigned patients that day
  3. EDUCATION: Retraining on minimum-necessary principle
  4. MONITOR: Extra oversight for Sarah's access next 30 days

Audit trail: All details logged, BAA-compliant, ready for breach assessment
```

---

### Financial Services: Anti-Money Laundering (AML) and Sanctions

**Setup:** Large institution, millions of customers, compliance requirements: FinCEN, OFAC, BSA/AML

**Use Case 1: Suspicious Activity Pattern Detection**

AML Analyst asks:
```
"Show customers receiving wire transfers >$100K from high-risk jurisdictions (FATF grey),
3+ transfers in same period"
```

**Response:**
```
SUSPICIOUS ACTIVITY ALERTS

🔴 TIER 1 - IMMEDIATE ESCALATION (5 customers):

ABC Import Corp (ID: 12847)
  • 4 wire transfers from Pakistan (grey-list): $480K total
  • From 4 different entities (shell company risk)
  • Rapid consolidation pattern
  • Historical: No prior Pakistani counterparty relationship
  • Risk assessment: NEW_COUNTERPARTY + GREY_JURISDICTION + CONSOLIDATION = SUSPICIOUS
  • Action: FREEZE pending SAR filing; contact customer for justification
  • SAR draft: Prepared, awaiting Compliance Officer approval

XYZ Trading (ID: 24891)
  • 3 transfers from Egypt: $185K total
  • Relationship: Legitimate, historical pattern consistent
  • Risk: Elevated but known business model
  • Action: MONITOR (not escalate); flag quarterly review

[Additional cases...]

Summary:
  • Flagged: 5 Tier 1 + 12 Tier 2 + 34 Tier 3
  • Est. SAR filings: 3-5 cases
  • Next: Escalate Tier 1 to Compliance Officer
```

**Use Case 2: OFAC Sanctions Screening**

Loan Officer initiates: *"$50M export finance deal with Turkish company. Check OFAC lists."*

**Automated Screening:**
```
OFAC COMPLIANCE CHECK

Customer: TurkeyTrade Corp (Istanbul Trading and Import Export Ltd.)
Beneficial Owners: Mehmet Aydin (75%), Fatima Aydin (25%)

Match Results:
  ✓ TurkeyTrade Corp: NO MATCH to SDN/CSL lists
  ✓ Mehmet Aydin: NO MATCH
  ✓ Fatima Aydin: NO MATCH
  ⚠️ Note: "Istanbul Trading Ltd" (partial name) has 1 potential CSL match
          (Iranian company), but different legal structure—NOT the same entity

Transaction History:
  • 12 prior transfers (all <$5M each)
  • No prior OFAC flags
  • No transactions to OFAC-sanctioned jurisdictions

✓ COMPLIANCE CLEARANCE APPROVED

Evidence: This screening logged for regulatory proof of due diligence
```

---

## Features: Complete Reference

### Tier 1: End User Interactive Features

#### Feature 1.1: Conversational Natural Language Query Interface

User asks: *"Show me sales by region for Q4 last year"*

**Processing Chain:**
1. Intent: QUERY_AGGREGATION(sales, region, Q4_2025)
2. Scope: Verify role has regional sales access
3. Compile: SQL to aggregate revenue by region
4. Return: Table with visualization
5. Explain: "See this because: (1) Sales Analyst role (2) No customer masking applied (3) Regional aggregation only"

**Banking example:** *"Which loans originated in Boston office in 2024 have defaulted?"*
→ Returns: 47 defaulted loans, $340M exposure, 3.2% default rate, with scope proof

**Healthcare example:** *"Open pain complaints from my patients yesterday?"*
→ Returns: 3 patients sorted by severity, one flagged for immediate follow-up

**Manufacturing example:** *"Are we ahead of production targets this month?"*
→ Returns: 3,420 units produced vs. 3,200 target (106%), broken down by product line

---

#### Feature 1.2: Multi-Turn Context-Aware Clarification

User queries loop without re-stating context:

```
User: "Show me customer churn this year"
→ Result: 1,240 customers churned (4.2 churn rate), by product line and region

User: "Focus on high-value ones only" (system remembers prior query)
→ System filters: churn_customers AND ARR>$50K
→ Result: 180 high-value customers churned, $18M lost

User: "Which ones still under contract?" (system contextualizes)
→ Result: 47 customers, potential recovery opportunity

User: "What was main reason they left?"
→ Result: 34 cited competitor, 11 cited cost, 2 cited gaps

User: "Can we reach out to the cost-sensitive ones?" (trigger action)
→ System creates outreach task, notifies sales leader
```

---

#### Feature 1.3: Explainability and Scope Rationale

Every result includes:
- What data was queried (sources)
- Why user can see it (authorization proof)
- Scope boundaries applied (what was filtered/masked)

**Example header:**
```
✓ Data Sources: Sales pipeline system, historical close rates
✓ Your Access: Sales Director role authorized for forecast inputs
✓ Scope Boundaries:
  • Customer names NOT included (masking for confidential discussions)
  • Field-level: Forecast values only; pricing and terms hidden
  • Row-level: Your assigned accounts only (12 accounts, $940M pipeline)
✓ Confidence: 18-month historical basis; 2 months forward = moderate confidence
```

---

#### Feature 1.4: Result Export with Policy-Aware Redaction

User exports report to email. System automatically redacts per policy:

**Example:** Healthcare compliance officer exports stroke admissions
```
Original fields: Patient name, exact age, admission reason, insurance
Exported fields: Age bin (65-75 age, not exact), admission reason, unit, length of stay
Removed: Patient name, insurance (per RLS policy)
Encryption: End-to-end before email transmission
Audit: Export logged with timestamp and recipient
```

---

#### Feature 1.5: Saved Query Templates with Governance

Sales operations creates template: "Monthly Sales Dashboard"
```
Parameters: Month (default: current), Region (optional)
Content: Revenue by region, YoY, variance to budget; new customer count; churn; win rates
Access: Anyone in Sales role
Usage: 1,240 runs in February by 280 staff
Status: APPROVED (Finance Director, 2/28)
Audit: All runs logged; Finance can see population analytics
Version control: Retire old versions, push updates to all users
```

---

### Tier 2: Tenant Administration Features

#### Feature 2.1: User and Group Lifecycle Management

Console for provisioning, deprovisioning, group management:
```
User Management:
  • Add user: John Smith, role=Sales_Rep, start=3/10
  • Disable user: Mark Johnson (save audit, archive after 90 days)
  • Bulk import: 50 contractors via CSV, auto-provision

Group Management:
  • Create "Board_Observers" (8 members)
  • Modify "Finance_Ops" access to new system
  • Deprovisioning report: Users inactive >60 days (suggest archiving)

Audit: Show all access changes last 30 days
```

---

#### Feature 2.2: Role and Persona Builder (No-Code)

Example: Healthcare CIO creating "Clinical_Department_Manager"

```
Role Definition:
Attributes: Manager of department X, reports to VP Clinical Ops

Access:
  • Patient records: Assigned department patients only
  • Clinical workflows: Orders, results, discharge summaries
  • Financial: Aggregate cost reports only (NOT individual billing)
  • QA metrics: Department metrics vs. peer benchmarks

Scope Rules (auto-enforced):
  • RLS: Department = user's department
  • FLS: No SSN, insurance subscriber ID
  • Temporal: Patients seen in last 12 months
  • Escalation: Can request temporary access outside (approval, logged)

Audit Implications:
  • All outside-department access triggers alert
  • Escalated access logged + reviewable
  • Satisfies HIPAA "need to know"

Users with role: 12 department managers
Last modified: Sarah Torres, 2/15/2026
```

---

#### Feature 2.3: Data Source Connector Management

Console for adding/managing data sources:
```
Connected Sources (8 total):

1. Salesforce (SFDC)
   • Status: ✓ Connected (100+ fields)
   • Last sync: 5 min ago
   • Latency: 340ms avg
   • Health: GREEN ✓
   • Actions: [Test] [Resync schema] [Disable] [View errors]

2. SAP (Accounting ERP)
   • Status: ✓ Connected
   • Latency: 1,200ms (complex schema)
   • Health: YELLOW ⚠ (slow query detected—recommend index)
   • Actions: [Optimize] [Test]

3. ADP (HR System)
   • Status: ✗ DISCONNECTED
   • Error: "API key expired"
   • Quick fix: [Regenerate key]

Add New Source:
  [Select type] [Enter credentials] [Test] [Import schema] [Assign to tenant]
```

---

#### Feature 2.4: Field-Level Masking and Row-Level Policies (No-Code)

**Field Masking Rule Example:**
```
Rule: Patient_SSN_Mask

Pattern: XXX-XX-#### (hides first 5 digits)

Who sees full SSN?
  ✓ Billing (payment verification needed)
  ✓ Compliance (BAA audits)
  ✗ Clinical staff
  ✗ Researchers (de-identified cohorts)

Unmasking:
  • Emergency access: logged + audited
  • Justified by job function + approval

Audit trail: [All unmasking events logged]
Status: ACTIVE (2,150 clinical staff)
```

**Row-Level Policy Example:**
```
Policy: LoanOfficer_Portfolio_Scope

Scope:
  User sees loans WHERE:
    • loan.originating_office = user.office, OR
    • loan.assigned_officer = user.name, OR
    • (user.role = "Senior" AND loan.status = "problem")

Rationale:
  • Line officers: Own portfolio
  • Senior officers: Problem loans only (supervision)
  • Cross-office: Prevented (conflict of interest)

Effect:
  User: Mike Chen (Boston, Commercial Loan Officer)
  Visible: 45 assigned loans + 2 problem loans from other offices = 47 total
  Policy applied silently; audit logged "RLS restriction applied"
```

---

#### Feature 2.5: Workflow and Trigger Management (No-Code)

Finance Director creates: "Month-End Close Automation"

```
Trigger: First business day of month, 11:00pm (batch window)

Steps:
  1. Verification
     • Check: GL batches posted (automated)
     • If FAIL: Alert accountant, stop
     • If PASS: Continue → 2 seconds

  2. Revenue Accrual
     • Calculate unbilled revenue (running...)
     • Duration: ~30 seconds

  3. Expense Accrual
     • Calculate accrued expenses (queued)

  4. Approval: HUMAN-IN-LOOP
     • Accountant reviews, approves
     • SLA: 4 hours

  5. Consolidation
     • Eliminate inter-entity transactions (queued)

  6. Report Generation
     • P&L, balance sheet, cash flow (queued)

  7. Distribution
     • Email to Finance + board portal (queued)

Total runtime: 45 minútes typically
SLA: Month-end close by 10:45am
Rollback: Available—if errors detected, GL can be restored
Audit: Every run logged with step-by-step times, approvals, outcomes
```

---

### Tier 3: Compliance and Audit Features

#### Feature 3.1: DSAR (Data Subject Access Request) Execution

```
DSAR Request:
ID: DSAR_2026_0347
Requestor: John Smith (customer since 2020)
Request: "Give me all records you hold about me"
Deadline: 30 days (GDPR)

ZTA-AI Processing:

Step 1: Identify
  • Customer master: ID #12847
  • Billing: 8 invoices, 4 payments
  • Support: 3 tickets
  • Analytics: Browsing/email data
  Total: 200+ records across 6 systems

Step 2: Aggregate → Collect to staging

Step 3: Redact → Remove others' records mentioning John

Step 4: Organize → Human-readable format (PDF, CSV)

Step 5: Deliver
  • Export encrypted
  • Secure portal (login required)
  • Access logged

Step 6: Document
  • Audit trail proves response within deadline
  • Legal evidence file (compliance proofing)

Status: COMPLETE (delivered 3/8, 7 days early)
Verification: User accessed 3/8 10:15am
```

---

#### Feature 3.2: Right-to-Erasure Execution

```
Erasure Request:
Customer: Jane Doe
Request: "Complete erasure of my personal data"
Basis: GDPR Article 17 (no longer needed)
Deadline: 45 days

Processing:

  Step 1: Identify deletable records
    • Account profile, billing, support, marketing: DELETE
    • Invoices (business records): RETAIN (accounting audit trail)

  Step 2: Deletion plan
    • Primary system: Delete customer + FK references
    • Billing: Pseudonymize (keep for audit, de-link from person)
    • Support: Delete tickets
    • Analytics: Delete browsing data
    • Backups: Flag for future purging (older backups auto-expire)

  Step 3: Execution
    • Execute deletes, verify completion

  Step 4: Validation
    • Query: SELECT COUNT(*) FROM customers WHERE id='Jane Doe' → Result: 0 ✓

  Step 5: Proof of Erasure
    • Deletion certificate
    • Signed by system, tamper-proof

Response to customer:
  "Your data has been fully deleted from live systems (3/15/2026).
   Offline backups may retain data for [X] days (auto-expire).
   [Deletion certificate attached]"

Status: COMPLETE
Proof: Signed deletion certificate + validation query logs
```

---

#### Feature 3.3: Audit Ledger and Forensic Export

```
Audit Query: "All access to patient record #54321 (2/15-3/15/2026)"

Results (23 events):

1. 2026-02-15 08:15 | Dr. Sarah Chen | Query patient record
   Justification: Patient assigned to Dr. Chen (clinical care)
   Policy: ✓ ALLOWED (patient assignment)
   Outcome: Record viewed 3 min, no export
   Audit: Event logged

2. 2026-02-15 14:30 | Patient Relations | SEND_PATIENT_LETTER
   Justification: Post-op care instructions
   Policy: ✓ ALLOWED (operations staff)
   Outcome: Letter printed (no electronic export)

3. 2026-02-20 10:45 | Compliance Officer | Query patient demographics
   Justification: HIPAA audit (validating controls)
   Policy: ✓ ALLOWED (compliance officer)
   Outcome: Record viewed, exported to secure audit file (encrypted)

4. 2026-02-22 16:20 | Billing Staff | ATTEMPTED ACCESS
   Justification: Claims verification
   Policy: ✗ BLOCKED (billing cannot see clinical)
   Outcome: Access denied, policy enforced

[Continue for all 23 events]

Summary:
  • Total: 23 access events
  • Authorized: 22 (95.7%)
  • Denied: 1 (4.3%)
  • Exports: 1 (compliance audit)
  • Unusual activity: 0

Forensic Export:
  • Format: CSV (tamper-proof audit report)
  • Signed: System signature (proves authenticity)
  • Compliance: Meets HIPAA audit standards (regulator-ready)
```

---

## Architecture Deep Dives with Examples

### Layer A: Experience and Access

**Components:**
- Chat interface (natural language entry)
- Session management (MFA, timeouts, tokens)
- Request context initialization (user scope setup)

**Example:**
```
User Sarah (Sales Manager) logs in:
  1. SAML authentication confirmed
  2. MFA: SMS code verified
  3. Session issued: 8-hour validity, refresh capability
  4. Context initialized:
     • User ID: sarah_chen_123
     • Tenant: FirstBank
     • Role: Sales_Manager
     • Scope filter: "Commercial loans, Boston office"
  5. All downstream queries filtered by scope automatically
```

---

### Layer B: Interpretation and Planning

**Components:**
- Intent extractor (recognizes operation type)
- Entity mapper (business terms → database schemas)
- Scope pre-checker (validates authorization)
- Query planner (generates optimized execution plan)

**Healthcare Example:**
```
Nurse asks: "Patients from my department without follow-up scheduled <60 days?"

Processing:
  1. Intent: FILTERED_AGGREGATION (patients with temporal filter + negation)
  2. Mapping: "my dept" → user.assigned_dept; "follow-up <60d" → LEFT JOIN appointments
  3. Scope: ✓ Nurse assigned to Cardiology; authorized
  4. Plan: Query patient + discharge + appointments with temporal predicate
  
Execution:
  SELECT p.*, dm.discharge_date 
  FROM patients p
  JOIN discharge_master dm ON ...
  LEFT JOIN appointments a ON ... AND a.appointment_date BETWEEN dm.discharge_date AND dm.discharge_date + 60
  WHERE p.department_id = '4317' AND a.appointment_id IS NULL

Result: 12 patients without scheduled follow-ups
Explanation: "These are aggregated, no PII; you have Cardiology access"
```

---

### Layer C: Policy and Guardrail Enforcement

Multiple policy layers checked on every query:

```
Manufacturer analyst query: "Show supplier scorecards (cost, quality)"

Policy checks:
  1. RBAC: Supply_Chain_Analyst role? ✓ YES
  2. ABAC: Has "Metals_Fasteners" category assigned? ✓ YES
     → Filter: supplier_category = "Metals_Fasteners" APPLIED
  3. FLS: Can see cost_score, quality_score? ✓ YES
     → Cannot see: contract_value, margin MASKED (2 fields hidden)
  4. Temporal: Access time restrictions? ✗ NONE
  5. Risk-based: MFA verified? Device safe? ✓ YES

Final result: 34 Metals suppliers, cost & quality scores only
Audit: "FILTER APPLIED (category), MASKING APPLIED (2 fields)"
```

---

### Layer D: Execution Plane

**Components:**
- Query compiler (translate to DB-native)
- Connector runtime (source adapters)
- Action orchestrator (workflows)
- Trigger engine (scheduled/event-based)

**Example Workflow:**
```
Month-end close automation:
  Status: RUNNING (started 11:00pm 3/1)

  Step 1: Validation [73% complete]
    Check: GL batches all posted
    → 847 batches identified ✓
    Duration: 2 seconds

  Step 2: Revenue Accrual [Running...]
    Calculate unbilled revenue
    Estimated duration: 30 seconds

  [Step 3-7 queued...]

Once Step 2 completes → Step 3 starts
After Step 4 (approval gate) → Manual approval required
All steps audited in real-time
Rollback available if errors found
```

---

### Layer E: Compliance and Audit

- Immutable ledger (append-only audit log)
- DSAR/erasure workflows
- Consent and legal basis tracking
- Breach workflows

**Already detailed above in Feature 3.1-3.3**

---

### Layer F: Reliability and Operations

**Observability:**
- Distributed tracing (interpretation → policy → compile → execution)
- Structured logging (sensitive data minimized)
- Metrics (latency, throughput, policy denials)
- Alerting (severity + escalation)

**Example SLO Dashboard:**
```
Interactive Query Path:
  Target: <1000ms P95
  Current: 940ms P95 (target met ✓)
  Tail risk (<1): 2.1% (within 2.5% budget)

Workflow Execution:
  Target: 99.9% availability
  Current: 99.92% (target met ✓)

Compliance Features:
  DSAR processing time: avg 18 hours (target <24h)
  Audit log freshness: <30 seconds (current: 8 seconds)
```

---

## Compliance Operations by Framework

### HIPAA Implementation Example

**Access Control:**
Doctors can only access patients in their care scope. Break-glass access logged and reviewed.

**Audit Logging:**
Every PHI access logged (6-year retention). Immutable.

**Breach Investigation:**
```
Alert: Employee accessed 340 patient records inappropriately

Investigation:
  • Which records: Identified, count = 340
  • What data: Clinical + imaging (PHI)
  • Risk: HIGH (comprehensive access, no documented need)
  
ZTA-AI forensic report:
  • Access denied by policy (logged)
  • No data export detected
  • Evidence: Audit logs proving control worked
  
HIPAA response:
  • 340 patients potentially affected
  • Notify within 60 days
  • Report to HHS OCR
  • ZTA-AI provides complete forensic package for regulators
```

### GDPR Implementation Example

**DSAR:** [Detailed in Feature 3.1 above]
**Erasure:** [Detailed in Feature 3.2 above]

**Consent Management:**
```
Customer opts out of marketing communications:
  1. Withdrawal recorded in ZTA-AI (timestamp)
  2. Marketing data tagged for deletion
  3. Automated deletion job (next 24 hours)
  4. Marketing systems receive instruction
  5. Verification query: Confirm customer removed
  6. Audit trail: Withdrawal timestamp → deletion timestamp → verification proof
  
Proof to regulator: "Customer opted out [date]; system automatically deleted data by [date]"
```

### DPDP ACT 2023 (India) Implementation Example

**Purpose Limitation:**
Every operation tagged with purpose ("customer support", "billing", "marketing"). Cannot repurpose without new consent.

**Data Principal Rights:**
Similar to GDPR but India-specific (correction request workflow, portability format).

**Localization:**
```
Indian customer data retention policy:
  • Sensitive data (financial, health, biometric): Must stay in India
  • Non-sensitive: Can transfer to Singapore with proper controls

Policy:
  WHERE data_category = 'SENSITIVE' → allowed_regions = ['India_DC']
  WHERE data_category = 'NON_SENSITIVE' → allowed_regions = ['India_DC', 'Singapore_DC']

Enforcement:
  User in US tries to copy customer data → BLOCKED (policy violation)
  Audit: Attempted export logged
```

---

## Quality Gates (Pre-Launch Checklist)

### Gate 1: Feature Completeness
- [ ] Every features documented, implemented, tested
- [ ] All 12 baseline templates operational (zero placeholders)
- [ ] Every admin operation in UI (no engineering-required tasks)
- [ ] Zero hardcoded domain assumptions

### Gate 2: Security
- [ ] No mock auth (SAML/OIDC only)
- [ ] Service mTLS active
- [ ] Egress controls prevent data exfiltration
- [ ] Red-team validation (zero critical/high vulns)
- [ ] Secret rotation automated

### Gate 3: Compliance
- [ ] DSAR workflow tested end-to-end
- [ ] Erasure workflow tested with recovery verification
- [ ] HIPAA breach detection operational
- [ ] GDPR consent workflow operational
- [ ] Immutable audit ledger verified

### Gate 4: Performance
- [ ] P95 latency <1000ms (interactive)
- [ ] Throughput supports 100 concurrent users
- [ ] Tail behavior acceptable under 10x peak load
- [ ] Degradation mode policy-safe

### Gate 5: Observability
- [ ] End-to-end tracing enabled
- [ ] SLO dashboards live
- [ ] Incident runbooks tested
- [ ] Forensic export verified

---

## 10-Phase Execution Plan (Outcome-Based, No Timelines)

### Phase 1: Architecture Freeze
**Outcome:** Zero ambiguity; every feature has owner + acceptance criteria

### Phase 2: Security Hardening
**Outcome:** Enterprise-grade identity, transport, egress controls

### Phase 3: Zero-Learning Enforcement
**Outcome:** Runtime policy enforces non-learning; data containment proven

### Phase 4: Connector Productionization
**Outcome:** All connectors certified, reliable, policy-safe

### Phase 5: Interpreter Maturity
**Outcome:** Domain-agnostic; new domains self-onboardable without hardcoding

### Phase 6: Agentic Completion
**Outcome:** 12 templates executable; action registry operational

### Phase 7: Compliance Operations
**Outcome:** HIPAA/GDPR/DPDP workflows operational; evidence exportable

### Phase 8: Admin Surface Completion
**Outcome:** Full no-code consoles; no engineering required for operations

### Phase 9: Performance Hardening
**Outcome:** <1000ms P95; SLOs met; SLA reliability proven

### Phase 10: Pilot Validation
**Outcome:** Live customer environment proof; market-ready launch

---

## Detailed Implementation Plan: Phase-by-Phase Breakdown

### Phase 1: Architecture Freeze
**Duration:** 3 weeks | **Owner:** Tech Lead

**Objectives:**
1. Document all component interfaces and contracts
2. Establish data flow specifications
3. Create feature-to-architecture traceability matrix
4. Define security boundaries and trust zones

**Deliverables:**
- [ ] Component interaction diagram (all layers A-F)
- [ ] Data schema definitions (core entities, relationships)
- [ ] API specification (intent input → result output)
- [ ] Error handling and fallback strategy document
- [ ] Traceability matrix: Feature → Component owner
- [ ] Architecture review sign-off (Security, Compliance, Engineering)
- [ ] **[CRITICAL] Action Registry Schema for All 12 Templates** — Each action must be fully specified with: trigger, required_data_scope, required_permissions, approval_requirements, input_schema, execution_steps, output_schema, risk_classification, audit_implications, allowed_personas, prohibited_actions (see template example in DSAR_EXECUTE). Phase 6 cannot proceed without this.
- [ ] **[CRITICAL] Connector Plugin Interface Contract** — Define the interface every connector must implement (connect, test_connection, discover_schema, execute_query, sync, health_check) with precise signatures, error codes, and timeout semantics. Custom connector SDK depends on this contract.

**Acceptance Criteria:**
- Zero unspecified components
- Every feature mapped to at least one component
- Security team has signed off on trust boundaries
- No ambiguity on data residency
- All 12 action templates have complete schema (Phase 6 gating criterion)
- Connector plugin interface contract is signed off by Integration Lead

**Dependencies:**
- Product requirements finalized (no scope changes)
- Stakeholder alignment on domains + personas
- Technology stack decisions finalized

---

### Phase 2: Security Hardening
**Duration:** 5 weeks | **Owner:** Security Lead

**Objectives:**
1. Remove all mock/placeholder auth (production OAuth/SAML/OIDC)
2. Implement service-to-service mTLS
3. Deploy secrets management framework
4. Establish egress controls and data exfiltration prevention

**Deliverables:**
- [ ] SAML/OIDC integration (test IdP configured)
- [ ] MFA enforcement (SMS, TOTP, hardware key support)
- [ ] Service certificate authority + issuance automation
- [ ] Secrets vault configured (HashiCorp Vault or AWS Secrets Manager)
- [ ] Network policy definitions (ingress/egress rules)
- [ ] Security scanning in CI/CD (SAST, dependency checks)
- [ ] Incident response playbook

**Acceptance Criteria:**
- No HTTP traffic (all HTTPS/mTLS)
- Secrets never logged or exposed in code
- MFA bypass impossible without physical access to vault
- Egress whitelisting prevents unauthorized external calls
- Dependency scanning blocks known CVEs (CVSS >7)

**Security Validations:**
- [ ] Penetration test: Auth bypass attempts (0 successful)
- [ ] Secret scanning: Vault rotation verified
- [ ] Network: Port scan shows only expected open ports

---

### Phase 3: Zero-Learning Enforcement
**Duration:** 4 weeks | **Owner:** ML/Policy Lead

**Objectives:**
1. Runtime policy prevents model parameter updates from customer data
2. Audit trail proves zero inference data retention
3. Isolation mechanisms prevent cross-tenant data leakage

**Deliverables:**
- [ ] Model serving layer (inference only, no learning)
- [ ] Policy enforcement: Read-only mode for model artifacts
- [ ] Data isolation: Tenant-specific cache/compute resources
- [ ] Audit logging: Track all data inputs and model interactions
- [ ] Compliance attestation: Zero-learning guarantee certificate

**Acceptance Criteria:**
- Model parameters unchanged after 1,000 customer queries (audit verified)
- No training data written to persistent storage
- Customer data deleted within 24 hours of session end
- Cross-tenant data queries blocked by policy layer
- Compliance audit can prove zero-learning status

**Testing:**
- [ ] Query 1,000+ customer records, verify model weights unchanged
- [ ] Confirm all temporary data deleted post-session
- [ ] Simulate multi-tenant concurrent access, verify isolation

---

### Phase 4: Connector Productionization
**Duration:** 6 weeks | **Owner:** Integration Lead

**Objectives:**
1. Certify SQL connector (existing; improve reliability)
2. Implement 4 new connectors (ERP, Data Warehouse, BI, Sheets)
3. Establish connector certification harness
4. Implement health monitoring and auto-recovery

**Deliverables:**
- [ ] SQL connector v2 (connection pooling, configurable timeout, retry logic)
- [ ] SAP/Oracle ERP connector (OData, REST API support)
- [ ] Snowflake/BigQuery connector (federated query, cost optimization)
- [ ] Tableau/Looker BI connector (metadata import)
- [ ] Google Sheets connector (real-time sync)
- [ ] Connector certification framework (latency, reliability, policy-safety tests)
- [ ] Health monitoring dashboard (connector uptime, latency percentiles)
- [ ] Circuit breaker pattern (graceful degradation when connector fails)

**Acceptance Criteria:**
- [ ] Each connector: 100+ test cases, 99.95% success rate
- [ ] Latency SLO: P95 <500ms per connector
- [ ] Auto-recovery: 95% of transient failures resolved without human intervention
- [ ] Schema change detection: Alerts within 10 minutes

**Certification Harness:**
```
For each connector:
  1. Latency test: 100 concurrent queries → P95 <500ms
  2. Reliability test: 10,000 sequential queries → 0 hard failures
  3. Schema test: Detect field additions/deletions within 10 min
  4. Policy test: Row/field masking applied correctly
  5. Data validation: Query results match native client
```

---

### Phase 5: Interpreter Maturity
**Duration:** 8 weeks | **Owner:** NLP/Domain Lead

**Objectives:**
1. Generalize domain logic (remove healthcare/banking hardcoding)
2. Implement domain-agnostic intent classification
3. Create domain onboarding framework
4. Validate across 5+ domains (manufacturing, retail, professional services, insurance, finance)

**Deliverables:**
- [ ] Domain abstraction layer (entity taxonomy, relationship rules)
- [ ] Intent classifier v2 (domain-agnostic; 95%+ accuracy on standard intents)
- [ ] Alias resolution engine (customer-specific terminology mapping)
- [ ] Domain onboarding playbook (steps to add new domain)
- [ ] Validation results (5+ domain test results, accuracy metrics)
- [ ] Fallback handler (graceful degradation for out-of-distribution queries)

**Acceptance Criteria:**
- [ ] No domain-specific hardcoding (every inference parameterized)
- [ ] Intent accuracy: >95% on top 20 intent classes per domain
- [ ] New domain onboardable with <2 weeks effort
- [ ] Queries with out-of-distribution intents return "I don't understand" (not hallucination)
- [ ] Cross-domain conflicts handled correctly (e.g., "records" = database records in IT, patient records in healthcare)

---

### Phase 6: Agentic Completion
**Duration:** 7 weeks | **Owner:** Workflow Lead

**Objectives:**
1. Implement 12 baseline action templates as executable workflows
2. Create action registry and triggering system
3. Build workflow orchestrator (sequential, parallel, approval gates)
4. Implement rollback and audit for all actions

**Deliverables:**
- [ ] 12 action templates (DSAR, erasure, escalation, bulk update, approval, etc.)
- [ ] Action registry schema (permissions, approval requirements, rollback rules)
- [ ] Workflow orchestrator (DAG execution, conditional branches, gates)
- [ ] Approval workflow (SLA-aware routing, escalation)
- [ ] Rollback mechanism (audit trail, transaction reversibility)
- [ ] Dry-run mode (preview action outcomes without execution)
- [ ] Integration with ticketing system (Jira, ServiceNow)

**Action Template Examples:**
```
1. DSAR_REQUEST: Trigger DSAR process, set deadline, track completion
2. ERASURE_REQUEST: Identify deletable data, execute deletion, prove completion
3. ESCALATE_TO_MANAGER: Attach evidence, notify manager, auto-SLA
4. BULK_SOFT_DELETE: Mark records deleted (soft), preserve audit trail
5. FIELD_MASKING_UPDATE: Re-classify sensitivity, apply masking, audit impact
6. CONSENT_WITHDRAWAL: Revoke analytics access, delete marketing data
7. INCIDENT_RESPONSE: Freeze access, generate forensic report, notify team
8. POLICY_UPDATE: Deploy new policy, validate compliance, audit existing data
9. CONNECTOR_REFRESH: Re-sync schema, alert on breaking changes
10. AUDIT_EXPORT: Generate compliance report, sign, deliver securely
11. SEGMENT_ACTIVATION: Export audience to marketing platform (policy-safe)
12. SCHEDULED_REPORTING: Auto-generate compliance reports, email stakeholders
```

**Acceptance Criteria:**
- [ ] All 12 templates operational (zero placeholders)
- [ ] Action execution latency: <5 seconds to initiation
- [ ] Approval workflow: SLA met (escalation within 4 hours)
- [ ] Rollback success rate: >99%
- [ ] Audit trail: Every step logged, tamper-proof

---

### Phase 7: Compliance Operations
**Duration:** 6 weeks | **Owner:** Compliance Lead

**Objectives:**
1. Operationalize DSAR, erasure, and breach workflows
2. Implement consent and retention management
3. Create compliance evidence export
4. Validate against HIPAA, GDPR, DPDP requirements

**Deliverables:**
- [ ] DSAR workflow (identify, aggregate, redact, deliver, prove)
- [ ] Erasure workflow (identify deletable, execute, prove deletion)
- [ ] Breach investigation workflow (forensic export, analysis, evidence)
- [ ] Consent management (withdrawal, re-purpose requests)
- [ ] Retention engine (auto-delete aged data per policy)
- [ ] Compliance report generator (HIPAA audit trail, GDPR controller proof)
- [ ] Legal holds (preserve data pending litigation)
- [ ] Signed attestations (regulatory-ready proofs)

**Workflow Examples:**
```
DSAR Workflow:
  1. Request intake (validate subject identity)
  2. System scan: Identify all records by subject
  3. Aggregation: Collect from all sources
  4. Redact: Remove other subjects' data
  5. Organize: Structure for delivery
  6. Delivery: Secure portal or encrypted email
  7. Proof: Signed receipt, compliance log

HIPAA Implementation:
  • Break-glass access: Logged, reviewed within 24 hours
  • Audit retention: 6 years, immutable
  • Unauthorized access: Alert within 15 minutes
  • Breach determination: <72 hours to conclude
  • Notification: <60 days to impacted individuals
```

**Acceptance Criteria:**
- [ ] DSAR turnaround: 95% within 10 days (7-day SLO)
- [ ] Erasure verification: Proof that data cannot be reconstructed
- [ ] Breach investigation: Forensic report in <4 hours
- [ ] Audit evidence: Regulator-ready format
- [ ] No compliance violations in external audit

---

### Phase 8: Admin Surface Completion
**Duration:** 5 weeks | **Owner:** Frontend Lead

**Note:** This phase covers TENANT ADMIN surfaces (user management, role builder, policies, workflows). The SYSTEM ADMIN CONSOLE (fleet health, churn prediction, cost optimization) is an internal tool for ZTA-AI operations and should be considered as either a separate phase or explicitly split within this phase depending on resource allocation. Both are critical for launch but serve different users (customer admins vs. ZTA-AI ops team).

**Objectives:**
1. Build no-code consoles for tenant admins
2. Eliminate all engineering-required operations
3. Verify usability with non-technical admins (UAT)

**Deliverables:**
- [ ] User management console (provisioning, deprovisioning, bulk import)
- [ ] Role builder (RBAC, ABAC policy definition, no-code)
- [ ] Connector management (add, test, configure, disable)
- [ ] Field masking rules (visual policy editor)
- [ ] Row-level policy editor (scope conditions, approval gates)
- [ ] Workflow builder (template configuration, trigger setup)
- [ ] Audit dashboard (access logs, policy decisions, anomalies)
- [ ] Compliance reporting (DSAR status, erasure proof, audit evidence)

**User Flows:**
```
Scenario: Hospital IT admin adds new clinical department

  1. Navigate: Admin → User Groups → [Create]
  2. Define: name="Cardiology_2026", description="..."
  3. Add members: [Bulk upload CSV or add individually]
  4. Assign role: Select from role catalog or create custom
  5. Set scope: Department = Cardiology, can see all patients assigned to dept
  6. Configure masking: SSN masked, insurance hidden
  7. Approval gate: Compliance reviews, approves
  8. Deploy: Immediate, audit logged
  9. Validation: Test user can see correct patients, cannot see restricted fields
```

**Acceptance Criteria:**
- [ ] Every operation self-service (no Slack @ engineer)
- [ ] UAT with 5+ non-technical admins: 95%+ task completion without support
- [ ] Documentation: Step-by-step guides for all operations
- [ ] Rollback available for all changes (undo within 30 days)

---

### Phase 9: Performance Hardening
**Duration:** 5 weeks | **Owner:** Performance Lead

**Objectives:**
1. Achieve <1000ms P95 latency for 95% of queries
2. Support 100+ concurrent users
3. Optimize tail behavior (p99, p99.9)
4. Load test at 10x peak and verify graceful degradation

**Deliverables:**
- [ ] Query optimization (caching, query rewrites, index recommendations)
- [ ] Load testing results (100 concurrent users, <1000ms P95 sustained)
- [ ] Tail latency analysis (p99, p99.9 < policy limit)
- [ ] Capacity model (max concurrent users, throughput limits)
- [ ] Degradation policy (queue management, priority routing under load)
- [ ] SLO dashboard (live monitoring of latency, error rate)
- [ ] Performance regression test (automated in CI/CD)

**Optimization Targets:**
```
Baseline measurements:
  • Intent extraction: 250ms (target: 150ms)
  • Schema queries: 500ms (target: 200ms)
  • Query compilation: 140ms (target: 80ms)
  • Policy enforcement: 60ms (target: 40ms)
  • Result serialization: 50ms (target: 30ms)
  Total baseline: ~1000ms
  Target total: <600ms (buffer for network/db latency) = <1000ms P95

Optimization strategies:
  1. Cache intent embeddings (re-use for identical queries)
  2. Pre-compute schema summaries (avoid full scan per query)
  3. Index policy rules (faster scope matching)
  4. Result streaming (start returning before full query complete)
  5. Connector connection pooling (avoid connection overhead)
```

**Load Testing Scenarios:**
```
Scenario 1: Normal load (100 concurrent users, 2 req/min per user)
  Expected: 95th percentile <1000ms, p99 <2000ms
  Passes: Yes/No

Scenario 2: Peak load (200 concurrent users, 5 req/min per user)
  Expected: P95 <1500ms (graceful degradation)
  Queue: <60 seconds average wait
  Timeouts: <0.1%

Scenario 3: Burst spike (500 concurrent in 30 second window)
  Expected: Queue formation, recovery to normal within 5 minutes
  No data loss, no policy bypass
```

**Acceptance Criteria:**
- [ ] P95 <1000ms sustained over 8-hour load test
- [ ] Error rate <0.1% during peak load
- [ ] No data loss or corruption under any load
- [ ] Graceful shutdown possible (in-flight requests complete within SLA)

---

### Phase 10: Pilot Validation
**Duration:** 8 weeks | **Owner:** Product Lead

**Objectives:**
1. Deploy in live customer environment
2. Validate all features end-to-end
3. Prove system meets compliance requirements
4. Gather feedback and refine UX

**Deliverables:**
- [ ] Pilot customer identified (signed agreement, legal BAA)
- [ ] Deployment runbook (installation, configuration, validation)
- [ ] Customer training (admin users, end users, support staff)
- [ ] Support escalation process (on-call Engineer availability)
- [ ] Feedback collection (weekly surveys, usage metrics)
- [ ] Compliance validation (HIPAA/GDPR/DPDP proofs)
- [ ] Go/no-go decision documentation

**Pilot Success Criteria:**
- [ ] 100% feature adoption by target users
- [ ] Zero security incidents or policy violations
- [ ] <5% user support requests (system is intuitive)
- [ ] Compliance audit: Zero findings
- [ ] Customer recommendation: "Ready for production"

**Pilot Timeline (8 weeks):**
```
Week 1-2: Deployment and configuration
Week 3-4: User training and initial usage
Week 5-6: Feature validation and refinement
Week 7: Compliance audit
Week 8: Feedback synthesis and go/no-go decision
```

---

## Technical Specifications: Deep Dives

### Core Data Model

**Primary Entities:**

```json
{
  "tenant": {
    "id": "uuid",
    "name": "string",
    "status": "active|suspended|archived",
    "data_residency": ["region"],
    "compliance_framework": ["HIPAA", "GDPR", "DPDP"],
    "created_at": "timestamp",
    "updated_at": "timestamp"
  },
  "user": {
    "id": "uuid",
    "tenant_id": "uuid",
    "email": "string",
    "roles": ["role_id"],
    "scope": {object},
    "mfa_enabled": boolean,
    "last_login": "timestamp",
    "status": "active|disabled|archived"
  },
  "role": {
    "id": "uuid",
    "tenant_id": "uuid",
    "name": "string",
    "permissions": ["permission"],
    "scope_rules": [{"attribute": "department", "value": "..."}],
    "created_at": "timestamp"
  },
  "policy": {
    "id": "uuid",
    "tenant_id": "uuid",
    "type": "RBAC|ABAC|RLS|FLS",
    "rules": [{...}],
    "status": "active|draft|retired",
    "created_by": "uuid",
    "created_at": "timestamp"
  },
  "connector": {
    "id": "uuid",
    "tenant_id": "uuid",
    "type": "sql|salesforce|erp|warehouse",
    "credentials": "encrypted_string",
    "schema": "{...}",
    "last_sync": "timestamp",
    "status": "healthy|degraded|error"
  },
  "action": {
    "id": "uuid",
    "user_id": "uuid",
    "type": "DSAR|ERASURE|EXPORT|UPDATE",
    "status": "pending|approved|executing|completed|failed|rolled_back",
    "approval_chain": [{...}],
    "executed_at": "timestamp",
    "audit_log": "{...}"
  },
  "audit_event": {
    "id": "uuid",
    "tenant_id": "uuid",
    "user_id": "uuid",
    "event_type": "QUERY|ACTION|POLICY_DECISION|AUTH_FAILURE",
    "resource_identifier": "string",
    "policy_applied": "string",
    "decision": "ALLOW|DENY",
    "reason": "string",
    "timestamp": "timestamp",
    "immutable": true
  }
}
```

### API Specification Examples

**Query Endpoint:**
```
POST /api/v1/query
Authorization: Bearer {token}
Content-Type: application/json

Request:
{
  "tenant_id": "uuid",
  "user_id": "uuid",
  "session_id": "uuid",
  "query": "Show me sales by region for Q4",
  "context": {
    "previous_queries": ["..."],
    "session_filters": {...}
  }
}

Response (200 OK):
{
  "query_id": "uuid",
  "status": "success",
  "intent": {
    "type": "AGGREGATION",
    "entities": ["sales"],
    "groupby": ["region"],
    "filter": {"period": "Q4"}
  },
  "execution_plan": {
    "steps": [
      {"type": "schema_lookup", "estimated_latency_ms": 150},
      {"type": "policy_evaluation", "estimated_latency_ms": 40},
      {"type": "query_compilation", "estimated_latency_ms": 80},
      {"type": "database_query", "estimated_latency_ms": 300}
    ]
  },
  "results": {
    "rows": [
      {"region": "North", "sales": 2340000},
      {"region": "South", "sales": 1890000},
      ...
    ]
  },
  "explainability": {
    "scope_applied": "role=SalesAnalyst, regions=[North,South,East]",
    "fields_masked": ["customer_names", "deal_terms"],
    "row_filter": "WHERE sales_rep_id IN (user.assigned_territories)"
  },
  "performance": {
    "total_latency_ms": 570,
    "database_rows_scanned": 45000,
    "result_rows_returned": 3,
    "cache_hit": false
  },
  "audit": {
    "audit_event_id": "uuid",
    "logged_at": "timestamp"
  }
}

Response (403 Forbidden):
{
  "error": "POLICY_VIOLATION",
  "reason": "User does not have access to customer pricing fields",
  "policy_id": "pol_23847",
  "policy_rule": "FLS_pricing_restricted_to_finance_only"
}

Response (401 Unauthorized):
{
  "error": "INVALID_SESSION",
  "reason": "Token expired; re-authenticate required"
}
```

**Action Execution Endpoint:**
```
POST /api/v1/actions/{action_type}/execute
Authorization: Bearer {token}

Request (DSAR Action):
{
  "subject_identifier": "email_address@example.com",
  "subject_verification": "OTP validated",
  "delivery_method": "secure_portal|encrypted_email",
  "include_audit_logs": true
}

Response (202 Accepted):
{
  "action_id": "uuid",
  "status": "queued",
  "estimated_completion_time": "2026-03-13T14:30:00Z",
  "next_steps": [
    "Waiting for background processing",
    "Aggregating data from 5 sources",
    "Compliance review",
    "Delivery"
  ],
  "webhook_callback": "https://webhook.customer.com/dsar_complete"
}

Polling Status:
GET /api/v1/actions/{action_id}/status

Response:
{
  "action_id": "uuid",
  "status": "completed",
  "completion_time": "2026-03-13T11:45:00Z",
  "completion_summary": {
    "records_collected": 247,
    "records_redacted": 12,
    "records_delivered": 235,
    "delivery_method": "secure_portal",
    "recipient_accessed": true,
    "recipient_access_time": "2026-03-13T12:15:00Z"
  },
  "forensic_evidence": {
    "request_received_at": "2026-03-12T09:45:00Z",
    "processing_initiated": "2026-03-12T09:47:00Z",
    "legally_compliant": true,
    "sla_met": true,
    "regulatory_proof_id": "proof_xyz123"
  }
}
```

**Policy Definition Endpoint:**
```
PUT /api/v1/policies/field-level-masking
Authorization: Bearer {admin_token}

Request:
{
  "policy_id": "fls_patient_ssn_mask",
  "field_path": "patients.social_security_number",
  "mask_pattern": "XXX-XX-####",
  "exceptions": [
    {
      "role": "Billing",
      "justification": "Payment verification"
    },
    {
      "role": "Compliance",
      "justification": "HIPAA audit"
    }
  ],
  "unmasking_audit_level": "critical",
  "audit_retention_days": 2190
}

Response (200 OK):
{
  "policy_id": "fls_patient_ssn_mask",
  "status": "active",
  "affected_users": 2150,
  "deployed_at": "2026-03-13T14:32:00Z",
  "validation": {
    "enforcement_verified": true,
    "sample_queries_tested": 100,
    "test_pass_rate": 1.0
  },
  "audit_log": {
    "created_by": "admin_sarah@hospital.com",
    "created_at": "2026-03-13T14:30:00Z",
    "change_reason": "Compliance requirement"
  }
}
```

---

---

### Connector Plugin Interface Contract

Every connector must implement this interface. This is the foundation for the connector marketplace, custom connector SDK, and third-party connector development.

**Connector Interface Definition:**

```python
# Every connector extends this base class

class ConnectorBase:
    """
    Every data source connector implements this contract.
    Violations of this interface cause Phase 4 gating to fail.
    """
    
    def __init__(self, connector_id: str, tenant_id: str, config: Dict):
        """
        Initialize connector with configuration.
        
        Args:
            connector_id: Unique connector instance ID (e.g., "salesforce_prod_eur")
            tenant_id: Tenant this connector belongs to (scope enforcement)
            config: Connection config (encrypted: username, password, endpoint, etc.)
        
        Raises:
            ConfigurationError: Invalid configuration
        """
        pass
    
    async def connect(self, timeout_seconds: int = 30) -> ConnectionStatus:
        """
        Establish connection to data source.
        
        Returns:
            ConnectionStatus with:
              - status: "connected" | "error"
              - response_time_ms: int
              - error: str (if error)
        
        Timeout: If connection takes >30s, raise TimeoutError
        Retry: Caller handles retry logic (circuit breaker pattern)
        
        Guarantee: No customer data retrieved during connect()
        """
        pass
    
    async def test_connection(self) -> TestResult:
        """
        Run health check: Can we reach the source?
        
        Returns:
            {
              "status": "healthy" | "degraded" | "error",
              "latency_ms": 240,
              "error": "..."
            }
        
        Use case: Admin clicks "Test connection" in UI
        SLA: <5 seconds
        """
        pass
    
    async def discover_schema(self, 
                            force_refresh: bool = False,
                            timeout_seconds: int = 60) -> Schema:
        """
        Retrieve metadata about available tables/entities and fields.
        
        Args:
            force_refresh: Ignore cache, fetch fresh (default: use cache)
            timeout_seconds: Abort if exceeds 60 seconds
        
        Returns:
            {
              "tables": [
                {
                  "name": "customers",
                  "display_name": "Customers",
                  "record_count": 145000,
                  "fields": [
                    {
                      "name": "customer_id",
                      "type": "integer",
                      "unique": true,
                      "nullable": false,
                      "description": "Primary key"
                    },
                    {
                      "name": "email",
                      "type": "string",
                      "sensitive": true,  # Policy hint: might be PII
                      "searchable": true,
                      "description": "Customer email address"
                    },
                    ...
                  ]
                },
                ...
              ]
            }
        
        Caching: Schema cached for 24 hours (configurable)
        Change detection: Monitor for schema drifts, alert if breaking changes
        """
        pass
    
    async def execute_query(self,
                           compiled_query: str,
                           scope_context: ScopeContext,
                           timeout_seconds: int = 60) -> QueryResult:
        """
        Execute a compiled query against the data source.
        
        Args:
            compiled_query: Native SQL (e.g., PostgreSQL dialect)
                           Already includes row/field masking from policy layer
            scope_context: {
              "tenant_id": "...",
              "user_id": "...",
              "user_role": "...",
              "applied_filters": {...}  # Row-level scope already applied
            }
            timeout_seconds: Query timeout (prevent runaway queries)
        
        Returns:
            {
              "rows": [{...}, {...}],  # Result set
              "count": 1240,
              "latency_ms": 342,
              "warnings": []  # E.g., "Query truncated to 10K rows"
            }
        
        Error handling:
            - Timeout: Raise TimeoutError (caller handles gracefully)
            - Authentication: Raise AuthenticationError (ops notified)
            - Rate limit: Raise RateLimitError (queue retry)
            - Query error: Return error in response (not exception)
        
        Guarantee: Only rows/fields permitted by scope_context are returned
                  (enforced by compiled query, connector doesn't second-guess)
        """
        pass
    
    async def sync(self) -> SyncResult:
        """
        Full refresh of schema and metadata.
        
        Use case: Daily job to pick up schema changes (new tables, fields)
        or on-demand refresh after customer updates their schema
        
        Returns:
            {
              "status": "complete" | "partial" | "failed",
              "tables_discovered": 47,
              "tables_added": 3,
              "tables_removed": 0,
              "fields_changed": 12,
              "duration_ms": 24300,
              "errors": []
            }
        
        Error tolerance: Continue if some tables fail (partial sync ok)
                       But surface errors for visibility
        SLA: <30 minutes for 1000-table schema
        """
        pass
    
    async def health_check(self) -> HealthStatus:
        """
        Periodic health check (called every 5 minutes).
        
        Returns:
            {
              "status": "healthy" | "degraded" | "error",
              "last_query_latency_ms": 340,
              "consecutive_failures": 0,
              "last_failure_at": "2026-03-13T14:25:00Z",
              "recommendation": "..."  # E.g., "Connection pool exhausted"
            }
        
        Used for: Fleet health dashboard + alerting
        SLA: <5 seconds
        Timeout action: Mark as error if >5s
        """
        pass
    
    def get_connection_info(self) -> ConnectionInfo:
        """
        Return connection metadata (for ops/support).
        
        Returns:
            {
              "connector_id": "salesforce_prod_eur",
              "type": "salesforce",
              "instance_url": "https://myinstance.salesforce.com",
              "api_version": "v57.0",
              "authenticated_as": "zta-sa@company.salesforce.com",
              "last_login_at": "2026-03-13T14:22:00Z",
              "rate_limit_remaining": 4200,
              "rate_limit_reset_at": "2026-03-14T00:00:00Z"
            }
        
        Privacy: Never return passwords or API keys (stored in vault only)
        """
        pass


class QueryResult:
    """Standard result struct returned by execute_query()"""
    rows: List[Dict[str, Any]]        # Result rows
    count: int                         # Number of rows returned
    latency_ms: int                    # Query execution time
    total_rows_available: int          # Total if not truncated
    truncated: bool                    # True if result set was limited
    warnings: List[str]                # E.g., ["Query truncated to 10K rows"]


class ConnectionStatus:
    """Status struct returned by connect()"""
    status: str                        # "connected" | "error"
    response_time_ms: int
    error: Optional[str]               # Error message if status="error"
    is_temporary: bool                 # True if error might resolve (retry-able)


class TestResult:
    """Result struct for test_connection()"""
    status: str                        # "healthy" | "degraded" | "error"
    latency_ms: int
    error: Optional[str]


class ScopeContext:
    """Context passed to execute_query() for scope enforcement"""
    tenant_id: str
    user_id: str
    user_role: str
    applied_filters: Dict              # Row/field filters already applied


class SyncResult:
    """Result struct for sync()"""
    status: str                        # "complete" | "partial" | "failed"
    tables_discovered: int
    tables_added: int
    tables_removed: int
    fields_changed: int
    duration_ms: int
    errors: List[str]


class HealthStatus:
    """Status struct for health_check()"""
    status: str                        # "healthy" | "degraded" | "error"
    last_query_latency_ms: int
    consecutive_failures: int
    last_failure_at: Optional[str]     # ISO timestamp
    recommendation: str                # Actionable guidance
```

**Error Codes (Standard Across All Connectors):**

```
SUCCESS (200):
  • Connection established
  • Query executed successfully
  • Schema discovered

CLIENT_ERROR (400):
  • Invalid query syntax
  • Connection config missing required field
  • Timeout expecting response

AUTHENTICATION_ERROR (401):
  • Invalid credentials
  • Token expired
  • MFA required

AUTHORIZATION_ERROR (403):
  • User lacks permission to access table
  • IP whitelist violation

NOT_FOUND (404):
  • Table does not exist
  • Schema not available

RATE_LIMITED (429):
  • Connector's API rate limit exceeded
  • Retry after X seconds

SERVER_ERROR (500):
  • Data source is unavailable
  • Internal server error
  • Service degraded

TIMEOUT (504):
  • Query execution exceeded timeout
  • Connection establishment exceeded timeout
```

**Implementation Requirements:**

```
Every connector implementation must:

1. Implement all 8 methods from ConnectorBase
2. No blocking I/O in __init__ (use async connect())
3. All I/O must be async (asyncio-compatible)
4. Respect timeouts (never hang)
5. Use scope_context in execute_query() (no direct access to unscoped data)
6. Return standard error codes
7. Log every operation (for audit trail)
8. Support connection pooling (reuse connections, limit pool size)
9. Handle rate limiting (return 429, don't retry internally)
10. No customer data in logs or error messages
11. Support both test mode (small queries) and production mode
12. Implement circuit breaker pattern (fast-fail after N consecutive errors)

Phase 4 Certification Harness Tests All Connectors Against:
  1. test_connection() succeeds <5s
  2. discover_schema() retrieves all tables and fields
  3. execute_query() returns correct result set
  4. Timeout handling: Query >timeout_seconds aborts cleanly
  5. Error handling: Invalid query returns 400, not exception
  6. Rate limiting: 429 on API limit, caller retries
  7. Scope enforcement: Row/field masking applied correctly
  8. Latency P95: <500ms for typical queries
  9. Reliability: 10,000 sequential queries with 0 hard failures
  10. Schema change detection: New field appears in schema <10min
```

**Example: Custom Connector Implementation**

```python
# Customer implements their proprietary database

class ProprietaryDBConnector(ConnectorBase):
    async def connect(self, timeout_seconds: int = 30) -> ConnectionStatus:
        """Connect to customer's internal database"""
        try:
            pool = asyncpg.create_pool(
                host=self.config['host'],
                user=self.config['user'],
                password=self.config['password'],
                timeout=timeout_seconds
            )
            # Test query to verify connectivity
            async with pool.acquire() as conn:
                result = await conn.fetchval('SELECT 1')
            return ConnectionStatus(status="connected", response_time_ms=...)
        except asyncpg.UnavailableCredentialError:
            return ConnectionStatus(status="error", error="Invalid credentials")
        except asyncio.TimeoutError:
            raise TimeoutError(f"Connection exceeded {timeout_seconds}s")
    
    async def execute_query(self, compiled_query: str, scope_context, 
                          timeout_seconds: int = 60) -> QueryResult:
        """Execute query with scope context"""
        # compiled_query already has row/field filters applied
        async with self.pool.acquire() as conn:
            try:
                rows = await asyncio.wait_for(
                    conn.fetch(compiled_query, timeout=timeout_seconds),
                    timeout=timeout_seconds
                )
                return QueryResult(
                    rows=rows,
                    count=len(rows),
                    latency_ms=...,
                    warnings=[]
                )
            except asyncio.TimeoutError:
                raise TimeoutError(f"Query exceeded {timeout_seconds}s")
    
    # ... implement other 6 methods similarly
```

**Connector Marketplace Registration:**

```yaml
# connectors/proprietary-db/connector.yaml

name: proprietary-db
display_name: Proprietary DB
version: 1.0.0
author: "Company Engineering"
description: "Connect to the proprietary enterprise database"

interface_version: "1.0"  # Must match ConnectorBase version

config_schema:
  required:
    - host
    - user
    - password
  optional:
    - port
    - database
    - ssl_verify

documentation:
  README: "README.md"
  setup_guide: "INSTALL.md"
  troubleshooting: "TROUBLESHOOT.md"

certification:
  status: "certified"  # Or "preview"
  certified_date: "2026-03-13"
  tested_on_versions: ["1.0.0", "1.0.1"]
  support_sla: "24 hours"
  contact: "connector-support@company.com"

dependencies:
  python: ">=3.9"
  asyncpg: ">=0.27.0"
```

This becomes the foundation for:
- Phase 4: Certification harness tests all connectors against this contract
- Phase 5+: Custom connectors follow this interface
- Connector marketplace: Community connectors must satisfy this contract
- Support: Issues triage against which method is failing

---

### Query Compilation Pipeline

**Step 1: Intent Extraction**
```
Input: "Show me loan applications from the automotive sector in Q4 with default rates"

Output:
{
  "intent_type": "PORTFOLIO_ANALYSIS",
  "entities": [
    {"name": "loan_applications", "type": "primary_resource"},
    {"name": "applications", "type": "alias"}
  ],
  "filters": [
    {"dimension": "sector", "operator": "=", "value": "automotive", "confidence": 0.99},
    {"dimension": "period", "operator": "WITHIN", "value": "Q4_2025", "confidence": 0.98}
  ],
  "metrics": [
    {"name": "count", "confidence": 0.99},
    {"name": "default_rate", "confidence": 0.97}
  ],
  "confidence_score": 0.98,
  "fallback_strategies": [
    "If 'automotive' not recognized: ask for clarification",
    "If 'default_rate' not available: substitute 'loss_rate'"
  ]
}
```

**Step 2: Scope Validation**
```
User: John Doe (Commercial Loan Officer, Boston office)
Intent entities: [loan_applications, sector]

Checks:
  1. RBAC: Commercial_Loan_Officer role authorized for loan queries? YES
  2. ABAC: John assigned "Automotive" sector? YES
  3. ABAC: John's office = Boston? YES (portfolio scope: Boston + Senior oversight)
  4. Temporal: Access time = business hours? YES
  5. Risk-based: MFA verified? YES; Device trusted? YES

Authorization decision: APPROVED with scope filters applied
  Applied filters: WHERE office='Boston' AND sector='Automotive' AND date BETWEEN Q4_start AND Q4_end
```

**Step 3: Schema Mapping**
```
Query terms → Database schema:
  "loan_applications" → tables: [loans, loan_applications]
  "sector" → columns: [borrower.industry_code, loan.source_of_funds_classification]
  "default rates" → derived metric: (COUNT(WHERE status='Defaulted') / COUNT(ALL)) * 100
  
Recommended mapping:
  SELECT COUNT(*) as total_applications,
         COUNT(CASE WHEN status IN ('Defaulted','Charged-off') THEN 1 END) as defaults,
         ROUND(COUNT(CASE WHEN status IN ('Defaulted','Charged-off') THEN 1 END) * 100.0 / COUNT(*), 2) as default_rate
  FROM loans
  WHERE originating_office = 'Boston'
    AND borrower_industry_code = 'Automotive'
    AND origination_date BETWEEN '2025-10-01' AND '2025-12-31'
  GROUP BY nothing (aggregate only)
```

**Step 4: Policy Enforcement**
```
Policies to apply:
  1. Field-level: Hide loan pricing (margin, rate_override) → Field masking applied
  2. Row-level: User can only see own office portfolio → Row filter applied
  3. Aggregation: Results only (no detail rows) → Check: Intent=AGGREGATION ✓

SQL after policy enforcement:
  SELECT COUNT(*) as total_applications,
         COUNT(CASE WHEN status IN ('Defaulted','Charged-off') THEN 1 END) as defaults,
         ROUND(...) as default_rate,
         -- pricing fields EXCLUDED (FLS policy)
         ARRAY_AGG(DISTINCT industry_subsector) as sectors
  FROM loans
  WHERE originating_office = 'Boston'  -- RLS policy
    AND borrower_industry_code = 'Automotive'
    AND origination_date BETWEEN '2025-10-01' AND '2025-12-31'
    AND ... (no unauthorized detail access)

No individual loan details in result (aggregation-only compliance check)
```

**Step 5: Execution**
```
Database: PostgreSQL (Boston office credit database)
Execution plan: Seq scan → Filter → Aggregate
Estimated cost: 42.5 (2,100 page reads expected)
Indexed columns: originating_office (yes), origination_date (yes), industry_code (no → recommend)
Latency estimate: 280ms
```

**Full Result:**
```
default_rate_q4_2025: 3.2%
total_applications: 147
total_defaults: 5
confidence: High (sourced from authoritative tables)
```

---

## Success Metrics and Acceptance Criteria

### Phase 1: Architecture Freeze
| Metric | Target | Validation |
|--------|--------|-----------|
| Components documented | 100% | All 6 layers (A-F) have specifications |
| Feature-component mapping | 100% | Traceability matrix complete; no orphan features |
| Security review sign-off | Yes | CISO approves trust boundaries |
| Ambiguity score | 0 | Every component interaction has defined contract |

### Phase 2: Security Hardening
| Metric | Target | Validation |
|--------|--------|-----------|
| Production auth methods | SAML, OIDC, OAuth | No mock auth remaining |
| Service mTLS coverage | 100% | All internal calls mTLS-encrypted |
| Secret rotation success | >99.9% | Automated, zero manual failures observed over 30 days |
| Egress whitelist enforcement | 100% | Port scan + network policy audit |
| Security scan pass rate | 100% | SAST, dependency check, zero high CVEs |
| Penetration test findings | 0 critical, 0 high | Internal or third-party pentest report |

### Phase 3: Zero-Learning Enforcement
| Metric | Target | Validation |
|--------|--------|-----------|
| Model parameter immutability | 100% over 50K queries | Checksum verification pre/post batch |
| Customer data retention time | <24 hours post-session | Audit log confirms deletion within SLA |
| Tenant data isolation violations | 0 | Cross-tenant query attempts blocked with audit |
| Compliance attestation | Signed proof | Legal document ready for regulators |

### Phase 4: Connector Productionization
| Metric | Target | Validation |
|--------|--------|-----------|
| Connector availability | 99.95% | Uptime monitoring over 30 days |
| Schema change detection latency | <10 minutes | Automated test: add field, verify alert |
| Query success rate per connector | >99.9% | 10,000 sequential queries per connector |
| P95 query latency | <500ms | Load test with 100 concurrent users |
| Certified connectors operational | 5 (SQL + 4 new) | All 5 pass certification harness |

### Phase 5: Interpreter Maturity
| Metric | Target | Validation |
|--------|--------|-----------|
| Intent classification accuracy | >95% on top 20 intents | Validation across 5 domains |
| Domain-specific hardcoding | 0 instances | Code review + semantic analysis |
| Out-of-distribution graceful handling | 100% of >OOD queries | No hallucinations, returns "I don't understand" |
| Cross-domain conflict resolution | 100% correct | Test suite of ambiguous queries across domains |
| New domain onboarding time | <2 weeks | Validated with sandbox domain |

### Phase 6: Agentic Completion
| Metric | Target | Validation |
|--------|--------|-----------|
| Template operationalization | 12/12 | All templates executable (zero placeholders) |
| Action execution latency | <5 seconds | Automated load test |
| Approval SLA compliance | 95% within 4 hours | Monitor 100+ approval requests |
| Rollback success rate | >99% | Rollback tested for each template |
| Audit trail completeness | 100% | Every action step logged, tamper-proof |

### Phase 7: Compliance Operations
| Metric | Target | Validation |
|--------|--------|-----------|
| DSAR turnaround time | 95% ≤ 10 days, SLO 7 days | Track 50+ DSAR requests |
| Erasure verification | 100% deletion proof | Query confirms data unrecoverable |
| Breach investigation report latency | <4 hours | Forensic report generation time |
| Compliance audit findings | 0 violations | Internal + external audit results |

### Phase 8: Admin Surface Completion
| Metric | Target | Validation |
|--------|--------|-----------|
| Self-service operation success | >95% first-time | UAT with 5+ non-technical admins |
| Engineering escalations required | 0 per month | Ops log tracking |
| Documentation completeness | 100% | Every operation has step-by-step guide |
| Rollback capability | All operations | Undo available for all changes <30 days |

### Phase 9: Performance Hardening
| Metric | Target | Validation |
|--------|--------|-----------|
| P95 latency (sustained) | <1000ms | 8-hour load test, 100 concurrent users |
| P99 latency | <2000ms | Same load test conditions |
| Error rate under peak load | <0.1% | Peak load scenario results |
| Graceful degradation | Operational under 10x peak | Queuing, no data loss, no policy bypass |

### Phase 10: Pilot Validation
| Metric | Target | Validation |
|--------|--------|-----------|
| Feature adoption rate | >90% by target users | Usage analytics over 8 weeks |
| Security incidents | 0 | No breaches, policy bypasses, or violations |
| User support requests | <5% of user base | Support ticket analysis |
| Compliance audit findings | 0 critical, ≤2 medium | External audit report |
| Customer recommendation | "Production-ready" | Signed agreement for full deployment |

---

## Operational Runbooks

### Runbook 1: User Provisioning (Non-Technical Admin)

**Scenario:** Hospital adds 3 new clinical staff to Cardiology department

**Steps:**
```
1. Navigate: https://zta-ai.hospital.local/admin → Users → [Add Users]

2. Bulk import (recommended for >1 user):
   a. Download CSV template: [Download]
   b. Fill in columns:
      | Email | First_Name | Last_Name | Department | Start_Date |
      | ... |
   c. Upload: [Choose file] → cardiology_new_staff.csv
   d. Verify: Shows 3 users identified
   e. Click [Process]

3. Configure access (automatic or manual):
   Automatic:
     a. Selected role: Clinical_Provider_Cardiology (inherits all Cardiology policies)
     b. [Confirm]
   
   Manual:
     a. For each user: [Configure Access]
     b. Select role: Clinical_Provider_Cardiology
     c. Verify scope: Department=Cardiology, patient_list_scope=assigned_patients
     d. Review masked fields: SSN (✓), Insurance (✓), Billing (✓)
     e. [Save]

4. Activate: [Send Activation Emails]
   System generates invitation links; staff logs in, sets password, enables MFA

5. Verification:
   a. Example: Dr. Sarah logs in
   b. Can see: 34 assigned patients (Cardiology)
   c. Cannot see: Billing details, SSN, pricing (policies enforced)
   d. Audit log shows: Sarah's first login, role assignment, scope applied
   
6. Email confirmation to admin:
   "3 users successfully provisioned to Cardiology
    Activation emails sent
    Audit evidence: log_2026_03_13_14_32_cardiology_provision.json"
```

**Estimated time:** 5 minutes
**Success indicator:** "Provisioning complete" + audit log generated

---

### Runbook 2: Field Masking Policy Update

**Scenario:** Hospital needs to mask patient medication list for non-clinical staff

**Steps:**
```
1. Problem identification:
   Compliance finds: Billing staff accidentally sees medication data (allowed for drug interactions, but shouldn't see)
   Decision: Mask medications for billing staff

2. Policy creation:
   Navigate: Admin → Policies → Field-Level Masking → [New Rule]
   
   a. Rule name: "Medications_Billing_Mask"
   b. Field to mask: patients.medications_current (entire field)
   c. Mask pattern: [REDACTED - See clinical notes for medication info]
   d. Who sees unmasked: Emergency, Clinical, Complince (with audit)
   e. Who sees masked: Billing, Collections, Patient Relations
   
3. Impact analysis:
   System calculates: 1,240 active billing users will be affected
   Existing queries: 340 will need re-execution (to apply new masking)
   
4. Approval workflow:
   a. Policy submitted to: Compliance Officer
   b. Officer receives notification
   c. Officer reviews: Who's affected? Why? When needed?
   d. Officer clicks: [Approve]
   e. Timestamp recorded: 2026-03-13 14:33:00

5. Deployment:
   System warnings: "Deployment will affect 1,240 users. Confirm? [Yes/No]"
   Click [Yes]
   
   Deployment proceeds:
     • Policy deployed to production (timestamp logged)
     • Cache invalidated for affected queries
     • Existing sessions continue (new masking applied to new queries)
     • New sessions active with masking immediately
   
6. Validation:
   Test users provisioned:
     a. Billing test user: Try to see medication list → [REDACTED] ✓
     b. Clinical test user: Try to see medication list → Full data shown ✓
   
7. Audit trail:
   Admin: sarah_torres@hospital.com
   Action: Created policy FLS_Medications_Billing
   Approved by: compliance_officer@hospital.com
   Deployed at: 2026-03-13 14:33:45
   Affected users: 1,240 billing staff
   Validation: Passed (2 test users verified)
   Proof: audit_2026_03_13_field_masking_deployment.json
```

**Estimated time:** 15 minutes (policy creation + approval + deployment)
**Rollback:** Available → [Disable Rule] (re-deploying original policy in <1 minute)

---

### Runbook 3: Handling a DSAR Request

**Scenario:** Patient John Smith requests all his medical records (GDPR/HIPAA)

**Steps:**
```
1. Request intake:
   a. DSAR portal: Patient submits request
      - Name: John Smith
      - Email verified: john.smith@email.com
      - Request type: "Full record export"
      - Deadline visible: 30 calendar days (GDPR)
   
2. Verification:
   a. System checks: Patient identity exists in system
   b. Eligibility: Yes, found patient record #12847 created 2024-03-15
   c. (If needed: Send OTP to verify email)
   
3. Automated processing:
   System scans all connected sources:
     • EHR (Epic): 145 visit records
     • Lab system: 32 lab results
     • Pharmacy: 18 prescriptions
     • Billing: 8 invoices
     • Analytics: 1,247 browsing events
     Total: 1,450 records collected
   
4. Data aggregation:
   a. Collect all records to staging area
   b. Organize by source:
      {
        "medical_records": [...145 records],
        "lab_results": [...32 records],
        ...
      }
   c. Redact other patients mentioned (if any)
   d. Create human-readable format (PDF + CSV)
   
5. Compliance review:
   a. Audit: All records are from authorized sources? Yes
   b. Sensitivity check: Any records we must withhold? 
      (e.g., other patients' notes mentioning John?) 
      → Found 2 provider notes mentioning John; redacting names
   c. Final check: Legal review? (Auto-approved for standard DSAR)
   
6. Delivery:
   a. Generate secure delivery link (1-time use, 30-day expiry)
   b. Send email: "Your DSAR export is ready. Download: [link]"
   c. Log: Delivery timestamp
   
7. Verification:
   a. John clicks link, downloads export (2026-03-13 10:15:00)
   b. System confirms: "John Smith download verified at 2026-03-13 10:15:00"
   
8. Compliance documentation:
   a. Generate proof:
      Request ID: DSAR_2026_0347
      Subject: John Smith (Patient #12847)
      Request received: 2026-03-12 09:15:00
      Processing completed: 2026-03-13 09:45:00
      Delivered: 2026-03-13 10:00:00
      Recipient access: 2026-03-13 10:15:00
      Legal deadline: 2026-04-11 23:59:59
      Status: ✓ COMPLETE (28 days early)
      Proof file: dsar_2026_0347_compliance_proof.json (signed)
   
   b. Regulatory file: Saved for HIPAA/GDPR audit
       → Ready to show regulator: "We processed DSAR within deadline"
```

**Timeline:** Auto-complete in 2-4 hours (waiting for human compliance review)
**Escalation:** If John claims he didn't receive it → Check download logs, resend if needed

---

### Runbook 4: Emergency Access (Break-Glass Procedure)

**Scenario:** Emergency nurse needs access to patient record outside normal scope

**Steps:**
```
1. Trigger request:
   Nurse: "Patient in ER bay 3 is unconscious; I need full access to history"
   
   Admin interface → Escalations → [Request Emergency Access]
   a. User: Nurse Sarah Chen
   b. Patient: <search patient name/ID>
   c. Duration: 1 hour (or until end of shift)
   d. Justification: "Patient unconscious; need full medical history"
   e. Approval level: Charge Nurse (immediate approval)
   
2. Approval (fast-tracked):
   a. Charge nurse receives alert (mobile push + email)
   b. Reviews justification
   c. Clicks [Approve]
   d. System: Role expanded immediately
   
3. Access granted (time-limited):
   Sarah can now access:
     ✓ Full patient history
     ✓ All clinical data
     ✓ Medication allergies
     Duration: 1 hour
   
   Background processing:
     • Real-time audit logging (every access recorded)
     • Countdown timer: 45 minutes remaining
     • Automatic revocation at 1 hour
   
4. Post-incident review (required):
   a. Once emergency resolves, charge nurse reviews:
      - Did Sarah access only the emergency patient? Yes
      - Was duration appropriate? Yes (25 minutes used)
   b. Compliance officer receives audit alert:
      Alert: Emergency access granted to Sarah (1 occurrence) for patient rec #54321
      Review status: Approved by charge nurse
      Audit evidence: [View logs]
   
5. Audit documentation:
   Event log entry:
     User: Sarah Chen (RN)
     Event: Emergency access to patient #54321
     Justification: Patient unconscious in ER, needed history
     Approval: Manually approved by Charge Nurse James
     Duration: 25 minutes (approved 60 min)
     Records accessed: 8 (history, medications, allergies)
     Post-access review: Approved (appropriate access)
     Timestamp: 2026-03-13 14:47-15:12
     Proof: audit_emergency_access_2026_03_13_14_47.json
```

**Response time:** <30 seconds for approval
**Audit trail:** Comprehensive review needed within 24 hours

---

### Runbook 5: Incident Response - Unauthorized Access Attempt

**Scenario:** System detects suspicious access pattern (employee accessing records they shouldn't)

**Steps:**
```
1. Alert triggered:
   System detects: Daniel Lopez (Finance) queried clinical records for 340 patients
   
   Policy check:
     Role: Finance_Analyst
     Scope: Financial data only (NOT clinical)
     Query: SELECT * FROM patients WHERE clinical_status = 'Active'
     Decision: ✗ BLOCKED (no scope)
   
   Alert severity: HIGH
   Alert recipients: Compliance Officer, IT Security, HR

2. Investigation initiated:
   Compliance Officer receives alert:
   "UNAUTHORIZED ACCESS ATTEMPT
    User: Daniel Lopez (Finance_Analyst)
    Attempted resource: Patient clinical records (340 records)
    Policy blocking: RLS_clinical_data_restricted
    Block timestamp: 2026-03-13 14:25:00
    [View forensic details]"
   
3. Forensic analysis:
   Click: [View forensic details]
   
   System provides:
     • Access timeline: Today at 14:25:00, previous attempts at 13:15:00, 12:30:00
     • Pattern: Escalating access attempts over 2 hours
     • Query history: First attempt was 100 records, then 250, then 340
     • Success/fail status: ALL DENIED (policy enforced)
     • No data actually accessed
   
   Compliance assessment:
     ✓ No breach occurred (policy enforced)
     ⚠️ Repeated attempts suggest intent
     ⚠️ Outside normal business pattern
   
4. Containment:
   Decision: Immediately disable Daniel's access pending investigation
   
   Action: [Disable Account]
   a. System revokes all access tokens
   b. Active sessions terminated
   c. Database access blocked
   d. Email notification: "Your account has been disabled. Contact IT Security."
   
5. Internal investigation:
   a. Contact Daniel: "We detected access attempts outside your role scope. 
      Session disabled pending review."
   b. Check if account was compromised (password reset, unusual login location)
   c. Review: Was Daniel authorized to access clinical data? No.
   d. Interview: Why the attempts? 
      Response: "My manager asked me to run a report. I didn't think to ask for help."
   e. Find actual owner: Who should run clinical reports? Analytics team
   
6. Resolution:
   a. Re-enable Daniel's account (after investigation clears)
   b. Process request through proper channels (manager → Analytics team)
   c. Training: "Use the proper workflow for cross-team requests"
   
7. Documentation:
   Incident report:
     ID: INC_2026_0356
     Date: 2026-03-13
     Detection: Automated policy enforcement
     Status: RESOLVED (no breach, unauthorized access prevented)
     Root cause: User confusion about access request workflow
     Corrective action: User training, workflow clarification
     Proof: incident_2026_0356_analysis.json
     
   Regulatory filing: Not required (breach did not occur; control effective)
```

**Resolution time:** <2 hours for immediate containment, <1 day for investigation
**Regulatory impact:** Proof that control prevented breach (risk: LOW, control: EFFECTIVE)

---

## Testing Strategy

### Unit Testing (Component Level)

**Intent Extraction Module:**
```
Test suite: test_intent_extractor.py

Test cases:
  1. banking_query_commercial_loan_filter
     Input: "Show loans from the automobile sector approved in Q4"
     Expected output:
       {
         "intent": "FILTERED_AGGREGATION",
         "entities": ["loans"],
         "filters": [
           {"dimension": "sector", "value": "automobile"},
           {"dimension": "approval_date", "value": "Q4"}
         ],
         "confidence": 0.97
       }
     Pass: Intent and filters correctly identified

  2. healthcare_query_out_of_distribution
     Input: "What's the weather forecast for tomorrow?"
     Expected output:
       {
         "confidence": 0.05,
         "fallback": "I don't understand this query. Can you rephrase?"
       }
     Pass: Out-of-distribution detected, no hallucination

  3. multi_turn_context_preservation
     Input 1: "Show me active patients"
     Input 2: "Filter to those over 65" (should reference prior result)
     Expected: Second query recognized as filter on first result
     Pass: Context correctly maintained

  4. domain_agnostic_aggregation
     Input (Banking): "Average loan size by region"
     Input (Manufacturing): "Average production per facility by region"
     Expected: Both correctly map to generic AGGREGATION with GROUP_BY
     Pass: Domain-agnostic understanding verified
```

**Policy Enforcement Module:**
```
Test suite: test_policy_enforcement.py

Test cases:
  1. rbac_role_denial
     User role: Billing_Analyst
     Query: SELECT * FROM clinical_data
     Expected: DENIED (role has no clinical permission)
     Pass: RBAC enforcement working

  2. field_level_masking
     User: Finance staff
     Query: SELECT ssn, name FROM patients
     Expected result: SELECT [MASKED], name FROM patients
     Verification: SSN column masked in result, name visible
     Pass: FLS masking applied

  3. row_level_scope
     User: Dr. Sarah (assigned to Cardiology)
     Query: SELECT * FROM patients
     Expected: Filtered to WHERE department = 'Cardiology'
     Verification: Count matches assigned patient list only
     Pass: RLS scope applied

  4. multiple_policy_interaction
     Policies: RBAC (allow clinical access) + FLS (mask billing) + RLS (own department)
     User: Nurse in Cardiology
     Query: SELECT * FROM patients WHERE department = 'Cardiology'
     Expected: All 3 policies compose correctly (RBAC passes, FLS masks billing, RLS scopes to dept)
     Pass: Policy composition verified
```

### Integration Testing (End-to-End Flows)

**Query Execution Flow:**
```
Test: end_to_end_query_with_policies

Setup:
  • User: Commercial loan analyst in Boston office
  • Data: Loan portfolio (500 loans, 10 fields)
  • Policies: RLS (own office only), FLS (mask pricing), temporal (business hours)

Test steps:
  1. User logs in (SAML auth)
  2. User submits: "Show me Q4 loan defaults by sector"
  3. Intent extraction (verify commercial context recognized)
  4. Policy evaluation (verify Boston scope applied)
  5. Query compilation (verify pricing fields excluded)
  6. Database execution (verify query runs <1 second)
  7. Result return (verify 3 sectors shown, 8 defaults visible)
  8. Audit logging (verify event recorded)

Verification:
  ✓ Intent correctly parsed
  ✓ Scope filter applied (Boston office only → excludes 450 loans)
  ✓ Pricing fields masked in response
  ✓ Latency <1 second
  ✓ Audit event shows policy applied
```

**DSAR Workflow:**
```
Test: dsar_end_to_end_execution

Setup:
  • Customer: John Smith
  • Systems: EHR, Billing, Analytics
  • Compliance: GDPR, 30-day deadline

Test steps:
  1. Submit DSAR: "Give me all my records"
  2. Verify identity (OTP sent to email)
  3. Identify customer in all systems (scan EHR, Billing, Analytics)
  4. Collect records (verify 200+ records retrieved)
  5. Aggregate (organized by system)
  6. Redact (find any other customers mentioned, redact names)
  7. Deliver (secure portal created, link sent)
  8. Verify receipt (confirm John downloaded)
  9. Document (compliance proof created)

Verification:
  ✓ Zero records missed (all systems scanned)
  ✓ No data from other customers exposed (redaction verified)
  ✓ Delivered within 7 days (SLO met)
  ✓ Forensic proof complete (regulator-ready)
```

### Performance Testing

**Load Test: 100 Concurrent Users**
```
Test harness: perf_test_loader.py

Configuration:
  • Duration: 1 hour
  • Users: 100 concurrent
  • Query rate: 2 queries/minute per user (200 total queries/minute)
  • Query mix: 60% aggregations, 30% filters, 10% complex joins
  • Scenarios: Peak hours, steady state

Metrics collected:
  • P50, P95, P99 latency
  • Error rate
  • Throughput (queries/second)
  • Database connection pool usage
  • Cache hit rate

Success criteria:
  • P95 latency: <1000ms ✓
  • Error rate: <0.1% ✓
  • No memory leaks (heap size stable)
  • Database connections: <80% of pool limit
```

**Tail Latency Analysis (P99, P99.9):**
```
Test: tail_latency_optimization

Baseline measurements:
  P99: 2,340ms (target: <2000ms)
  P99.9: 4,100ms (target: <3000ms)

Optimization targets:
  1. Cache schema metadata (reduce p99 from 2.3s to <2s) → Result: 1,850ms ✓
  2. Connection pooling warmup (reduce spikes) → Result: 500ms improvement ✓
  3. Query plan optimization (reduce database time) → Result: 600ms improvement ✓
  Final P99: 1,650ms ✓
  Final P99.9: 2,400ms ✓
```

### Security Testing

**Penetration Test: Auth Bypass**
```
Test: auth_bypass_attempt

Scenarios:
  1. SQL injection in credentials field
     Attempt: email' OR '1'='1'; --
     Expected: Rejected (parameterized queries used)
     Result: ✓ BLOCKED

  2. Token expiration boundary
     Create token, wait until expiry timestamp
     Attempt: Use token at expiry+1 second
     Expected: Token rejected, re-auth required
     Result: ✓ BLOCKED

  3. MFA bypass
     Attempt: Disable MFA via settings without confirmation
     Expected: Require current MFA code to disable
     Result: ✓ BLOCKED

  4. Cross-tenant access
     User from Tenant A attempts: GET /api/v1/tenant/{tenant_b_id}/data
     Expected: Denied (403 Forbidden), policy enforced
     Result: ✓ BLOCKED
```

**Policy Bypass Attempts:**
```
Test: policy_enforcement_robustness

Scenarios:
  1. Direct database access (bypass API)
     Attempt: Connect directly to PostgreSQL using leaked credentials
     Expected: Database user has minimal permissions (SELECT only on public views)
     Result: ✓ BLOCKED (user cannot execute full query)

  2. Query modification (append SQL)
     Submitted query: "Show me sales"
     Attacker modifies to: "Show me sales; DROP TABLE users; --"
     Expected: Query execution fails (prepared statements)
     Result: ✓ BLOCKED

  3. Policy rule manipulation
     Attempt: Modify policy rule via API to remove masking
     Expected: Authentication required, audit logged, approval gated
     Result: ✓ BLOCKED (requires admin role + approval)
```

### Compliance Testing

**HIPAA Audit Log Verification:**
```
Test: hipaa_audit_logging

Scenarios:
  1. Access logging completeness
     Log all PHI access:
       ✓ User ID
       ✓ Timestamp (accurate to second)
       ✓ Query/operation
       ✓ Results accessed (count)
       ✓ Policy decision (allowed/denied)
     Verification: 100% of PHI access logged

  2. Break-glass access logging
     Emergency access to patient record → Logged as "EMERGENCY_ACCESS"
     Includes: Justification, approver, duration, what was accessed
     Post-review required: Within 24 hours
     Verification: All break-glass access has post-review

  3. Immutability
     Audit logs written to append-only storage
     Attempt to modify past log: FAILED (immutable)
     Verification: Logs tamper-proof
```

**GDPR Right-to-Erasure Verification:**
```
Test: gdpr_erasure_verification

Steps:
  1. Create test customer record (email, profile, transaction history)
  2. Submit erasure request
  3. System processes deletion
  4. Query 1: SELECT * FROM customers WHERE id = {deleted_id}
     Expected: 0 rows (deleted)
  5. Query 2: SELECT * FROM transactions WHERE customer_id = {deleted_id}
     Expected: 0 rows (deleted or pseudonymized)
  6. Query 3: Check backups (if access available)
     Expected: Flagged for future purging (if not yet auto-expired)
  
  Verification: ✓ Customer completely erased from live systems
              ✓ Proof of deletion generated
              ✓ Certificate signed (tamper-proof)
```

---

## Security & Audit Deep Dives

### Threat Model and Mitigations

**Threat 1: Unauthorized Data Access**
```
Attacker profile: Malicious insider (employee with low-risk role)
Attack goal: Extract sensitive customer data (medical records, financial data)

Attack vectors:
  A. SQL injection (database)
  B. Direct database access (credential theft)
  C. Policy manipulation (modify own access rules)
  D. Session hijacking (steal authentication token)

Mitigations:
  A. SQL injection:
     ✓ Parameterized queries (prepared statements) - prevents injection
     ✓ Input validation (strict whitelist) - only known intents allowed
     ✓ Query AST validation - reject complex/unusual patterns
     Testing: Pentest with 1,000+ injection payloads (0 successful)

  B. Direct database access:
     ✓ Database user has minimal permissions (SELECT on views only)
     ✓ Views enforce RLS/FLS policies in SQL (no bypass possible)
     ✓ Network isolation (database not accessible from internet)
     Testing: Attempt direct database query → BLOCKED (permission denied)

  C. Policy manipulation:
     ✓ Policy changes require admin role
     ✓ Admin role requires MFA + approval workflow
     ✓ All policy changes audited
     Testing: Non-admin attempts policy change → BLOCKED

  D. Session hijacking:
     ✓ Tokens expire (8-hour max, configurable)
     ✓ HTTPS only (TLS 1.3+)
     ✓ HttpOnly cookies (no JS access)
     Testing: Stolen token attempt after expiry → BLOCKED

Residual risk: LOW (controls effective)
```

**Threat 2: Data Exfiltration (Bulk Export)**
```
Attacker profile: Contractor with legitimate access who goes rogue
Attack goal: Export all customers' records to external media

Attack vectors:
  A. API bulk export (export all records via API)
  B. Database dump (extract backup)
  C. Network egress (copy to external server)

Mitigations:
  A. API bulk export:
     ✓ Export endpoint has rate limiting (max 100MB/hour per user)
     ✓ Exports are audited (who exported what, when)
     ✓ Large exports require approval
     Testing: Attempt export >100MB → Rate limited to next hour

  B. Database dump:
     ✓ No backup access for normal users
     ✓ Backup encryption (at-rest)
     ✓ Backup deletion governance (retention policy enforced)
     Testing: Attempt to read backup file → BLOCKED (encryption key unavailable)

  C. Network egress:
     ✓ Firewall rules whitelist known destinations only
     ✓ Unknown IPs blocked (egress policy)
     ✓ VPN/proxy required for external communication
     Testing: Attempt outbound to unknown IP → BLOCKED

Residual risk: MEDIUM (requires multiple policy violations or admin access)
Mitigation: Continuous monitoring + anomaly detection
```

**Threat 3: Model Poisoning (Data Leakage via Model)**
```
Attacker profile: Cloud model provider employee
Attack goal: Exfiltrate customer data via model parameters

Attack vector: Include customer data in LLM training, extract via prompt injection

Mitigation:
  ✓ Zero-learning guarantee: Model parameters frozen (read-only)
  ✓ Inference only: No backpropagation through customer data
  ✓ Data deletion: All customer data deleted within 24 hours
  ✓ Audit: Verify model parameters unchanged per query batch

Testing:
  • Run 50,000 customer queries
  • Checksum model parameters before + after
  • Result: ✓ Checksums identical (no learning)
  • Conclusion: Model poisoning impossible

Residual risk: VERY LOW (architectural control)
```

### Audit Evidence and Regulatory Proving

**HIPAA Compliance Proof Package:**
```
Document A: Notice of Privacy Practices
  • Explains how patient data is used
  • Signed by patient

Document B: Business Associate Agreement (BAA)
  • Executed between healthcare provider and ZTA-AI vendor
  • Defines responsibilities, security requirements
  • Signed by both parties

Document C: Security Controls Inventory
  • Technical controls: MFA, encryption, audit logging
  • Physical controls: Locked server room, visitor logs
  • Administrative controls: Access policies, training records

Document D: Audit Trail
  • 6 months of access logs (HIPAA requirement)
  • All PHI access documented
  • Break-glass access with post-review

Document E: Breach Investigation Report
  • If breach suspected:
    - Data identification (what was potentially exposed)
    - Risk assessment (was it actually at-risk)
    - Mitigation (have we contained it)
    - Notification plan (who needs to be told)

Document F: Annual Risk Assessment
  • Performed by Compliance Officer
  • Identifies vulnerabilities
  • Mitigation plan
  • Signed certification

Regulator evidence: Provide A-F to OHR/CMS for compliance audit
Expected outcome: ✓ Compliance confirmed (no violations found)
```

**GDPR Compliance Proof Package:**
```
Document A: Data Processing Agreement (DPA)
  • Executed between data controller (customer) and processor (ZTA-AI)
  • Standard contractual clauses (if data leaves EU)
  • Data subject rights (DSAR, erasure, consent)
  • Signed by both parties

Document B: Privacy Impact Assessment (DPIA)
  • Risk analysis: What customer data is processed and where
  • Mitigation: Controls in place to minimize risk
  • Conclusion: Risk acceptable with controls
  • Reviewed by Data Protection Officer

Document C: Consent Records
  • Customers' consent to data processing
  • Purpose limitation: Data used only for specified purpose
  • Withdrawal records: If customer opts out

Document D: DSAR Response Evidence
  • Last 12 months: All DSAR requests logged
  • Response time: <30 days (GDPR deadline)
  • Completeness: All records retrieved
  • Signed customer receipts

Document E: Erasure Proof
  • Deletion certificates signed by system
  • Verification queries showing data deleted
  • Retention policy applied (old data auto-deleted)

Document F: Breach Notification Log
  • If breach occurred: Notification sent within 72 hours
  • Individuals informed within 48 hours
  • Regulator notified

Regulator evidence: Provide A-F to ICO (UK) or CNIL (France) for audit
Expected outcome: ✓ Compliance confirmed (GDPR requirements met)
```

### Forensic Export Capability

**Compliance Officer Requests: "Generate audit evidence for Q1 2026"**

```
System response: Generating forensic export...

1. Audit log extract:
   • Start date: 2026-01-01
   • End date: 2026-03-31
   • Events: Query execution, policy decisions, access denials, breaks-glass
   
   Export format (tamper-proof CSV):
   timestamp | user_id | action | resource | policy_decision | result | reason
   2026-01-05 08:15 | user_123 | QUERY | patients | ALLOW | 50 rows | RBAC_clinical_access
   2026-01-05 08:22 | user_456 | QUERY | salary_data | DENY | 0 rows | INSUFFICIENT_PERMISSION
   ...

2. Access pattern analysis:
   • Top queried entities (patients, financial_records, inventory)
   • Most common queries (aggregations > filters > joins)
   • Policy violations (access denied events)
   • Break-glass usage (unusual access requiring approval)

3. Compliance violations:
   • Zero HIPAA violations: ✓
   • Zero GDPR violations: ✓
   • Zero unauthorized exports: ✓
   • Zero policy bypasses: ✓

4. DSAR/Erasure status:
   • DSAR requests: 47 received, 46 completed (1 pending)
   • Avg response time: 8.2 days (GDPR target: 30 days) ✓
   • Erasure executed: 12 requests, 100% verification passed
   • Avg erasure time: 2.1 days

5. Incident summary:
   • Unauthorized access attempts: 3 detected, 3 blocked
   • Policy denials: 127 (legitimate scope restrictions)
   • False alarms: 0
   • Actual breaches: 0

6. Signed attestation:
   "I, Compliance Officer Sarah Torres, certify that the above audit evidence
    accurately represents ZTA-AI's security and compliance posture for Q1 2026.
    All systems operated as designed. No unauthorized access or data breaches occurred.
    
    Signed: Sarah Torres
    Date: 2026-04-01
    Digital Signature: [Cryptographic signature verifiable by regulators]
    Proof ID: attestation_q1_2026_audit_proof.json"

Output file: audit_evidence_q1_2026.json (encrypted, signed)
→ Regulator can verify signature → Proof is authentic
→ Ready for regulatory submission
```

---

## Risk Register and Mitigations

| Risk | Impact | Likelihood | Mitigation | Owner |
|------|--------|-----------|-----------|-------|
| **LLM Provider Outage (Cloud SaaS)** | MEDIUM | LOW | AWS Bedrock fallback (automatically switch on Azure unavailability); latency degradation acceptable during failover; SLA: <5min recovery | Performance Lead |
| **Compliance conflict** (audit vs. erasure) | HIGH | MEDIUM | Legal-approved pseudonymization + key destruction strategy; separate testing per compliance framework | Compliance |
| **Security bypass** (hidden fallback paths) | CRITICAL | LOW | Safe-fail architecture + adversarial testing; code review + static analysis; pentest quarterly | Security |
| **Latency miss** (cannot achieve <1000ms) | MEDIUM | MEDIUM | Budgeted optimization per layer; load testing monthly; caching strategy; connector pooling | Perf Lead |
| **Connector instability** | HIGH | MEDIUM | Certification harness; circuit breakers; health monitoring; fallback connectors | Integration Lead |
| **Agentic safety** (unintended action) | CRITICAL | MEDIUM | Risk-class approvals; dry-run mode; rollback controls; action audit trail; policy gates | Workflow Lead |
| **Operational complexity** (on-prem) | HIGH | HIGH | Standardized deployment packs; compatibility matrix; runbooks; ops training | Operations |
| **Feature parity drift** | MEDIUM | LOW | Traceability matrix enforced as release gate; regression testing per phase | Product |
| **Tenant isolation failure** | CRITICAL | LOW | Network segmentation; database row-level isolation; audit verification; security scanning | Security |
| **Key compromise** (secrets leak) | CRITICAL | LOW | Vault-based secret rotation; encrypted at-rest; zero hardcoding; audit logs | Security |
| **Scalability bottleneck** | HIGH | MEDIUM | Load testing; auto-scaling validation; database optimization; connector optimization | Perf Lead |

---

---

## Deployment Architecture and Multi-Tenancy

### Deployment Topology

ZTA-AI operates in two deployment modes, both supported from Day 1:

**Mode 1: Cloud-Hosted SaaS (Managed by ZTA-AI)**
```
┌─────────────────────────────────────────────────┐
│ Customer Web/Mobile App                         │
│ (Browser or iOS/Android)                        │
└────────────────┬────────────────────────────────┘
                 │ HTTPS
                 ▼
┌─────────────────────────────────────────────────┐
│ ZTA-AI Cloud Infrastructure (AWS/Azure/GCP)     │
│                                                 │
│ ┌──────────────────────────────────────────┐   │
│ │ Load Balancer + WAF                      │   │
│ └────────────────┬─────────────────────────┘   │
│                  │ mTLS                        │
│ ┌────────────────▼─────────────────────────┐   │
│ │ Multi-Tenant Router Service              │   │
│ │ • Workspace routing                      │   │
│ │ • Session initialization                 │   │
│ │ • Tenant context injection               │   │
│ └────────────────┬─────────────────────────┘   │
│                  │ Per-tenant network          │
│ ┌────────────────▼─────────────────────────┐   │
│ │ Tenant Pods (Kubernetes)                 │   │
│ │ • API Gateway                            │   │
│ │ • Query Engine                           │   │
│ │ • Policy Enforcer                        │   │
│ │ • Audit Logger                           │   │
│ │ • Action Orchestrator                    │   │
│ └────────────────┬─────────────────────────┘   │
│                  │ Pod-local networking       │
│ ┌────────────────▼─────────────────────────┐   │
│ │ Data & Cache Layer (Per-Tenant)          │   │
│ │ • Redis (in-pod, ephemeral)             │   │
│ │ • PostgreSQL (tenant-isolated DB)        │   │
│ │ • Audit log storage (immutable)         │   │
│ └──────────────────────────────────────────┘   │
│                                                 │
└─────────────────────────────────────────────────┘
                 │ mTLS
                 ▼
┌─────────────────────────────────────────────────┐
│ Customer Data Infrastructure                    │
│ • SQL Database (customer-managed)              │
│ • ERP/Warehouse (Salesforce, SAP, BigQuery)    │
│ • Identity Provider (customer SAML/OIDC)       │
└─────────────────────────────────────────────────┘
```

**Mode 2: On-Premises Deployment (Customer-Managed)**
```
┌─────────────────────────────────────────────────┐
│ Customer Network (DMZ or Internal LAN)          │
│                                                 │
│ ┌──────────────────────────────────────────┐   │
│ │ ZTA-AI On-Prem Package                   │   │
│ │ (Tarball/Helm Chart)                     │   │
│ │                                          │   │
│ │ ┌────────────────────────────────────┐   │   │
│ │ │ Kubernetes Cluster (3+ nodes)      │   │   │
│ │ │                                    │   │   │
│ │ │ ┌════════════════════════════════┐ │   │   │
│ │ │ │ ZTA-AI Components              │ │   │   │
│ │ │ │ • API Gateway                  │ │   │   │
│ │ │ │ • Query Engine                 │ │   │   │
│ │ │ │ • Policy Enforcer              │ │   │   │
│ │ │ │ • Audit Logger                 │ │   │   │
│ │ │ │ • LLM Inference (Local)         │ │   │   │
│ │ │ └────────────────────────────────┘ │   │   │
│ │ │                                    │   │   │
│ │ │ ┌════════════════════════════════┐ │   │   │
│ │ │ │ Infrastructure                 │ │   │   │
│ │ │ │ • PostgreSQL (in-cluster)      │ │   │   │
│ │ │ │ • Redis (in-cluster)           │ │   │   │
│ │ │ │ • MinIO (S3-compatible storage)│ │   │   │
│ │ │ └────────────────────────────────┘ │   │   │
│ │ └────────────────────────────────────┘   │   │
│ │                                          │   │
│ │ ┌────────────────────────────────────┐   │   │
│ │ │ Update Agent                       │   │   │
│ │ │ • Checks for patches (daily)       │   │   │
│ │ │ • Auto-downloads (no internet)     │   │   │
│ │ │ • Validates signatures (offline)   │   │   │
│ │ │ • Applies updates (zero-downtime)  │   │   │
│ │ └────────────────────────────────────┘   │   │
│ └──────────────────────────────────────────┘   │
│                                                 │
└─────────────────────────────────────────────────┘
                 │ Connector
                 ▼
        Customer Data Sources
        (All local network)
```

### Deployment Artifacts and Deliverables

**SaaS Deployment (AWS):**
```
artifacts/
├── terraform/              # Infrastructure-as-code
│   ├── main.tf             # VPC, subnets, security groups
│   ├── kubernetes.tf       # EKS cluster definition
│   ├── networking.tf       # Private Link endpoints to customers
│   ├── rds.tf              # Multi-tenant PostgreSQL
│   └── variables.tf        # Configurable for different regions
├── helm/                   # Kubernetes package manager
│   ├── Chart.yaml          # Helm chart metadata
│   ├── values-prod.yaml    # Production values (CPU, memory, replicas)
│   ├── values-staging.yaml # Staging configuration
│   ├── templates/          # Kubernetes manifests
│   │   ├── deployment.yaml # Pod specifications
│   │   ├── service.yaml    # Load balancer configuration
│   │   ├── ingress.yaml    # URL routing
│   │   ├── networkpolicy.yaml # Tenant isolation rules
│   │   ├── secret.yaml     # Database credentials, API keys (encrypted)
│   │   └── configmap.yaml  # Policy rules, system config
│   └── README.md           # Deployment instructions
├── scripts/
│   ├── deploy.sh           # Deploy to Kubernetes cluster
│   ├── health-check.sh     # Verify cluster health
│   ├── backup.sh           # Full backup procedure
│   ├── restore.sh          # Restore from backup
│   ├── upgrade.sh          # Rolling update with zero downtime
│   └── rollback.sh         # Emergency rollback
└── monitoring/
    ├── prometheus-rules/   # Alert definitions (latency, errors, memory)
    ├── dashboards/         # Grafana dashboards (SLO, per-tenant metrics)
    └── alerts.yaml         # PagerDuty/OpsGenie integration
```

**On-Premises Deployment (Customer-Hosted):**
```
zta-ai-on-prem-[version].tar.gz
├── LICENSE.txt             # License key + expiration
├── legal/
│   ├── EULA.txt            # End-user license agreement
│   ├── SLA.txt             # Service level agreement
│   └── SUPPORT.txt         # Support terms
├── helm/
│   ├── Chart.yaml
│   ├── values-onprem.yaml  # Pre-configured for on-prem (resource limits)
│   └── templates/          # Same as SaaS but with on-prem defaults
├── installer/
│   ├── install.sh          # One-command installation
│   ├── config-wizard.py    # Interactive configuration
│   ├── validate.sh         # Pre-flight checks (Docker, disk, network)
│   ├── requirements.txt    # System requirements (16GB RAM min, 100GB disk)
│   └── examples/           # Example configurations (SQL Server, Oracle, Snowflake)
├── llm-bundles/            # Local LLM options (no external API calls)
│   ├── mistral-7b/         # Open-source LLM (quantized for on-prem)
│   ├── llama-2-13b/        # Alternative LLM
│   └── custom-endpoint.md  # Instructions for connecting local LLM
├── connectors/
│   ├── sql-server/         # Pre-built connector
│   ├── oracle/
│   ├── snowflake/
│   └── custom-connector.md # SDK for custom connectors
├── update-agent/
│   ├── agent.py            # Background process (checks daily, downloads offline)
│   ├── config.yaml         # Update server URL (air-gapped option)
│   └── signature-validation.py # Verifies authenticity before install
├── operations/
│   ├── admin-console/      # Internal dashboard (fleet management)
│   ├── backup-restore/     # Local backup procedures
│   ├── troubleshooting.md  # Common issues and fixes
│   └── support-logs.sh     # Collects logs for support (anonymized)
└── docs/
    ├── INSTALL.md          # Step-by-step installation
    ├── CONFIG.md           # Configuration reference
    ├── OPERATIONS.md       # Day-2 operations guide
    └── TROUBLESHOOTING.md  # Problem resolution
```

### Multi-Tenancy Architecture

**Tenant Isolation Boundaries:**

1. **Network Isolation:**
   - Each cloud tenant has dedicated Kubernetes security group
   - Egress restricted to their customer data sources + ZTA-AI services only
   - Ingress only from their IP whitelist (static or dynamic SAML OIDC provider)

2. **Database Isolation:**
   - Separate PostgreSQL schema per tenant (shared DB, isolated schema)
   - OR dedicated RDS instance per tenant (compliance requirement for HIPAA/GDPR)
   - Row-level security: `WHERE tenant_id = current_tenant_id`
   - No cross-tenant joins possible in application code (language-enforced via sqlc generics)

3. **Cache Isolation:**
   - Redis namespaced per tenant: `tenant_123:intent_cache:*`
   - Eviction is tenant-scoped
   - No cache poisoning possible (tenant_id verified on every cache access)

4. **Audit Log Isolation:**
   - Immutable append-only log per tenant
   - Encryption per tenant (distinct key per tenant)
   - Retention policy per tenant (configurable: 1 year, 6 years, 7 years per compliance need)

5. **Compute Isolation (On-Prem):**
   - Kubernetes namespaces per tenant (resource quotas enforced)
   - CPU limit: 2 cores per tenant (configurable per SLA)
   - Memory limit: 4GB per tenant (configurable)
   - Network policies prevent pod-to-pod communication outside namespace

### Tenant Routing: User → Instance

**Cloud SaaS Tenant Discovery:**

```
User accesses: https://zta-ai.company.com/workspace/BOSTON-CLINIC-2

Step 1: Load Balancer (AWS ALB)
  Receives HTTPS request
  Terminates TLS (certificate per customer domain)
  Forwards to Router Service

Step 2: Router Service
  Extract: workspace_code = "BOSTON-CLINIC-2"
  
  Query tenant registry:
    SELECT tenant_id, tenant_name, tier, region FROM workspaces
    WHERE workspace_code = 'BOSTON-CLINIC-2'
    
  Result: tenant_id = "tenant_a7f23", region = "us-east-1"
  
Step 3: Route to Tenant Pod
  Load balance across tenant_a7f23 pods (3 replicas)
  Select pod with lowest latency: pod_2
  
Step 4: Inject Tenant Context
  HTTP Header: x-tenant-id: tenant_a7f23
  HTTP Header: x-workspace-code: BOSTON-CLINIC-2
  
Step 5: All Downstream Services
  Every service reads x-tenant-id header
  Database: WHERE tenant_id = $TENANT_ID (automatic filtering)
  Cache: Use tenant_id as namespace prefix
  Audit: Every event tagged with tenant_id
  
Result: User session fully scoped to tenant_a7f23
        No data bleed possible (policy enforced at every layer)
```

**On-Premises Tenant Association:**

For single-tenant on-prem installations:
```
1. Install package
2. Configure: customer_name = "Boston Clinic", customer_code = "BC-001"
3. All sessions automatically map to BC-001 tenant
4. Multi-tenant on-prem (optional): Configure additional customers in config.yaml
```

---

## System Admin Console (Internal Operations Layer)

This is the surface through which ZTA-AI operations team operates the business. It's not user-facing; it's ops/business-facing.

### Dashboard 1: Fleet Health Board

**Purpose:** Real-time overview of all customer instances (SaaS only)

```
┌────────────────────────────────────────────────────┐
│ FLEET HEALTH BOARD (Last 24 hours)                  │
├────────────────────────────────────────────────────┤
│                                                    │
│ OVERALL STATUS: 🟢 HEALTHY                         │
│ • 127 active customers                             │
│ • 99.98% uptime (target: 99.95%) ✓                │
│ • 1 degraded, 0 incidents                         │
│                                                    │
├────────────────────────────────────────────────────┤
│ CUSTOMER CLUSTERS                                  │
├────────────────────────────────────────────────────┤
│                                                    │
│ us-east-1 (Primary)                               │
│   Status: 🟢 HEALTHY                              │
│   Tenants: 67 (Healthcare 45, Finance 22)        │
│   Availability: 99.97%                            │
│   Peak latency: 847ms (target: <1000ms) ✓        │
│   Alert: 0                                        │
│   Action: [Drill down]                            │
│                                                    │
│ eu-west-1 (GDPR)                                  │
│   Status: 🟡 DEGRADED                             │
│   Tenants: 34 (All Europe-based)                 │
│   Availability: 97.8% (⚠️ below SLA)             │
│   Peak latency: 1240ms (⚠️ above target)         │
│   Alert: 2 (see below)                            │
│   Action: [Drill down]                            │
│                                                    │
│ ap-southeast-1 (APAC)                             │
│   Status: 🟢 HEALTHY                              │
│   Tenants: 26 (All Asia-Pacific)                 │
│   Availability: 99.99%                            │
│   Peak latency: 723ms ✓                          │
│   Alert: 0                                        │
│   Action: [Drill down]                            │
│                                                    │
├────────────────────────────────────────────────────┤
│ CRITICAL ALERTS (Past 24 Hours)                   │
├────────────────────────────────────────────────────┤
│                                                    │
│ 🔴 CRITICAL (1):                                  │
│    Tenant: HealthCorp International               │
│    Alert: Database latency spike to 3200ms        │
│    Duration: 12 minutes (2:15am-2:27am)          │
│    Impact: 1,200 queries backlogged               │
│    Root cause: Index missing on audit_logs table │
│    Action: [View Details] [Auto-Mitigate]        │
│                                                    │
│ 🟡 WARNING (2):                                   │
│    Tenant: EuroBank AG                            │
│   Alert: Connector error rate 8.2% (target <1%)  │
│    Duration: 4 hours (intermittent)              │
│    Root cause: Salesforce API rate limit         │
│    Action: [View Details] [Contact Tenant]       │
│                                                    │
│    Tenant: RetailChain Ltd                       │
│    Alert: Audit log storage 87% capacity         │
│    Duration: Sustained (growing daily)           │
│    Root cause: Unusual query volume               │
│    Action: [View Details] [Expand Capacity]      │
│                                                    │
├────────────────────────────────────────────────────┤
│ SLO COMPLIANCE (Past 30 Days)                     │
├────────────────────────────────────────────────────┤
│                                                    │
│ Availability: 99.96% (target 99.95%) ✓           │
│ Latency P95: 945ms (target <1000ms) ✓            │
│ Error rate: 0.08% (target <0.1%) ✓              │
│ DSAR turnaround: 8.2 days (target 10 days) ✓    │
│                                                    │
└────────────────────────────────────────────────────┘
```

### Dashboard 2: Per-Customer Deep Dive

**Purpose:** Operational details for a single customer

```
┌────────────────────────────────────────────────────┐
│ CUSTOMER: HealthCorp International                 │
│ Tenant ID: tenant_h7x2q                            │
│ Contract: Enterprise, 3-year, $500K/year          │
│ SLA: 99.9% uptime, <1200ms P95, 24/7 support      │
│ Region: us-east-1                                  │
│ Data residency: US only (HIPAA requirement)        │
│ Go-live: 2025-03-15 (27 days ago)                 │
│                                                    │
├────────────────────────────────────────────────────┤
│ CURRENT STATUS (This Hour)                        │
├────────────────────────────────────────────────────┤
│                                                    │
│ Status: 🟢 HEALTHY                                │
│ Users online: 247 / 1,200 licensed                │
│ Active queries: 8                                  │
│ Query rate: 150 queries/hour (typical 180)        │
│ Average latency: 620ms (excellent)                │
│ Error rate: 0.0%                                   │
│ Connectors: 3 (EHR, Lab, Billing)                 │
│   • EHR: 🟢 OK, latency 240ms                     │
│   • Lab: 🟢 OK, latency 180ms                     │
│   • Billing: 🟡 Slow, latency 890ms (unusual)    │
│                                                    │
├────────────────────────────────────────────────────┤
│ USAGE METRICS (Past 30 Days)                      │
├────────────────────────────────────────────────────┤
│                                                    │
│ Total queries: 245,000                            │
│ Peak day: 2026-03-18 (8,900 queries)             │
│ Peak hour: 2026-03-18 14:00-15:00 (340 queries)  │
│ Average queries/day: 8,167                        │
│ Usage trend: ↑ 8% week-over-week (ramping up)    │
│                                                    │
│ Query breakdown:                                  │
│   • Aggregations: 60% (typical pattern)           │
│   • Filters: 30%                                  │
│   • Joins: 10%                                    │
│ Domains queried:                                  │
│   • Patient data: 45%                             │
│   • Operations: 35%                               │
│   • Finance: 20%                                  │
│                                                    │
├────────────────────────────────────────────────────┤
│ COMPLIANCE & SECURITY                             │
├────────────────────────────────────────────────────┤
│                                                    │
│ Data stored: 2.3TB (clinical records)             │
│ Audit logs: 847MB (6-year retention policy)       │
│ Security events: 0 (zero breaches/violations)     │
│ Break-glass access: 3 (all reviewed/approved)     │
│ Unusual access: 0 (no anomalies detected)         │
│ Policy violations: 0 (all access policy-compliant)│
│ DSAR requests: 2 (both completed on time)         │
│ Erasure requests: 0                               │
│                                                    │
├────────────────────────────────────────────────────┤
│ COST ANALYSIS                                     │
├────────────────────────────────────────────────────┤
│                                                    │
│ Contract: $500K/year → ~$41,667/month             │
│ Actual cost (AWS): ~$32,100/month                 │
│   • Compute: $15,200 (70% of customer pods)      │
│   • Database: $8,400 (PostgreSQL, backup)        │
│   • Storage: $4,800 (S3 audit logs)              │
│   • Egress: $2,100 (data transfer to customer)   │
│   • LLM API: $1,600 (Azure OpenAI inference)     │
│ Margin: +27% (profitable customer) ✓             │
│ LLM cost per query: $0.0065 (vs revenue $0.20)   │
│                                                    │
│ Forecasted 30-day cost (based on current usage):   │
│   • If usage trends stable (8,167 q/day): $32.1K  │
│   • If usage grows 20% (9,800 q/day): $38.5K     │
│   ⚠️ Alert: Will exceed contract allocations in   │
│      3 months at current growth rate              │
│   Action: [Recommend upsell] [Review contract]   │
│                                                    │
├────────────────────────────────────────────────────┤
│ QUICK ACTIONS                                      │
├────────────────────────────────────────────────────┤
│                                                    │
│ [View Audit Logs] [Monitor Real-Time]             │
│ [Check Connector Health] [Run Diagnostics]        │
│ [Contact Customer] [Escalate to Support]          │
│ [View Performance Graph] [Export Report]          │
│                                                    │
└────────────────────────────────────────────────────┘
```

### Dashboard 3: Churn Prediction & Risk Detection

**Purpose:** Identify at-risk customers before they churn

```
┌────────────────────────────────────────────────────┐
│ CHURN RISK ANALYSIS (30-Day Forecast)              │
├────────────────────────────────────────────────────┤
│                                                    │
│ HIGH RISK (3 customers - action needed):          │
│                                                    │
│ 🔴 EuroBank AG (Tenant: tenant_e3m2p)            │
│    Risk score: 8.2/10 (HIGH)                      │
│    Indicators:                                    │
│      • Usage declined 40% in past 2 weeks        │
│      • No active users past 4 days                │
│      • Ticket submitted: "Evaluating competitors" │
│      • Connector errors in past 4 hours           │
│    Recommended action:                            │
│      → [Call enterprise account manager]          │
│      → [Debug connector issue] (immediate)        │
│      → [Offer technical support call]            │
│    Predicted churn probability: 65%               │
│                                                    │
│ 🔴 RetailChain Ltd (Tenant: tenant_r5k8q)       │
│    Risk score: 7.1/10 (HIGH)                      │
│    Indicators:                                    │
│      • Storage capacity warnings (87%)            │
│      • Latency degradation (avg +340ms)          │
│      • Support ticket: "System is slow"           │
│      • License expiration: 45 days                │
│    Recommended action:                            │
│      → [Expand storage + database optimization]  │
│      → [Proactive support engagement]             │
│      → [Renewal discussion] (start early)        │
│    Predicted churn probability: 58%               │
│                                                    │
│ 🟡 MedicalStaff Solutions (Tenant: tenant_m2j9l) │
│    Risk score: 5.4/10 (MEDIUM)                    │
│    Indicators:                                    │
│      • Feature adoption below target (only 3 of  │
│        12 templates used)                         │
│      • Support tickets spike (10 in past week)    │
│      • Onboarding still pending (promised 3 wks) │
│    Recommended action:                            │
│      → [Assign success manager]                   │
│      → Schedule feature training                  │
│      → [Follow-up training call]                 │
│    Predicted churn probability: 35%               │
│                                                    │
│ MEDIUM RISK (8 customers - monitor):              │
│   • [Expand to view]                              │
│                                                    │
│ LOW RISK (116 customers - routine check):         │
│   • [Expand to view]                              │
│                                                    │
└────────────────────────────────────────────────────┘
```

### Dashboard 4: LLM Cost Optimization

**Purpose:** Track and optimize LLM inference costs

```
┌────────────────────────────────────────────────────┐
│ LLM COST ANALYTICS (Past 30 Days)                  │
├────────────────────────────────────────────────────┤
│                                                    │
│ TOTAL LLM SPEND: $18,450                          │
│ • Azure OpenAI (Infer): $14,200 (77%)            │
│ • AWS Bedrock (Rare): $2,100 (11%)               │
│ • Self-hosted (On-prem): $2,150 (12%)            │
│                                                    │
│ COST PER QUERY: $0.0132                           │
│ • Baseline: $0.0075 (intent extraction)           │
│ • Overhead: $0.0042 (context, retries, fallback) │
│ • Target: <$0.0100 (21% improvement needed)      │
│                                                    │
├────────────────────────────────────────────────────┤
│ TOP 10 CUSTOMERS BY LLM COST                      │
├────────────────────────────────────────────────────┤
│                                                    │
│ 1. HealthCorp Intl: $2,340 (45% of total)        │
│    Queries: 245,000 | Cost/query: $0.0095        │
│    Trend: ↑ 8% week-over-week                    │
│    Action: [Optimize intent cache hit rate]      │
│                                                    │
│ 2. EuroBank AG: $1,840 (10%)                     │
│    Queries: 140,000 | Cost/query: $0.0131        │
│    Trend: ↓ Stable                               │
│                                                    │
│ 3-10. [Other 8 customers: $13,270 combined]      │
│                                                    │
├────────────────────────────────────────────────────┤
│ OPTIMIZATION OPPORTUNITIES                        │
├────────────────────────────────────────────────────┤
│                                                    │
│ 💰 Cache Hit Rate: 62% (target 80%)              │
│    Opportunity: Increase cache TTL + warm cache  │
│    Est. savings: $2,100/month (11%)              │
│    ROI: Immediate (dev time: 4 hours)            │
│                                                    │
│ 💰 Intent Classification Accuracy: 94%            │
│    (Out-of-distribution queries → fallback)      │
│    Opportunity: Improve OOD detection             │
│    Est. savings: $1,400/month (7%)               │
│    ROI: 1 week payback                           │
│                                                    │
│ 💰 Model Selection: Using GPT-4 (expensive)      │
│    Opportunity: Evaluate Mistral/Llama for       │
│    non-sensitive intents                         │
│    Est. savings: $4,200/month (23% of total)    │
│    Risk: Accuracy regression (testing needed)    │
│                                                    │
│ Projected monthly savings (if all optimizations  │
│ implemented): $7,700 (42% reduction)            │
│ Annual impact: $92,400 cost reduction            │
│                                                    │
└────────────────────────────────────────────────────┘
```

---

## Frontend & Mobile UX Specification

### User Experience Flows

**Home Screen (Web & Mobile)**

```
On Login → Redirect to home screen

┌──────────────────────────────────────────┐
│ ✓ HealthCorp International Health System  │
│ Logged in as: Dr. Sarah Chen              │
│ Role: Clinician | Dept: Cardiology       │
│                                          │
├──────────────────────────────────────────┤
│ QUICK ACTIONS                            │
│                                          │
│ [🔍 Ask a Question]  [📊 View Dashboard] │
│                                          │
├──────────────────────────────────────────┤
│ PERSONALIZED SUGGESTIONS                 │
│ (Based on your recent queries)           │
│                                          │
│ 🩺 "Your patients with follow-up due"   │
│    [See 3 patients with appointments    │
│    overdue - click to expand]           │
│                                          │
│ 📋 "Open care plans from last week"      │
│    [Review 8 incomplete plans]          │
│                                          │
│ ⚠️ "Readmission risk cohort"             │
│    [12 patients flagged - click          │
│    to see details]                      │
│                                          │
│ 🔔 "Sepsis alerts (today)"               │
│    [1 alert active - see now]           │
│                                          │
├──────────────────────────────────────────┤
│ SAVED QUERIES                            │
│                                          │
│ 📌 "My Cardiology Patients - Today"     │
│    Updated 2 hours ago [View]            │
│                                          │
│ 📌 "Readmission Risk Scorecard"         │
│    Updated yesterday [View]             │
│                                          │
│ 📌 "Open Orders by Priority"            │
│    Updated 1 week ago [View]            │
│                                          │
│ [+ Create New Query]                    │
│                                          │
├──────────────────────────────────────────┤
│ RECENT ACTIVITY                         │
│                                          │
│ • Queried "Sepsis risks" 14:22          │
│ • Exported report "Q1 Discharge Summary" │
│ • Ran "Readmission dashboard" 13:50     │
│                                          │
├──────────────────────────────────────────┤
│ [⚙️ Settings] [❓ Help] [🚪 Sign Out]     │
│                                          │
└──────────────────────────────────────────┘
```

**Query Input Interface (Web)**

```
┌─ Query Bar ─────────────────────────────┐
│                                         │
│ 🎤 [Microphone] Type or say your query  │
│ ─────────────────────────────────────────
│ "Show me my patients with overdue follow-ups"
│                                         │
│ ┌─ Smart Suggestions ─────────────────┐ │
│ │ • "...with high readmission risk"   │ │
│ │ • "...by appointment urgency"       │ │
│ │ • "...from last 30 days"            │ │
│ └─────────────────────────────────────┘ │
│                                         │
│ [🔍 Search]  [🎯 Advanced]  [📋 Template]│
│                                         │
└─────────────────────────────────────────┘

Mobile (iOS/Android):
┌──────────────────────────────┐
│ 🎤 Tap to speak...          │
├──────────────────────────────┤
│ "Show me my cardiology..."  │
├──────────────────────────────┤
│ ...(typing as listening)    │
│                              │
│ [Send ▶]  [Cancel ✕]        │
└──────────────────────────────┘
```

**Results Display (Example - Sepsis Alert)**

```
┌─────────────────────────────────────────┐
│ SEPSIS ALERT SUMMARY            [Close] │
├─────────────────────────────────────────┤
│                                         │
│ 🔴 CRITICAL (1 patient)                │
│                                         │
│ Robert M. [Room 412A]     [View Full Record]│
│ ├─ Vitals: T=103.2°F, HR=128, BP=88/52 │
│ ├─ Labs: WBC=18.2↑, Lactate=4.1↑       │
│ ├─ qSOFA: 3/3 (HIGH RISK)              │
│ ├─ 🚨 Recommendation: PAGE PHYSICIAN   │
│ ├─ Time escalated: 2 minutes ago       │
│ └─ [Contact Attending] [View Chart]    │
│                                         │
│ ─────────────────────────────────────── │
│                                         │
│ 🟡 ELEVATED RISK (3 patients)          │
│                                         │
│ Maria G. [Room 410]                    │
│ ├─ T=101.8°F, WBC=15.1, BP=92/60      │
│ ├─ Recommendation: Monitor closely     │
│ └─ [View Chart]                        │
│                                         │
│ [Show all 3] [⊕ Add to task list]      │
│                                         │
├─────────────────────────────────────────┤
│ ✓ Source: Epic EHR                      │
│ ✓ Your access: Cardiology dept assigned │
│ ✓ Scope: Assigned patients              │
│ Last updated: 4 minutes ago             │
│ [Refresh] [Export] [Share]              │
│                                         │
└─────────────────────────────────────────┘
```

**Offline Mode (Mobile)**

When network unavailable:
```
┌──────────────────────────────┐
│ ⚠️ No Connection             │
│                              │
│ Cached queries available:    │
│                              │
│ 📌 "My Patients" (2h ago)    │
│ 📌 "Vital Signs" (5h ago)    │
│ 📌 "Med List" (yesterday)    │
│                              │
│ New queries unavailable      │
│ (will sync when online)      │
│                              │
│ [View cached data]           │
│                              │
└──────────────────────────────┘
```

### Tenant Routing UX (SaaS Only)

**Workspace Selection (First Login)**

```
No workspace code provided:
┌─────────────────────────────────────┐
│ Which organization are you with?     │
│                                      │
│ [Search organizations...]            │
│                                      │
│ Popular:                              │
│ • HealthCorp International            │
│ • Boston Medical Center               │
│ • Partners Healthcare                 │
│                                      │
│ Not listed?                          │
│ [Enter workspace code]               │
│ [Request invite from administrator]  │
│                                      │
└─────────────────────────────────────┘

User enters workspace code:
├─→ [Magic link sent to email]
│   + Admin clicks "Approve"
│   └─→ [Invited user can now access]
```

**Workspace Switcher (If Multi-Workspace Access)**

```
Logged in as: Dr. Sarah Chen

Current workspace: HealthCorp International

[Switch Organization ▾]

Available workspaces:
• HealthCorp International (primary)
• Boston Medical Center (consulting role)
• State Health Commission (advisor)

[Select]
```

---

## Action Registry: Rigorous Structural Definition

Every action must be defined with this schema:

```json
{
  "action_id": "ACT-001",
  "name": "DSAR_EXECUTE",
  "display_name": "Execute Data Subject Access Request",
  "category": "compliance",
  
  "trigger": {
    "type": "manual|scheduled|event",
    "manual_activation": "User clicks 'Execute' in UI",
    "scheduled_example": "Every Monday at 09:00 UTC (retention cleanup)",
    "event_trigger_example": "On customer account deletion"
  },
  
  "required_data_scope": [
    {
      "system": "customer",
      "resources": ["customer_profile", "all_transactions"],
      "why": "DSAR must retrieve all records held by organization"
    }
  ],
  
  "required_permissions": [
    "compliance.can_execute_dsar",
    "audit.can_access_audit_logs"
  ],
  
  "approval_requirements": {
    "level": "AUTOMATIC|MANUAL|MULTI_STAGE",
    "sla_hours": 4,
    "escalation": "To Compliance Officer if not approved in 4 hours",
    "reviewer_role": "Compliance_Officer"
  },
  
  "input_schema": {
    "subject_identifier": {
      "type": "string",
      "description": "Email, customer ID, or name",
      "validation": "Must match verified customer in system"
    },
    "include_audit_logs": {
      "type": "boolean",
      "description": "Include user activity logs",
      "default": true
    },
    "delivery_method": {
      "type": "enum",
      "values": ["secure_portal", "encrypted_email"],
      "default": "secure_portal"
    }
  },
  
  "execution_steps": [
    {
      "step_id": 1,
      "name": "Verify Subject Identity",
      "description": "Validate that subject exists and is authorized to make request",
      "timeout_minutes": 5,
      "fallback": "Request OTP verification"
    },
    {
      "step_id": 2,
      "name": "Identify All Records",
      "description": "Scan all connected systems for records matching subject",
      "systems": ["erp", "crm", "accounting", "audit_logs"],
      "timeout_minutes": 30,
      "fallback": "Retry with exponential backoff"
    },
    {
      "step_id": 3,
      "name": "Aggregate Records",
      "description": "Collect identified records to staging area",
      "timeout_minutes": 10,
      "fallback": "Partial collection (warn compliance officer)"
    },
    {
      "step_id": 4,
      "name": "Redaction",
      "description": "Remove references to other data subjects",
      "timeout_minutes": 5,
      "fallback": "Manual review required"
    },
    {
      "step_id": 5,
      "name": "Organization & Formatting",
      "description": "Structure data in human-readable format",
      "timeout_minutes": 5,
      "fallback": "Default format with warning"
    },
    {
      "step_id": 6,
      "name": "Encryption",
      "description": "Encrypt export (AES-256)",
      "timeout_minutes": 2,
      "fallback": "FAIL (security requirement)"
    },
    {
      "step_id": 7,
      "name": "Delivery",
      "description": "Deliver via secure portal or encrypted email",
      "timeout_minutes": 5,
      "fallback": "Manual delivery (notify ops)"
    },
    {
      "step_id": 8,
      "name": "Compliance Documentation",
      "description": "Generate signed proof for regulator",
      "timeout_minutes": 2,
      "fallback": "FAIL (audit requirement)"
    }
  ],
  
  "output_schema": {
    "action_id": "string (UUID)",
    "status": "completed|failed|partial",
    "records_collected": "integer",
    "records_redacted": "integer",
    "records_delivered": "integer",
    "completion_time": "timestamp",
    "delivery_confirmation": {
      "method": "string",
      "recipient": "string",
      "delivered_at": "timestamp",
      "received_confirmation": "timestamp"
    },
    "compliance_proof": {
      "proof_id": "string",
      "signed": true,
      "regulatory_ready": true
    }
  },
  
  "risk_classification": {
    "risk_level": "CRITICAL|HIGH|MEDIUM|LOW",
    "requires_confirmation": true,
    "dry_run_available": true,
    "reversible": false,
    "sla_critical": true
  },
  
  "audit_implications": {
    "logged": true,
    "immutable_log": true,
    "includes_approval_chain": true,
    "includes_execution_details": true,
    "compliance_framework": ["GDPR", "HIPAA", "DPDP"]
  },
  
  "allowed_personas": [
    "Compliance_Officer",
    "System_Admin",
    "Customer_Data_Subject"
  ],
  
  "prohibited_actions": [
    "Cannot modify in-flight action",
    "Cannot delete audit log of action",
    "Cannot bypass approval for CRITICAL actions"
  ],
  
  "examples": {
    "success_path": "Subject requests DSAR → auto-verified → 5 sources scanned (450 records) → redacted (8 refs to others) → encrypted → delivered via portal → subject downloads → proof recorded",
    "failure_path": "Subject unverified → OTP requested → OTP expired → request rejected → marked as declined + reason logged",
    "partial_path": "3 of 5 systems available → partial collection delivered with warning → compliance officer reviews → decision to retry or accept partial"
  }
}
```

**All 12 Action Templates Must Have This Schema:**

1. ✓ DSAR_EXECUTE (above)
2. ✓ ERASURE_EXECUTE (reversible: false, requires: legal proof)
3. ✓ ESCALATE_TO_MANAGER (reversible: true, SLA: 4 hours)
4. ✓ BULK_SOFT_DELETE (reversible: true, requires: approval)
5. ✓ FIELD_MASKING_UPDATE (reversible: true, requires: compliance review)
6. ✓ CONSENT_WITHDRAWAL (reversible: false after 30-day grace period)
7. ✓ INCIDENT_RESPONSE (reversible: false, SLA: <15 minutes to freeze)
8. ✓ POLICY_UPDATE (reversible: true, SLA: 1 hour to validate)
9. ✓ CONNECTOR_REFRESH (reversible: true, back-off strategy)
10. ✓ AUDIT_EXPORT (reversible: false - immutable)
11. ✓ SEGMENT_ACTIVATION (reversible: true, compliance gates)
12. ✓ SCHEDULED_REPORTING (reversible: true for one-time, not recurring)

---

## On-Premises LLM Integration Strategy

**Resolving the Cloud/On-Prem Contradiction**

Originally: "Never learns from or exfiltrates customer data"
Problem: If on-prem relies on Azure OpenAI API, there's an external dependency + data leaves customer network

**Solution: Multi-Mode LLM Architecture**

```
┌─ LLM Strategy by Deployment ─────────────────────┐
│                                                  │
│ CLOUD-HOSTED SAAS:                              │
│ ├─ Primary: Azure OpenAI (GPT-4, cost-optimized)│
│ ├─ Fallback: AWS Bedrock (Anthropic Claude)    │
│ ├─ Data: Transient (deleted within 24 hours)   │
│ ├─ Guarantee: "Zero-learning" enforced         │
│ └─ Compliance: SOC2, FedRAMP (depending region) │
│                                                  │
│ ON-PREMISES (Customer-Managed):                │
│ ├─ Primary: Mistral-7B (quantized, local)      │
│ │  • 7B parameters, 4-bit quantized = 3GB RAM  │
│ │  • Accuracy: 94% on standard intent classes  │
│ │  • Latency: 80ms per inference (local GPU)    │
│ │  • Cost: $0 per inference (customer pays      │
│ │    only for hardware/power)                   │
│ │                                               │
│ ├─ Alternative: LLaMA-2-13B (if customer       │
│ │  provides more compute: 16GB GPU memory)     │
│ │  • Better accuracy (96%) but slower          │
│ │  • Still fully local, no external calls      │
│ │                                               │
│ ├─ Fallback: Customer can bring own LLM        │
│ │  • Custom endpoint: Configure endpoint URL   │
│ │  • Any model: Local or air-gapped            │
│ │  • Risk: Customer responsible for accuracy   │
│ │                                               │
│ └─ Guarantee: "Zero external calls"            │
│    All inference local, zero exfiltration      │
│                                                  │
└──────────────────────────────────────────────────┘
```

**Implementation Details:**

```yaml
on-prem-config.yaml:

llm_config:
  enabled: true
  mode: "local"  # local | remote_endpoint | azure_api
  
  if_local:
    model: "mistral-7b"  # mistral-7b | llama-2-13b | custom
    quantization: "4bit"  # 4bit | 8bit | full
    
    mistral-7b:
      checkpoint_size: "3.2GB"
      storage_path: "/zta-ai/models/mistral-7b"
      download_url: "https://zta-ai.s3.amazonaws.com/models/mistral-7b-v0.2.tar.gz"
      checksum: "sha256:abc123..."  # Verify authenticity
      
    inference_config:
      gpu_memory: "6GB"  # Auto-detect or manual
      cpu_fallback: true  # If GPU unavailable, use CPU (slower)
      max_tokens: 256
      temperature: 0.3  # Deterministic for compliance
      
    performance:
      batch_size: 32  # Queries batched per second
      latency_target_ms: 150  # Local should be <150ms
      
  if_remote_endpoint:
    endpoint_url: "http://localhost:8000/v1/completions"
    api_key: "${CUSTOM_LLM_API_KEY}"  # From secrets vault
    max_retries: 3
    timeout_seconds: 30
    
  if_azure_api:
    enabled: false  # Cloud-only, ON-PREM MUST use local
    # (This section ignored in on-prem deployment)
```

**Deployment Process (On-Prem):**

```bash
$ ./install.sh

1. Detect available compute:
   Scanning GPU...
   • NVIDIA T4 detected (16GB memory) ✓
   
2. Recommend model:
   → Mistral-7B is suitable (3GB needed, 16GB available)
   → Or LLaMA-2-13B for better accuracy (13GB needed)
   
   User selects: Mistral-7B
   
3. Download (air-gapped option):
   Option A: Download from internet
   Option B: Use offline mirror (provide USB drive)
   Option C: Use custom URL (air-gapped CDN)
   
   Selected: Offline mirror (USB drive provided)
   
4. Verify integrity:
   Checking checksum...
   SHA256: abc123abc123...abc123 ✓ MATCH
   Signature verified: ✓ Valid (signed by ZTA-AI, verified locally)
   
5. Extract and optimize:
   Extracting model...
   Converting to 4-bit quantization...
   Testing inference...
   
6. Test inference:
   Running 100 sample intents...
   Success rate: 96% ✓
   Avg latency: 112ms ✓
   
7. Done:
   LLM ready for queries
   All inference local, zero external calls
```

**Guarantees enforced:**

```
On-Premises Guarantee (Immutable in Code):

config.policy:
  on_prem_mode:
    external_api_calls: "NEVER"  # Hardcoded, cannot be overridden
    model_learning: "DISABLED"    # LLM runs inference-only mode
    data_persistence: "SESSION_ONLY"  # Deleted within 24 hours
    
  enforcement:
    - No HTTP/HTTPS calls outside local network (firewall enforced)
    - Model weights are read-only (immutable in container)
    - Audit logs prove zero-learning (checksums verified)
    - Legal: "On-Premise First" guarantee backed by architecture

Legal Contract Language:
  "For on-premises deployments, ZTA-AI operates entirely within customer's
   network. No customer data leaves the firewall. No external APIs are called.
   All inference is performed locally. ZTA-AI implements technical and
   operational controls to enforce this guarantee."
```

---

## Performance Baseline Reconciliation

**Resolving the latency contradiction:**

Original MVP Reality section: "~5000ms baseline latency"
Present Optimization Targets section: "~1000ms baseline"

**Explanation & Clarification:**

```
LATENCY MEASUREMENTS: Different Scenarios

Scenario A: MVP Baseline (Original, ~5000ms)
  Context: Unoptimized proof-of-concept
  Path: Chat → Intent extraction → Policy check → Query build → DB execute
  
  Breakdown:
    1. Intent extraction: 1,800ms (no caching, full model inference)
    2. Policy evaluation: 300ms (inefficient rule lookup)
    3. Schema query: 1,000ms (full schema scan per query, no cache)
    4. Query compilation: 800ms (unoptimized code generation)
    5. Database execution: 800ms (no indexes, table scan)
    6. Result serialization: 300ms
    ──────────────────
    TOTAL: ~5,200ms
  
  Conditions: Healthcare tenant, 50GB schema, cold cache

---

Scenario B: Optimized Baseline (Current target, ~1000ms)
  Context: Production-hardened, caches enabled, indexes tuned
  Path: Same as A, but optimized
  
  Breakdown:
    1. Intent extraction: 150ms (cached embeddings, reuse)
    2. Policy evaluation: 40ms (indexed rule lookup)
    3. Schema query: 200ms (cached schema, <100ms lookup)
    4. Query compilation: 80ms (optimized AST generation)
    5. Database execution: 400ms (proper indexes)
    6. Result serialization: 30ms
    ──────────────────
    TOTAL: ~900ms (P95: <1000ms)
  
  Conditions: Same tenant, warm cache, indexes present

---

OPTIMIZATION TIMELINE:

Phase 0 (Today - MVP): 5,200ms baseline
  ↓ (Weeks 1-2: Add caching)
Phase 1 (Week 2): 3,400ms (38% improvement)
  ↓ (Weeks 3-4: Policy indexing)
Phase 2 (Week 4): 2,100ms (62% improvement)
  ↓ (Weeks 5-6: Database tuning)
Phase 3 (Week 6): 980ms (81% improvement) ← TARGET
  ↓ (Weeks 7-8: Connector pooling)
Phase 4 (Week 8): 850ms (84% improvement) ← STRETCH

Success Criteria:
  Phase 9 (Performance Hardening) Gate: P95 <1000ms sustained
  This is achievable from MVP ~5200ms baseline
```

---

## Updated Quality Gates

### Gate 1: Feature Completeness & ARCHITECTURE
**Now includes deployment and frontend layers**

```
Completion checklist:

BACKEND FEATURES:
  ✓ Query interface (conversational, multi-turn)
  ✓ Intent extraction (domain-agnostic)
  ✓ Policy enforcement (RBAC, ABAC, RLS, FLS)
  ✓ Query compilation (optimizer)
  ✓ Action registry (12 templates, rigorous schema)
  ✓ Compliance workflows (DSAR, erasure, breach)
  ✓ Audit logging (immutable, tamper-proof)

FRONTEND & UX:
  ✓ Web interface (home, query, results, settings)
  ✓ Mobile app (iOS/Android)
  ✓ Offline mode (cached queries)
  ✓ Voice input (speech-to-text)
  ✓ Smart suggestions (contextual)
  ✓ Tenant routing UX (workspace selection)

DEPLOYMENT:
  ✓ Cloud deployment (Terraform, Helm, K8s)
  ✓ On-prem deployment (installer, Helm chart)
  ✓ Multi-tenant routing service
  ✓ Update agent (air-gapped compatibility)
  ✓ LLM integration (local + API modes)

OPERATIONS:
  ✓ System admin console (fleet health, per-customer)
  ✓ Churn prediction dashboard
  ✓ Cost optimization dashboard
  ✓ Incident response tools

Pass Criteria: 100% of above documented, implemented, tested
```

### Gate 2: Security (UNCHANGED)
```
[No changes - existing security gate still valid]
```

### Gate 3: Compliance (UNCHANGED)
```
[No changes - existing compliance gate still valid]
```

### Gate 4: Performance
```
WITH ON-PREM ADDITION:

Cloud SaaS:
  ✓ P95 latency <1000ms (100 concurrent users)
  ✓ Throughput 200 q/min
  ✓ Error rate <0.1%

On-Premises:
  ✓ P95 latency <1500ms (local LLM latency overhead)
  ✓ Throughput 100 q/min (customer hardware dependent)
  ✓ Error rate <0.1%
  ✓ LLM inference fully local (zero external calls)
  ✓ Model accuracy >94% on standard intents
```

### Gate 5: Observability (UPDATED)
```
Dashboard coverage:
  ✓ Fleet health board (SaaS only)
  ✓ Per-tenant deep dive
  ✓ Churn risk detection
  ✓ LLM cost optimization
  ✓ On-prem admin console
```

### Gate 6: Operational Readiness (NEW)
```
Completion checklist:

Deployment:
  ✓ SaaS infrastructure code (Terraform)
  ✓ On-prem installation script
  ✓ Deployment runbook (step-by-step)
  ✓ Version upgrade procedure
  ✓ Rollback procedure

Operations:
  ✓ System admin console (fully functional)
  ✓ Fleet health monitoring (SaaS)
  ✓ Alert configuration (thresholds)
  ✓ On-call runbooks (incident response)
  ✓ Cost tracking (per-tenant)

Support:
  ✓ Troubleshooting guide (50+ scenarios)
  ✓ FAQ (100+ common questions)
  ✓ Support log collection tool
  ✓ Self-service diagnostics

User:
  ✓ End-user documentation
  ✓ Admin training materials
  ✓ Video tutorials (top 10 workflows)
  ✓ System health status page (SaaS)

Pass Criteria: Ops team can manage fleet without engineering
```

---

## Conclusion: Single Source of Truth

- **Every feature described is mandatory** (no MVP cuts)
- **Every persona is concretely illustrated** (domain-agnostic but specific)
- **Every use case is detailed with examples** (banking, healthcare, manufacturing, insurance, professional services)
- **Every architecture component is explained** (with real walkthroughs)
- **Every compliance framework is operationalized** (HIPAA, GDPR, DPDP)
- **Every gate is defined** (launch acceptance criteria)
- **Every risk is identified and mitigated** (risk register)

This is the reference document for Product, Engineering, Security, Compliance, Legal, and Operations alignment.

All other decisions, designs, and implementations flow from this plan.
