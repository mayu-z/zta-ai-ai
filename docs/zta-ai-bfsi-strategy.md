# ZTA-AI — BFSI Vertical Strategy (SLM-Strict)

**Plan Alignment:** This vertical strategy is aligned to `ZTA_AI_FINAL_PRODUCT_PRODUCTION_PLAN.md` (v3.0, April 11, 2026). Product-wide scope and phase gates are governed by the plan file. See `docs/PLAN_ALIGNMENT.md`.

**Beachhead Market: Banking, Financial Services & Insurance**

**// full vertical strategy — market · use cases · compliance · sales · roadmap**

---

## 01 — Why BFSI is the Right Beachhead

1.  **Highest Willingness to Pay**: BFSI pays a 3–5× premium for security products. A data breach triggers RBI fines, SEBI audits, and customer exodus. ($1.7B India BFSI cybersecurity investment in 2023).
2.  **Regulation Creates Your Sales Script**: RBI, SEBI, IRDAI, DPDP Act, and GDPR mandate data security. (₹250Cr max DPDP penalty per breach).
3.  **98% of Banks Want Generative AI Now**: Banks plan to use GenAI tools by end of 2025 but fear internal data leaks. ZTA-AI's sandboxed SLM architecture addresses this directly.
4.  **RBI FREE-AI Framework = Tailwind**: Responsible & Ethical AI (FREE-AI) framework 2025 creates a compliant path for the 80% of institutions yet to deploy AI.
5.  **Internal Use Case is Clear & Urgent**: Analysts, relationship managers, risk teams, and HR all need to query siloed data. ZTA-AI's deterministic, policy-driven architecture with untrusted SLM is the only safe path.
6.  **Fastest Growing AI Sub-Sector**: GenAI in BFSI growing at 32.5% CAGR (2025–2032).

---

## 02 — BFSI Market Numbers

*   **$43B**: AI in BFSI — 2024 (→ $299B by 2033)
*   **$1.9B**: GenAI in BFSI — 2025 (→ $13.6B by 2032)
*   **$6.2B**: BFSI Chatbot Market 2030 (27.4% CAGR)
*   **24%**: AI in BFSI CAGR (Fastest enterprise sector)
*   **$110B**: India Fintech 2024 (→ $420B by 2029)
*   **46%**: Mid-size Banks with AI Chatbots (Up from 30% in 2022)

---

## 03 — Internal BFSI Use Cases (What ZTA-AI Solves)

**Note**: ZTA-AI's play in BFSI is **internal-facing only**. It fills the gap that generic AI tools cannot safely fill by enforcing hard department silos through a **deterministic, claim-based architecture** where the **SLM is completely sandboxed and untrusted**.

### Risk Analyst (RISK)
*   **Prompt**: "What is our current NPL ratio by branch and how does it compare to last quarter?"
*   **Access**: Loan book, NPL data, branch performance. (DENIED: HR, customer PII, treasury).
*   **SLM receives**: Pre-approved, structured claims only — no raw data.

### Relationship Manager (SALES)
*   **Prompt**: "Show me all clients in my portfolio with upcoming loan renewals in the next 30 days."
*   **Access**: Own client portfolio, product data. (DENIED: other RMs' clients, internal P&L, HR).
*   **SLM receives**: Filtered claims based on user's access scope.

### Compliance Officer (COMPLIANCE)
*   **Prompt**: "Which transactions in the last 7 days breached our AML threshold? Summarize for RBI report."
*   **Access**: Transaction monitoring, AML flags, audit logs. (DENIED: salary data, HR records).
*   **SLM receives**: Sanitized, compliance-tagged claims only.

### Treasury Desk (TREASURY)
*   **Prompt**: "What is our current ALM gap across 1Y, 3Y, and 5Y buckets? Any SLR/CRR concerns?"
*   **Access**: ALM data, liquidity, SLR/CRR positions. (DENIED: customer PII, HR, retail loan book).
*   **SLM receives**: Aggregated, sensitivity-filtered claims.

### HR / People Team (HR)
*   **Prompt**: "What is the attrition rate in our retail banking division this year compared to industry benchmark?"
*   **Access**: Headcount, attrition, leave records. (DENIED: financial P&L, loan book, AML data).
*   **SLM receives**: Redacted claims with masked PII.

### Internal Audit (AUDIT)
*   **Prompt**: "Generate the quarterly internal audit summary report for our trade finance division with exception log."
*   **Access**: Cross-dept read-only, exception reports, audit trails. (DENIED: No modification rights).
*   **SLM receives**: Validated claims with full provenance tracking.

---

## 04 — Regulatory Compliance Wall

### RBI FREE-AI (2025)
*   AI governance board mandatory.
*   Post-deployment bias monitoring & explainability.
*   Human oversight & audit-ready documentation.
*   *Penalty: Only 20% of banks currently comply.*

### RBI Cybersecurity Master Directions
*   Data localization (store in India).
*   Access control audit trails & 3rd party risk assessments.
*   Incident reporting within 6 hours.
*   *Penalty: Top mgmt personally liable.*

### DPDP Act 2023 (India)
*   Explicit consent & Data Principal rights.
*   Grievance Officer & Data Protection Impact Assessments.
*   *Penalty: Up to ₹250 Crore per non-compliance.*

### SEBI Framework
*   Zero trust access for market data.
*   Segregation of trading vs ops data.
*   KYC data isolation mandatory.
*   *Penalty: Trading license revocation risk.*

---

## 05 — Who Buys ZTA-AI Inside a Bank

1.  **CISO (Technical Champion)**: Cares about security audits, **SLM sandboxing**, no tool/function access, immutable logs, SOC 2.
2.  **CCO / CRO (Budget Unlocker)**: Cares about RBI FREE-AI, DPDP consent, regulator reports, liability. Values **deterministic, policy-driven architecture**.
3.  **CTO / CDO (Technical Decision Maker)**: Cares about connectors, private cloud deployment, latency, integration. Values **claim-based data model** and **output validation**.
4.  **CFO / COO (Economic Buyer)**: Cares about ROI, productivity, cost vs analysts, compliance offset.

---

## 06 — BFSI MVP — What to Build First

### Phase 1: Foundation (Month 1–2)
*   Zero Trust Gate with RBAC+ABAC token enforcement.
*   Deterministic Interpreter layer (no SLM usage in parsing).
*   PostgreSQL + MSSQL connectors via Tool/Function Layer.
*   Claim Engine with immutable, versioned claims.
*   Dept silos (Risk/Compliance/HR/Treasury) via Policy Engine.
*   Immutable query audit log & SAML/OIDC SSO.
*   **Goal**: Working demo for CISO showing SLM sandboxing.

### Phase 2: Compliance Layer (Month 3–4)
*   Context Governance Layer with data minimization.
*   Sandboxed SLM Runtime with output validation.
*   RBI FREE-AI report generator.
*   DPDP consent flow management.
*   Data localization config (India-only hosting).
*   PII masking (Salary/Aadhaar/PAN) via redaction engine.
*   **Goal**: CCO/CRO signs off. Unlocks budget.

### Phase 3: Connector Expansion (Month 5–6)
*   Core Banking System (Finacle/Flexcube/Temenos).
*   Loan Management System (LMS) connector.
*   File upload (PDF/Excel).
*   On-prem Docker agent.
*   **Goal**: First 3 paying pilots running.

### Phase 4: Scale (Month 7–12)
*   SOC 2 Type II & ISO 27001 certifications.
*   CERT-In empanelment.
*   Premium connectors: Salesforce, SAP, Bloomberg.
*   **Goal**: 10 paying customers, $1M ARR path.

---

## 07 — BFSI Sales Playbook

1.  **Find Your Champion**: Start with mid-level Compliance Analysts or Risk Managers.
2.  **Lead with Compliance**: Pitch "RBI FREE-AI compliant internal data governance," not just "AI."
3.  **Free 30-Day Pilot**: BFSI requires seeing it in their environment. Target 2–3 departments.
4.  **Pre-empt Security Reviews**: Have questionnaires, architecture diagrams, and pen tests ready.
5.  **Price Against Headcount**: ₹30L–₹1Cr/year range for mid-size banks (less than hiring analysts).
6.  **Target Private Banks First**: HDFC, Axis, ICICI, etc. move faster than PSU banks (SBI/PNB).

---

## 08 — Certifications You Must Have

*   **SOC 2 Type II**: Required for due diligence. (3–6 months, $30K–$60K).
*   **ISO 27001**: Mandatory for enterprise procurement. (6–12 months, $20K–$50K).
*   **CERT-In Empanelment**: Required for Indian banking vendors. (3–6 months, $5K–$15K).
*   **RBI Cloud Framework**: Data localization proof required. (2–4 months).
*   **DPDP Compliance Audit**: Prove consent flows & data mapping. (2–3 months).
*   **VAPT Report**: Penetration testing required every 6 months. (4–6 weeks).

---

## 09 — BFSI-Specific Risks

*   **Long Procurement Cycles**: 6–12 months is standard. (Mitigation: NBFCs/fintechs first).
*   **Core Banking System Lock-In**: Legacy Finacle/Flexcube systems are closed. (Mitigation: Start with reporting DBs).
*   **Data Quality**: Indian banks have messy, duplicated legacy data. (Mitigation: Partner for data prep).
*   **Data Localization**: RBI mandates data stay in India. (Mitigation: Host LLM in India region).
*   **Competition**: Microsoft/Google are moving into this space. (Mitigation: Win fast with RBI-specific moats).

---

## Summary

**Go-To-Market**: Build a **RBI FREE-AI compliant internal AI assistant** with a **sandboxed, untrusted SLM** that enforces hard department silos via a **deterministic, claim-based architecture** with full audit trails and data localization in India. Close 3 NBFCs/fintechs first, use them as references for private banks, then go upstream.

*   **NBFCs**: First target.
*   **6 Months**: To first pilot.
*   **₹30L–1Cr**: Per bank / year.
*   **SLM Sandboxing**: Your defensible moat.
*   **RBI FREE-AI**: Your compliance story.
