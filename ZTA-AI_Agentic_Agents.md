# ZTA-AI — Agentic Agents
## Explanation · Examples · Implementation Plan

> **Internal Engineering Reference · April 2026 · v1.0**

---

## How to Read This Document

Each agent section follows the same structure:

- **What it is** — plain-language description of the agent's purpose
- **How it works in ZTA** — the exact mechanics: trigger, data access, scope enforcement, confirmation, execution, audit
- **Real examples** — concrete input/output walkthroughs
- **Implementation plan** — what needs to be built, in what order, with engineering estimates

Every agent operates through the **Action Registry**. No agent can take an action that has not been pre-approved and configured by the IT admin. The LLM recognises intent and personalises output — it never decides what actions are possible.

### Universal Pipeline (applies to every agent)

```
User trigger / Scheduled trigger / Data event
        ↓
Intent Classifier     → is this agentic or informational?
        ↓
Action Resolver       → which registered action matches?
        ↓
Eligibility Check     → does this persona have permission?
        ↓
Scope Guard           → is the data within this user's allowed scope?
        ↓
Sensitive Field Monitor (always on, parallel)
        ↓
Confirmation UI       → (if requires_confirmation = true)
        ↓
Action Executor       → atomic execution with rollback on failure
        ↓
Audit Log + Notification Dispatch
```

---

## Agent 1 — Result Notification Agent

### What it is

Detects when exam results are published, generates a personalised performance summary for each affected student, and optionally surfaces improvement suggestions based on pre-configured policy rules. Fully automated once configured — zero manual intervention needed per student.

### How it works in ZTA

**Trigger type:** Event-based (data change detection)

The IT admin configures: *"When new result records appear in the results table for Semester X, fire this agent for all students with results in that batch."* The Trigger Engine polls the results data source on each sync cycle (configurable, default every 15 minutes). When new records are detected, it identifies affected students and queues one action instance per student.

**Data access:** The agent reads only the triggering student's own result records. The Scope Guard enforces `own_id` — one student's notification process cannot touch another student's data even if they are in the same trigger batch.

The LLM receives only abstract performance slots derived from the student's results:

```
subject_name, score_pct, grade, class_average_pct, rank_in_class,
attendance_pct, pass_fail_status
```

It never receives raw database identifiers, roll numbers of other students, or any field outside the declared `required_data_scope` of this action.

**Improvement suggestions:** These are not free-form LLM-generated advice. The IT admin pre-configures a rule set in the Action Registry:

```
if score_pct < 40  → suggest: remedial classes, faculty consultation
if score_pct 40–50 → suggest: self-study resources, peer study groups
if attendance < 75 → suggest: attendance improvement plan (mandatory note)
if all_pass = true → suggest: merit scholarship eligibility check
```

The LLM personalises the language around these pre-defined rules. It cannot recommend actions outside the configured set.

**Notification channel:** Sent via the university's configured notification service (email via their SMTP, in-app notification, or SMS gateway). ZTA never sends from its own domain on the university's behalf.

**Confirmation:** `requires_confirmation: false` for this agent — it is fully automated. The IT admin reviewed and approved the trigger configuration at setup time. Individual per-student confirmation would defeat the purpose of automation.

**Audit trail:** Per-student log entry — student ID (tokenised), result summary hash, improvement rules triggered, notification channel, delivery status (delivered / bounced / pending), timestamp.

### Real Example

**Trigger condition met:** Results for CS Semester 3 published at 14:32.

**Trigger Engine fires for student Priya Sharma (tokenised as STU-00412):**

Data fetched from results connector (as ClaimSet):
```
mathematics: 74%, grade B, class average 68%
physics: 88%, grade A, class average 71%
economics: 51%, grade C, class average 63%
attendance: 71%
overall_result: PASS
```

LLM generates notification (filling pre-configured template):

```
Subject: Your Semester 3 Results are Now Available

Dear Priya,

Your Semester 3 results have been published. Here is your 
performance summary:

  Mathematics   74%   Grade B   (Class avg: 68%) ✓ Above average
  Physics       88%   Grade A   (Class avg: 71%) ✓ Top performer
  Economics     51%   Grade C   (Class avg: 63%)

Overall Result: PASS

Suggested next steps:
→ Your attendance this semester was 71%, below the 75% requirement.
  Please review your attendance record and speak with your advisor
  before Semester 4 registration.
→ Your Physics score qualifies you to apply for the Department
  Merit Award. Applications close 30th April.

For any queries, contact your academic advisor or visit the 
Student Services portal.

— ZTA-AI Academic Notifications
   [University Name]
```

Notification dispatched via university SMTP at 14:33. Delivery confirmed 14:34. Audit event written.

### Implementation Plan

**Phase:** Phase 3 (Agentic Layer), after Action Registry and Trigger Engine are stable.

**Action Registry entry:**
```json
{
  "action_id": "result_notification_v1",
  "trigger_type": "event",
  "trigger_condition": "new_records_in:results WHERE semester = :configured_semester",
  "required_data_scope": ["results.own", "attendance.own"],
  "output_type": "notification",
  "requires_confirmation": false,
  "allowed_personas": ["student"],
  "improvement_rules": "configurable_by_it_admin",
  "notification_template": "configurable_by_it_admin",
  "rate_limit": "1_per_result_publication_event"
}
```

**What needs to be built:**

1. Trigger Engine event listener for results table change detection
2. Per-student action queue with deduplication (prevent double-sending if sync fires twice)
3. ClaimSet extraction from results connector scoped to `own_id`
4. Rule engine that evaluates improvement_rules config against the ClaimSet
5. LLM template fill with abstract slots (no raw data passed to LLM)
6. Notification dispatch via university SMTP/SMS gateway
7. Per-student delivery tracking and retry on bounce
8. Audit event writer

**Engineering estimate:** 4–5 days (excluding Trigger Engine infrastructure, which is shared)

**Dependencies:** Trigger Engine, Notification Service, results connector certified, SMTP configured by IT admin

---

## Agent 2 — Fee Reminder Agent

### What it is

Detects students with unpaid or overdue fees based on configured schedule and threshold conditions, and sends personalised reminders with payment context. Three configurable reminder stages: advance notice, due date, and overdue escalation.

### How it works in ZTA

**Trigger type:** Scheduled + threshold-based (two conditions, both configurable)

The IT admin sets up three trigger rules in the admin dashboard:

```
Rule 1: 3 days before due_date WHERE balance > 0 → send advance reminder
Rule 2: on due_date WHERE balance > 0             → send due date reminder
Rule 3: 7 days after due_date WHERE balance > 0   → send overdue notice
        (with late fee amount appended if late_fee_policy configured)
```

The Trigger Engine evaluates all three conditions on each sync cycle. A student only receives the relevant reminder based on their current state — if they paid between Rule 1 and Rule 2, Rule 2 does not fire for them.

**Data access:** Fee records scoped to `own_id`. The agent sees: amount due, fee breakdown, due date, payment history, partial payments. It does not see any other student's fee data.

**Rate limiting:** A student cannot receive more than 1 fee reminder per day regardless of how many rules qualify. The Notification Service enforces this.

**Confirmation:** `requires_confirmation: false` — fully automated. Configuration was reviewed at IT admin setup.

**Escalation path:** Rule 3 (overdue) automatically cc's the finance team contact configured by the IT admin, in addition to notifying the student.

**Audit trail:** For each reminder — student ID (tokenised), trigger rule that fired, amount in reminder, notification channel, delivery status, timestamp.

### Real Example

**Date: 12th April. Fee due date: 15th April. Rule 1 fires (3 days before).**

Student Rahul Verma (STU-00891) has ₹30,000 outstanding (partial payment of ₹15,000 already made on 3rd April).

ClaimSet fetched:
```
total_fee: 45000
paid_amount: 15000
outstanding: 30000
due_date: 2026-04-15
fee_components: [tuition: 35000, library: 5000, exam: 5000]
payment_history: [{date: 2026-04-03, amount: 15000, method: UPI}]
```

Notification sent:

```
Subject: Fee Payment Reminder — ₹30,000 Due on 15th April

Dear Rahul,

This is a friendly reminder that your semester fee payment 
is due in 3 days.

  Total fee:        ₹45,000
  Paid so far:      ₹15,000 (paid 3rd April via UPI)
  Outstanding:      ₹30,000

  Due date:         15th April 2026

To pay now, reply to this message or visit the Student 
Portal and click "Pay Fees" to generate your payment link.

If you have already paid, please allow 24 hours for your 
records to update.

— Fee Management
   [University Name]
```

**Date: 22nd April. Rahul has still not paid. Rule 3 fires (7 days overdue).**

```
Subject: ⚠️ Overdue Fee Notice — Immediate Action Required

Dear Rahul,

Your semester fee payment of ₹30,000 was due on 15th April 
and remains outstanding.

  Outstanding amount:  ₹30,000
  Days overdue:        7 days
  Late fee (if any):   ₹500 (as per university policy)
  Total now due:       ₹30,500

Please make payment immediately to avoid further action.
Your exam registration may be affected if fees remain 
unpaid after 30th April.

[Finance team has been notified of this outstanding balance.]

— Fee Management
   [University Name]
```

Finance team receives a parallel notification listing all overdue accounts.

### Implementation Plan

**Action Registry entry:**
```json
{
  "action_id": "fee_reminder_v1",
  "trigger_type": "scheduled+threshold",
  "trigger_rules": "configurable_by_it_admin (3_rules)",
  "required_data_scope": ["fees.own"],
  "output_type": "notification",
  "requires_confirmation": false,
  "allowed_personas": ["student", "staff"],
  "rate_limit": "1_per_day_per_student",
  "escalation": "rule3_cc_finance_contact"
}
```

**What needs to be built:**

1. Scheduled Trigger Engine rules for 3 reminder stages
2. Student eligibility evaluation at trigger time (check current balance before sending)
3. Late fee calculation from policy config
4. Three configurable notification templates (advance / due date / overdue)
5. Finance team cc on Rule 3 escalation
6. Deduplication: if student pays between trigger evaluation and notification dispatch, suppress send
7. Delivery tracking and bounce handling
8. Audit event per reminder instance

**Engineering estimate:** 3–4 days (Trigger Engine infrastructure shared across all agents)

**Dependencies:** Trigger Engine, Notification Service, fee connector certified, SMTP/SMS configured

---

## Agent 3 — UPI Payment Agent

### What it is

Generates a UPI payment request pre-filled with the student's correct outstanding amount and a unique order ID, and delivers the payment link through the chat interface. ZTA never handles, processes, or records the actual financial transaction — it only creates the entry point.

### How it works in ZTA

**Hard constraint first:** This agent has `financial_transaction: false` and `write_to_source: false` in its Action Registry entry. It cannot initiate, approve, record, or modify any financial transaction. It can only call the university's payment gateway API to generate a URL.

**Trigger type:** User-initiated

Student says: *"I want to pay my fees"* or *"generate a payment link"* or *"how do I pay my outstanding balance?"*

**Execution flow:**

```
1. Intent Classifier → UPI Payment action identified
2. Action Resolver  → matches "upi_payment_link_generation" in Action Registry
3. Eligibility Check → student persona has payment_link_permission: true?
4. Scope Guard      → read fee data scoped to own_id
5. Fee connector returns:
   outstanding_amount: 30000
   student_id_alias: STU-00891  (alias, not raw DB ID)
   fee_period: Semester 3 2026
6. Agent calls university payment gateway API (configured by IT admin):
   POST /v1/orders
   {
     amount: 3000000,  (in paise)
     order_id: "ZTA-STU00891-SEM3-20260412143201",
     description: "Semester 3 Fee Payment",
     customer_name: "[student name from HR connector]",
     expiry: 1800  (30 minutes)
   }
7. Gateway returns: payment_url
8. Agent surfaces link to student in chat
9. Confirmation: not required (link generation is read-only + reversible — 
   unused links simply expire)
10. Audit event: link generated, order_id, amount, expiry, 
    gateway response status
```

**After the student pays:** The payment gateway webhooks directly to the university's finance system. On the next sync cycle, ZTA's fee connector picks up the updated payment status. The student's outstanding balance updates in ZTA automatically — no manual reconciliation needed.

**ZTA never knows if the payment was completed** — it only knows that a link was generated. The financial outcome lives entirely in the university's own systems.

### Real Example

**Student:** *"Can you generate a payment link for my pending fees?"*

**ZTA:** 
```
I can see you have an outstanding fee balance of ₹30,000 
for Semester 3 (Tuition: ₹25,000 · Library: ₹3,000 · Exam: ₹2,000).

Here is your personalised UPI payment link:

  ┌─────────────────────────────────────┐
  │  Pay ₹30,000 — Semester 3 Fees      │
  │  [PAY NOW →]                        │
  │  Link valid for 30 minutes           │
  │  Order ID: ZTA-STU00891-SEM3-...    │
  └─────────────────────────────────────┘

This link is unique to your account and pre-filled with 
your details. You can pay via any UPI app 
(GPay, PhonePe, Paytm, etc.).

If you have any issues with the payment, contact the 
Finance Office at finance@university.edu.
```

**Student:** *"Can you also pay for my roommate Karan? He asked me to."*

**ZTA:** 
```
I can only generate a payment link for your own account. 
Each student needs to log in and generate their own 
payment link. Please ask Karan to access ZTA-AI with 
his own credentials.
```
*(Scope Guard blocked the cross-user request before it reached the payment gateway call.)*

### Implementation Plan

**Action Registry entry:**
```json
{
  "action_id": "upi_payment_link_v1",
  "trigger_type": "user_query",
  "required_data_scope": ["fees.own"],
  "output_type": "link",
  "financial_transaction": false,
  "write_to_source": false,
  "requires_confirmation": false,
  "allowed_personas": ["student", "staff", "faculty"],
  "payment_gateway": "configurable_by_it_admin",
  "link_expiry_seconds": 1800
}
```

**What needs to be built:**

1. Payment gateway connector interface (Razorpay / PayU / CCAvenue — pluggable via connector SDK)
2. Order ID generation format (unique, deterministic from student alias + semester + timestamp)
3. Amount fetched from fee connector (own_id scope), converted to gateway's currency unit
4. Gateway API call with error handling (gateway down → graceful error message)
5. Link rendered in chat with expiry countdown
6. Scope Guard enforcement preventing cross-user link generation
7. Audit event: order_id, amount, gateway, expiry, student alias (not name)
8. On fee connector sync: detect paid status, surface confirmation to student proactively

**Engineering estimate:** 3 days (excluding payment gateway integration, which depends on which gateway the university uses — add 1–2 days per gateway integration)

**Dependencies:** Fee connector, Payment Gateway API credentials configured by IT admin, Notification Service for post-payment confirmation

---

## Agent 4 — Refund Processing Agent

### What it is

Handles student refund requests end-to-end — validates eligibility against policy, calculates the refund amount, creates the request in the finance system, routes it to the finance team, and tracks status. A human finance officer always approves before any money moves.

### How it works in ZTA

**Risk class:** Medium-High. Write-lite action with financial implications. Every step requires explicit confirmation.

**Trigger type:** User-initiated

Student says: *"I want to request a refund for my hostel fee. I did not use the hostel this semester."*

**Validation flow (automated, against configured policy):**

```
Step 1: Eligibility check
  → Is the fee category refundable? (configured in refund policy)
  → Is the request within the refund window? (policy: 30 days from payment)
  → Does the student have a confirmed payment for this category?
  → Is there already an active refund request for this category?
  → Result: ELIGIBLE / INELIGIBLE (with specific reason)

Step 2: Amount calculation
  → Refund policy rules (configured by IT admin):
    0–7 days from payment date  → 100% refund
    8–30 days                   → 50% refund
    31+ days                    → 0% refund (ineligible)
  → Payment date: 1st March. Current date: 12th April = 42 days
  → Result: 0% refund under standard policy

  [If eligible:]
  → Calculated refund amount = payment amount × applicable percentage
```

If ineligible, the agent explains clearly and does not proceed:

```
"Your hostel fee payment was made 42 days ago (1st March).
 Our refund policy covers requests within 30 days of payment.
 Unfortunately this request is outside the eligible window.
 
 If you believe this is an exceptional circumstance, you can
 raise a manual review request with the Finance Office at
 finance@university.edu (reference: your student ID)."
```

If eligible:

```
Step 3: Confirmation UI
  "You are requesting a refund for:
   
   Category:        Hostel Fee
   Amount paid:     ₹16,000 (paid 2nd April)
   Refund amount:   ₹8,000 (50% — request is 15 days after payment)
   Policy applied:  Hostel Refund Policy v2.1
   
   This request will be sent to the Finance department.
   Expected processing time: 7–10 working days.
   
   [Confirm Request]  [Cancel]"

Step 4: On confirm
  → Creates refund request record in finance system via connector
    (write: INSERT into refund_requests, NOT UPDATE to approved_refunds)
  → Finance team notified:
    student alias, fee category, amount, policy basis, request timestamp
  → Student receives: reference number + expected timeline
  → Audit log: full request payload, policy version applied,
    confirmation captured, finance notification delivery status

Step 5: Finance officer approves in their system
  → On next sync, ZTA detects status change: pending → approved
  → Student notified: "Your refund of ₹8,000 has been approved.
    It will be credited to your account within 3–5 working days."
```

**ZTA constraint:** The agent creates a refund request. It cannot approve its own request. Approval is always a human decision in the finance system. ZTA only surfaces the status change after the fact.

### Real Example

**Student:** *"I withdrew from the university last week. Can I get a refund on my tuition?"*

**ZTA checks:**
- Fee category: tuition — refundable: yes
- Payment date: 15th March. Withdrawal date: 8th April. Days elapsed: 24
- Policy: 1–30 days → 75% refund of prorated unused amount
- Prorated unused: 2.5 months remaining of 5-month semester = 50% of tuition
- Refund = 75% × 50% × ₹35,000 = ₹13,125

```
ZTA:
"Based on your withdrawal date and payment date, here is 
your refund calculation:

  Tuition paid:            ₹35,000
  Unused portion (50%):    ₹17,500
  Refund rate (24 days):   75%
  Calculated refund:       ₹13,125
  Policy applied:          Tuition Refund Policy v3.0, Section 4.2

This request will go to the Finance department for approval.
Processing time: 10–15 working days for withdrawal refunds.

[Confirm Refund Request of ₹13,125]  [Cancel]"
```

Student confirms. Reference number generated. Finance team notified.

### Implementation Plan

**Action Registry entry:**
```json
{
  "action_id": "refund_request_v1",
  "trigger_type": "user_query",
  "required_data_scope": ["fees.own", "refund_policy.read"],
  "output_type": "workflow",
  "write_target": "refund_requests (INSERT only)",
  "requires_confirmation": true,
  "approval_level": "finance_officer",
  "allowed_personas": ["student", "staff", "faculty"],
  "policy_document": "configurable_by_it_admin"
}
```

**What needs to be built:**

1. Refund policy rule engine (configurable: categories, windows, percentages)
2. Eligibility evaluation: payment date lookup, window calculation, duplicate request check
3. Prorated calculation for partial-period refunds
4. Confirmation UI with policy version cited (for audit clarity)
5. Write to `refund_requests` table via finance connector (INSERT only, no UPDATE or approval)
6. Finance team notification with full context
7. Student notification on submission
8. Sync-based status tracker: poll refund_requests status field, notify student on approval/rejection
9. Audit event: full payload, policy version, timestamps at each stage

**Engineering estimate:** 5–6 days (policy rule engine is the most complex component)

**Dependencies:** Fee connector (read), Finance system connector (write to refund_requests), Notification Service, policy document uploaded and parsed by IT admin

---

## Agent 5 — Email Draft and Send Agent

### What it is

Drafts structured emails for common university workflows (leave requests, complaints, formal reminders, meeting requests) using pre-configured templates, presents the draft to the user for review, and sends via the university's own SMTP configuration after explicit confirmation.

### How it works in ZTA

**Two modes configurable per email type:**

- **Draft-only mode:** Agent drafts the email, user copies and sends manually
- **Draft-and-send mode:** Agent drafts, user reviews and confirms, agent sends via SMTP

Default: all email types start in draft-only mode. IT admin promotes specific types to draft-and-send after reviewing the template.

**Trigger type:** User-initiated

**Template system:** Every email type has a registered template in the Action Registry. Templates define:
- Allowed recipients (from/to rules)
- Required data slots (what the agent fetches from connectors)
- User-provided slots (what the user must supply)
- Fixed content (boilerplate that cannot be changed)

**Recipient enforcement:** The agent can only send to recipients within the IT admin-configured approved list. Default approved list: any email address within the university's own domain. External addresses require explicit IT admin approval and a separate Action Registry entry.

**Sending constraint:** The agent cannot send on behalf of a different user than the logged-in user. The `From:` field is always the logged-in user's registered email — never spoofed, never configurable by the end user.

### Real Example A — Leave Request

**Faculty member:** *"Draft a leave application for me from 15th to 17th April. Family emergency."*

Agent fetches from HR connector (own scope):
```
user_name: Prof. Anil Mehta
department: Computer Science
designation: Assistant Professor
HOD_email: dr.sharma@university.edu
leave_balance_casual: 8 days remaining
```

Draft generated:
```
────────────── DRAFT — Please review before sending ──────────────

To:      Dr. Sharma, HOD — Computer Science
         dr.sharma@university.edu
From:    Prof. Anil Mehta (anil.mehta@university.edu)
Subject: Leave Application — 15th April to 17th April 2026

Respected Dr. Sharma,

I am writing to request casual leave from 15th April to 
17th April 2026 (3 days) due to a family emergency.

I will ensure all my classes are covered:
  [Please add handover arrangements here]

My current casual leave balance is 8 days. This request 
will use 3 days, leaving a balance of 5 days.

I will remain reachable by email during this period for 
any urgent matters.

Thanking you,
Prof. Anil Mehta
Assistant Professor, Computer Science

──────────────────────────────────────────────────────────────────

  Leave balance after this request: 5 casual days remaining

  [Edit draft]  [Send to Dr. Sharma]  [Save as draft]  [Cancel]
```

**Prof. Mehta clicks Send.** Email dispatched via university SMTP. Leave request record created in HR system (if leave_application action is also registered). HOD receives the email + an in-app notification if they are a ZTA user.

### Real Example B — Student Complaint

**Student:** *"Help me draft a complaint about the library being closed during exam week."*

```
────────────── DRAFT — Please review before sending ──────────────

To:      Student Grievance Cell
         grievance@university.edu
From:    Priya Sharma (priya.sharma@university.edu)
Subject: Complaint — Library Closure During Examination Period

Dear Grievance Committee,

I am a student of [your department — please fill in] and 
I am writing to raise a concern regarding library access 
during the current examination period.

Issue: [Please describe the specific dates and impact here]

This has affected my exam preparation because:
[Please describe the impact here]

I request that:
1. Library hours be extended during examination periods
2. This matter be reviewed for future semesters

I am available for any further clarification.

Yours sincerely,
Priya Sharma
[Student ID — please verify]

──────────────────────────────────────────────────────────────────
  ⚠️  This draft has 3 fields for you to fill in before sending.
  
  [Edit draft]  [Send after editing]  [Cancel]
```

Note: The agent flags incomplete slots and will not allow sending until the user has reviewed the draft. It cannot auto-fill details it does not know (like specific dates of the incident) and does not invent them.

### Implementation Plan

**Action Registry entries (one per email type):**
```json
{
  "action_id": "email_leave_request_v1",
  "trigger_type": "user_query",
  "required_data_scope": ["hr.own (leave_balance, HOD_email)"],
  "user_provided_slots": ["handover_arrangements"],
  "output_type": "email",
  "send_mode": "draft_and_send",
  "requires_confirmation": true,
  "allowed_recipients": "university_domain_only",
  "allowed_personas": ["faculty", "staff", "student"],
  "smtp_config": "university_configured"
}
```

**What needs to be built:**

1. Template registry: store and version email templates per type
2. Slot resolver: identify which slots come from connectors (auto-fetched) vs. user (prompted)
3. Draft renderer: produce formatted draft with slot values filled in
4. Incomplete slot detector: flag unfilled slots, block send until reviewed
5. Confirmation UI with full draft preview
6. SMTP dispatch via university's configured credentials (not ZTA's)
7. Recipient allowlist enforcement (block sends to non-approved domains)
8. From-address enforcement (always logged-in user's registered email)
9. Delivery status tracking and bounce handling
10. Audit: email metadata (not full body), recipient, sender, timestamp, delivery status

**Engineering estimate:** 4–5 days for infrastructure + 1 day per additional email type template

**Dependencies:** HR connector (for leave data), Notification Service (SMTP), IT admin has configured SMTP credentials and approved recipient domains, at least 3 email templates configured before launch

---

## Agent 6 — Bulk Notification Agent

### What it is

Enables authorised staff (admins, department heads, registrar) to send targeted announcements or alerts to groups of users defined by role, department, year, or custom criteria — all with full audit trail and rate limiting.

### How it works in ZTA

**Access restricted by design:** Only personas with `bulk_notify_permission: true` in their Action Registry configuration can trigger this agent. Students and regular faculty cannot initiate bulk sends.

**Trigger type:** Admin-initiated (from chat or admin dashboard)

**Targeting logic:**

The target group is defined by a query against user records within the admin's own scope. The Scope Guard enforces this — a department head can target their department's students. They cannot target another department's students or staff. A registrar can target institution-wide. Scope is enforced at the target resolution step, not by trust.

**Rate limiting:** No individual user receives more than N notifications per day (IT admin configures N, default: 3). If a student already received 3 notifications today and qualifies for a bulk send, they are silently excluded from that batch. The IT admin sees the actual reach count vs. the qualified count in the send report.

**Confirmation with reach count:** Before any bulk send, the agent presents:
- Exact target criteria applied
- Number of recipients who will receive it
- Number excluded by rate limiting
- Full message preview

**Audit trail:** Sender ID, target criteria query, recipient count (not recipient list — privacy), message hash, timestamp, delivery success rate, rate-limit exclusion count.

### Real Example A — Exam Rescheduling Alert

**Registrar:** *"Send an urgent alert to all final year students that the Physics exam has been rescheduled to 20th April."*

```
Target resolution:
  Criteria: year = final, status = active
  Qualified recipients: 847 students
  Rate-limit exclusions: 12 students (already at daily limit)
  Actual send count: 835

──────────────── CONFIRM BULK SEND ────────────────

To:      835 Final Year Students (12 excluded by daily limit)
From:    Registrar's Office
Channel: Email + In-app notification
Subject: URGENT: Physics Exam Rescheduled

URGENT NOTICE

The Physics (PHY-401) examination scheduled for 18th April 
has been rescheduled to 20th April 2026 at the same time 
and venue.

Please update your exam schedule accordingly.

For queries: exams@university.edu

  [Send to 835 students]  [Edit]  [Cancel]
```

**Registrar confirms.** 835 notifications dispatched. Send report generated showing delivery success rate.

### Real Example B — Scope Enforcement

**Department head (Computer Science):** *"Send a notification to all students in the university about our department's upcoming hackathon."*

```
ZTA:
"Your notification permissions are scoped to Computer Science 
department students. I can send this to 312 Computer Science 
students.

To reach all university students, this request needs to go 
through the Registrar's Office, which has institution-wide 
notification permissions.

Would you like me to send to Computer Science students only?

  [Send to 312 CS Students]  [Cancel]"
```

The system does not refuse — it explains the scope constraint and offers what is actually permitted.

### Implementation Plan

**Action Registry entry:**
```json
{
  "action_id": "bulk_notification_v1",
  "trigger_type": "user_initiated",
  "required_data_scope": ["user_records (within sender scope)"],
  "output_type": "bulk_notification",
  "requires_confirmation": true,
  "approval_level": "self (confirmation UI is the gate)",
  "allowed_personas": ["registrar", "dept_head", "admin", "finance_officer"],
  "bulk_notify_permission": true,
  "rate_limit_per_recipient_per_day": "configurable (default: 3)",
  "scope_enforcement": "sender_department_scope"
}
```

**What needs to be built:**

1. Target resolution engine: translate natural language criteria into a scoped user query
2. Scope Guard at target resolution (enforce sender's departmental boundary)
3. Rate limit check: cross-reference target list with today's notification count per user
4. Reach count calculation (qualified vs. actual after rate limit exclusions)
5. Confirmation UI with full message preview and reach counts
6. Bulk dispatch via Notification Service (email + in-app, channel configured per recipient preference)
7. Delivery tracking at batch level (success rate, bounce count)
8. Send report generated and stored for IT admin review
9. Audit: sender alias, criteria hash, counts, message hash, timestamp

**Engineering estimate:** 4 days

**Dependencies:** User directory connector, Notification Service, bulk rate limiter (shared infrastructure)

---

## Agent 7 — Leave Approval Agent

### What it is

Manages the complete leave workflow — application, policy validation, routing to the correct approver, approval or rejection, and status notification. The approval step is always a human decision. ZTA manages the routing and tracking.

### How it works in ZTA

**Risk class:** Medium. Multi-step workflow with a write operation (creating a leave record) and a mandatory human approval node.

**Trigger type:** User-initiated (applicant) + system-routed (approver)

**Org hierarchy requirement:** The IT admin configures the approval hierarchy in the admin dashboard:
```
Student leave    → Academic Advisor → HOD
Faculty leave    → HOD → Dean (if > 5 days)
Staff leave      → Department Manager → HR Head (if > 10 days)
```

**Full workflow:**

```
Stage 1: Application (Applicant)
  User: "I want to apply for leave from 15th to 17th April"
  
  Agent checks (all automated):
  ├── Leave balance: sufficient? (own HR data)
  ├── Leave type eligibility: casual, sick, earned — which applies?
  ├── Blackout dates: any exam/mandatory dates in requested range?
  ├── Existing requests: any pending request overlapping these dates?
  └── Result: ELIGIBLE or INELIGIBLE with reason

  If eligible → Confirmation UI:
  "Leave request: 15–17 April (3 casual days)
   Balance after: 5 casual days remaining
   Approver: Dr. Sharma (HOD)
   [Submit]  [Cancel]"

Stage 2: Routing (System)
  On submit:
  ├── Leave record created in HR system (status: PENDING)
  ├── Approver identified from org hierarchy config
  ├── Approver notified (email + in-app):
  │   "[Applicant] has requested 3 days casual leave
  │    Dates: 15–17 April | Balance: 8 → 5 days
  │    Scheduled duties during this period: [from timetable connector]
  │    [Approve]  [Reject]  [Request More Info]"
  └── Applicant notified: "Your request has been forwarded to Dr. Sharma"

Stage 3: Approver Action (Human)
  Approver clicks Approve (in email link or ZTA chat):
  ├── Leave record updated: PENDING → APPROVED
  ├── Leave balance deducted in HR system
  ├── Applicant notified: "Your leave has been approved"
  ├── Calendar blocked (if calendar connector configured)
  └── Audit: approver identity, decision, timestamp, reason (if rejected)

Stage 4: Rejection flow
  If rejected:
  ├── Applicant notified with reason
  ├── Balance unchanged
  └── Option: re-apply with modified dates
```

**ZTA constraint:** The approver cannot be the same person as the applicant (system enforces this — if org hierarchy somehow routes to self, it escalates to the next level). Auto-approval is off by default — IT admin can enable it for specific leave types (e.g., single-day sick leave) as a configuration option.

### Real Example

**Student Arjun (CS Semester 5):** *"Apply for 2 sick leave days — today and tomorrow. I have fever."*

```
ZTA checks:
  Leave balance: 6 sick days remaining ✓
  Blackout dates: no exam or mandatory event today/tomorrow ✓
  Existing requests: none overlapping ✓

ZTA:
"Here is your sick leave request:

  Type:     Sick Leave
  Dates:    12th April – 13th April 2026 (2 days)
  Reason:   Illness (as provided)
  Approver: Dr. Pradeep (Academic Advisor)
  
  Balance:  6 sick days → 4 sick days after approval

  Note: A medical certificate may be required for sick 
  leave if requested by your advisor.

  [Submit Request]  [Cancel]"
```

Arjun submits. Dr. Pradeep receives:

```
Leave Approval Request

Arjun Kumar has requested 2 sick leave days
Dates: 12–13 April 2026
Reason: Illness
Sick leave balance: 6 days (will become 4 if approved)

Scheduled classes during this period:
  12 Apr: Data Structures Lab (10:00–12:00) — 18 students enrolled
  13 Apr: No scheduled duties

  [Approve]  [Reject]  [Request More Info]
```

Dr. Pradeep approves. Arjun receives:

```
"Your sick leave for 12–13 April has been approved by 
Dr. Pradeep. Your updated sick leave balance is 4 days."
```

### Implementation Plan

**Action Registry entry:**
```json
{
  "action_id": "leave_application_v1",
  "trigger_type": "user_query",
  "required_data_scope": ["hr.own (balance)", "timetable.own", "org_hierarchy.read"],
  "write_target": "leave_requests (INSERT) + leave_balance (UPDATE on approval)",
  "output_type": "workflow",
  "requires_confirmation": true,
  "approval_level": "org_hierarchy_configured",
  "human_approval_required": true,
  "auto_approve_option": "configurable_per_leave_type",
  "allowed_personas": ["student", "faculty", "staff"]
}
```

**What needs to be built:**

1. Leave policy engine: leave types, balances, blackout dates (configurable per institution)
2. Org hierarchy config in admin dashboard: maps personas to approvers
3. Balance check and deduction logic (deduct only on approval, not on application)
4. Blackout date check against timetable connector (if configured)
5. Approval routing: identify correct approver from hierarchy config
6. Approver notification with action buttons (Approve / Reject / More Info)
7. Action button handling (approver clicks in email or ZTA chat)
8. Status tracking and applicant notification at each stage
9. Audit: full workflow trail with timestamps at each stage
10. Escalation: if approver does not act within N days (configurable), escalate to next level

**Engineering estimate:** 7–8 days (most complex workflow of the set)

**Dependencies:** HR connector (read balance, write leave records), Timetable connector (optional, for duty impact), Org hierarchy configuration in admin dashboard, Notification Service

---

## Agent 8 — Meeting Scheduler Agent

### What it is

Checks calendar availability of specified participants, finds overlapping free slots, presents options to the requestor, and sends calendar invites after confirmation. Participants' free/busy status is visible — but not the content of their appointments.

### How it works in ZTA

**Privacy boundary:** The agent can see that a participant is **busy** at a given time. It cannot see the title, description, or attendees of that appointment. This is a hard scope constraint in the calendar connector — it requests free/busy data only, not full calendar access.

**Trigger type:** User-initiated

**Execution flow:**

```
1. User: "Schedule a 1-hour project review with my 4 research students next week"

2. Participant resolution:
   → "my 4 research students" resolved from org hierarchy + class roster
     (own scope: only students associated with the requestor's courses)
   → Participant list: [Student A, Student B, Student C, Student D]

3. Availability fetch:
   → Calendar connector fetches free/busy for each participant
     for the requested window (next week, Mon–Fri, 9am–5pm)
   → Own calendar also fetched for conflict check

4. Slot finder:
   → Identifies windows where ALL participants are free simultaneously
   → Minimum slot: 1 hour (requested duration)
   → Returns top 3 options ranked by:
     a. Earliest available
     b. Mid-week preference (configurable)
     c. Morning preference (configurable)

5. Options presented to requestor:
   "Available slots for all 5 participants next week:
    
    1. Monday 14 Apr, 10:00–11:00 AM
    2. Tuesday 15 Apr, 2:00–3:00 PM
    3. Thursday 17 Apr, 11:00–12:00 PM
    
    [Select Monday]  [Select Tuesday]  [Select Thursday]  [Show more]"

6. Requestor selects slot

7. Confirmation UI:
   "Send calendar invite for:
    Project Review Meeting
    Monday 14 April, 10:00–11:00 AM
    Attendees: Prof. Mehta + 4 students
    Location: [please add — or leave blank for virtual]
    [Add meeting link]  [Confirm Send]  [Cancel]"

8. On confirm:
   → Calendar invite sent via university's calendar API
     (Google Calendar or Microsoft 365, configured by IT admin)
   → All attendees receive invite with accept/decline option
   → Audit: requestor alias, attendee count (not names), 
     slot selected, invite dispatch timestamp
```

### Real Example

**HOD:** *"I need to schedule a 30-minute one-on-one with each of my 8 faculty members this week."*

```
ZTA:
"I'll find available 30-minute slots for one-on-one meetings
with each of your 8 faculty members.

Here are the first 3 faculty members and their earliest 
available slots this week that also fit your calendar:

  Dr. Sharma:    Monday 10:30–11:00 AM
  Prof. Mehta:   Monday 2:00–2:30 PM
  Dr. Pillai:    Tuesday 9:00–9:30 AM

Would you like me to schedule these 3 now and show you 
options for the remaining 5?

  [Schedule these 3]  [Show all 8 options first]  [Cancel]"
```

Note: The agent batches efficiently rather than overwhelming the user with 8 separate confirmations.

### Implementation Plan

**Action Registry entry:**
```json
{
  "action_id": "meeting_scheduler_v1",
  "trigger_type": "user_query",
  "required_data_scope": ["calendar.own (free/busy)", "calendar.participants (free/busy only)"],
  "output_type": "calendar_invite",
  "calendar_access_level": "free_busy_only",
  "requires_confirmation": true,
  "allowed_personas": ["faculty", "staff", "dept_head", "admin"],
  "calendar_provider": "configurable (Google / Microsoft 365)"
}
```

**What needs to be built:**

1. Calendar connector (Google Calendar API or Microsoft Graph API — pluggable)
2. Free/busy fetcher (NOT full calendar access — free/busy only, enforced at connector level)
3. Participant resolver: map natural language ("my research students") to user IDs within own scope
4. Slot finder algorithm: overlapping free windows across N participants
5. Slot ranking and top-3 presentation
6. Confirmation UI with meeting details and optional fields (location, link)
7. Invite dispatch via calendar API
8. Batch scheduling support (multiple one-on-ones from single request)
9. Audit: requestor alias, attendee count, slot, dispatch timestamp

**Engineering estimate:** 4–5 days

**Dependencies:** Calendar connector (Google Workspace or Microsoft 365 configured by IT admin), Org hierarchy config for participant resolution

---

## Agent 9 — Payroll Query Agent

### What it is

Answers payroll and salary-related questions for employees within their own scope only. Read-only. Every access to salary data triggers the Sensitive Field Access Monitor automatically.

### How it works in ZTA

**Scope:** The hardest scope restriction of any agent. `own_id` enforced unconditionally. No persona — including HR Staff — can use this agent to query another employee's salary. HR Head and Finance Officer have a separate, explicitly registered `payroll_report_v1` action for bulk payroll views, which has different approval requirements.

**Sensitive field classification:** All salary fields (gross, net, deductions, components, YTD figures) are classified as SENSITIVE. This means:
- Results are never cached
- Full figures are masked in the audit log (hash only, not actual amounts)
- Sensitive Field Access Monitor is notified of every payroll query automatically
- Results are watermarked in the response (invisible to user, traceable if screenshot leaked)

**What it can answer:**

```
"What was my net salary for March?"
"Why did my salary change this month compared to last?"
"What are my current deductions?"
"What is my year-to-date income tax deduction?"
"When is my next salary credited?"
"Show me my payslip for February."
```

**What it cannot answer:**

```
"What does my colleague earn?"     → Scope Guard blocks: not own_id
"Show me the average salary in 
 my department."                   → Aggregate query on sensitive field, 
                                     not registered for this action
"Why does Priya earn more than me?"→ Cross-user comparison, blocked
```

### Real Example

**Employee:** *"My salary was lower this month. Why?"*

Agent fetches from payroll connector (own_id scope):
```
march_net: [SENSITIVE - not logged in plain]
april_net: [SENSITIVE - not logged in plain]
difference: -2340
deductions_march: [PF: 1800, TDS: 3200, professional_tax: 200]
deductions_april: [PF: 1800, TDS: 5540, professional_tax: 200]
tds_change_reason: "Annual tax recalculation applied in April 
                    based on revised income projection"
```

```
ZTA:
"Your April salary is ₹2,340 lower than March. Here's why:

  The difference is in your TDS (Tax Deducted at Source):
  
    March TDS:   ₹3,200
    April TDS:   ₹5,540
    Difference:  ₹2,340 more deducted

  Reason: Your employer has applied the annual TDS 
  recalculation for FY 2026-27 in April. This is standard 
  practice — your projected annual income was revised, 
  and the TDS is spread across the remaining months of 
  the financial year.

  All other components (PF, Professional Tax, basic salary) 
  remain unchanged.

  If you believe the calculation is incorrect, contact 
  HR or Payroll at payroll@university.edu with your 
  employee ID."
```

The actual salary figures are not shown in the response — only the difference and the components that changed. This minimises sensitive data surface area even within the employee's own view. The IT admin can configure whether exact figures are shown (default: yes for own data) or only breakdowns.

### Implementation Plan

**Action Registry entry:**
```json
{
  "action_id": "payroll_query_v1",
  "trigger_type": "user_query",
  "required_data_scope": ["payroll.own"],
  "output_type": "structured_response",
  "cache_results": false,
  "sensitive_field_monitor": true,
  "requires_confirmation": false,
  "allowed_personas": ["faculty", "staff"],
  "cross_user_access": false
}
```

**What needs to be built:**

1. Payroll connector (HR/payroll system — read-only, own_id scope enforcement at connector level)
2. Comparison logic: current vs. previous month diff calculation
3. Deduction change explanation: map deduction field changes to human-readable reasons (TDS recalc, PF revision, etc.)
4. Sensitive field handling: no caching, hash-only in audit log, no raw figures in telemetry
5. Response formatter: show changes and reasons, not raw salary numbers unless configured
6. Sensitive Field Access Monitor hook (fires automatically, no extra code needed if monitor is built)
7. Audit: access event, fields touched (not values), timestamp, response hash

**Engineering estimate:** 3–4 days

**Dependencies:** Payroll/HR connector, Sensitive Field Access Monitor (prerequisite)

---

## Agent 10 — Leave Balance Agent

### What it is

Provides real-time leave balance information and, in apply mode, deducts leave and notifies the manager. The simplest write-lite agent — small scope, clear undo path (if applied incorrectly, IT admin can reverse the record).

### How it works in ZTA

**Two distinct modes:**

**Check mode (read-only):**
```
"How many leaves do I have?"
→ HR connector fetch (own_id)
→ Return breakdown by type: casual, sick, earned, compensatory
→ No confirmation needed, no write, no notification
```

**Apply mode (write-lite):**
```
"Apply 2 sick leave days for today and tomorrow"
→ Balance check: sufficient?
→ Policy check: self-application allowed for sick leave?
→ Blackout check: any mandatory event?
→ Confirmation UI
→ On confirm: deduct from balance, create leave record
→ Manager notification
→ Audit
```

**Manager notification:** This is non-optional for apply mode. The IT admin configures the manager's identity from the org hierarchy. The manager receives a simple informational notification — not an approval request (apply mode is for leave types that do not require prior approval, e.g., sick leave in many institutions). If the leave type requires approval, the Leave Approval Agent handles it instead.

### Real Example

**Employee:** *"How many earned leaves do I have left?"*

```
ZTA:
"Your current leave balance:

  Casual leave:        8 days
  Sick leave:          4 days
  Earned leave:        14 days  ← (as requested)
  Compensatory off:    1 day

  Leave year ends: 31st March 2027
  
  Note: Unused earned leave can be carried forward (up to 
  30 days per university policy)."
```

**Employee:** *"Apply 1 casual leave for this Friday."*

```
ZTA:
"Casual leave application:

  Date:     18th April 2026 (Friday)
  Type:     Casual leave
  Balance:  8 days → 7 days after this application

  Your manager (Dr. Sharma) will be notified.
  No prior approval required for single-day casual leave
  per HR Policy 3.2.

  [Apply Leave]  [Cancel]"
```

Employee confirms. Leave record created. Manager receives:

```
"Prof. Mehta has applied for 1 casual leave day on 
18th April 2026 (Friday). 
Remaining casual balance: 7 days.

(No action required — casual leave applied per HR Policy 3.2.
 Contact HR to reverse if needed.)"
```

### Implementation Plan

**Action Registry entry:**
```json
{
  "action_id": "leave_balance_v1",
  "trigger_type": "user_query",
  "required_data_scope": ["hr.own (leave_balance, policy)"],
  "write_target": "leave_records (INSERT) + leave_balance (UPDATE)",
  "output_type": "response + notification",
  "requires_confirmation": true,
  "approval_level": "self (informational notify to manager)",
  "allowed_personas": ["faculty", "staff", "student"],
  "apply_mode": "configurable_per_leave_type"
}
```

**What needs to be built:**

1. Leave balance fetcher from HR connector (own_id scope)
2. Balance display formatter (all types in one view)
3. Apply mode: eligibility check + blackout check + confirmation UI
4. Write: INSERT leave record, UPDATE balance in HR system via connector
5. Manager notification (informational, not approval request)
6. Year-end carry-forward display from policy config
7. Audit: leave type, dates, balance before/after, notification delivery

**Engineering estimate:** 2–3 days (simplest write-lite agent)

**Dependencies:** HR connector (read + write), org hierarchy for manager resolution, Notification Service

---

## Agent 11 — Sensitive Field Access Monitor

### What it is

This agent runs silently in the background on every query and agentic action that touches classified sensitive fields. It is not user-facing — it is ZTA's insider threat detection layer. It watches for unusual access patterns and alerts the IT head and compliance officer when anomalies are detected.

### How it works in ZTA

**Not triggered by users — triggered by the system.** Every time any query or action touches a field classified as SENSITIVE, PHI, BIOMETRIC, or PERSONAL, the monitor receives a structured event:

```
{
  "user_alias": "USR-00412",
  "persona": "hr_staff",
  "timestamp": "2026-04-12T14:23:11Z",
  "session_id": "SES-7731",
  "fields_accessed": ["salary", "bonus", "tax_deduction"],
  "data_subject_alias": "EMP-00891",
  "query_type": "payroll_query",
  "result_row_count": 1
}
```

The monitor accumulates these events per session and per user, running pattern detection continuously.

**Patterns it detects:**

```
Pattern 1: Volume spike
  → Same user accessing same sensitive field category repeatedly
    in a short window
  → Threshold (configurable): >10 accesses to salary fields in 60 minutes
  → Example: HR staff querying 34 different employees' salary records in 2 hours

Pattern 2: After-hours access
  → Sensitive field access outside normal working hours
  → Baseline: established from 30-day rolling historical access pattern
  → Example: User who always accesses 9am–6pm suddenly accesses at 2:47am

Pattern 3: Bulk result access
  → Single query returns sensitive data for many subjects simultaneously
  → Threshold (configurable): result_row_count > 20 for SENSITIVE fields
  → Even if the user has permission for each record, bulk access is flagged

Pattern 4: Boundary probing
  → Multiple queries in sequence that appear to test what fields are accessible
  → Pattern: 5+ queries in 10 minutes with varying field combinations
    on the same data subject
  → Example: querying salary, then salary+bonus, then salary+bonus+account_number
    in rapid succession

Pattern 5: Cross-context access
  → User accessing sensitive data for subjects outside their normal scope pattern
  → Example: HR officer for Finance department suddenly querying Engineering
    department employee records (even if their persona technically permits it)
```

**Alert routing:**

| Severity | Trigger | Action |
|----------|---------|--------|
| Low | Pattern detected, below threshold | Logged, visible in security panel, no notification |
| Medium | Pattern at threshold | Email alert to IT head and compliance officer |
| High | Pattern significantly above threshold or multiple patterns simultaneously | Immediate alert + session flagged (all actions require additional confirmation until reviewed) |
| Critical | Exfiltration indicators (bulk access + after hours + boundary probing together) | Immediate alert + optional auto-suspend (IT admin must configure this — off by default) |

**What the IT head sees (security panel):**

```
⚠️  HIGH — Unusual Sensitive Field Access Pattern

User:         [USR-00412] — HR Staff
Department:   Human Resources
Time window:  14:00 – 16:12 today (2 hours 12 minutes)

Pattern detected:
  Volume spike: accessed salary fields for 34 different employees
  in 2 hours 12 minutes (threshold: 10 per hour)

Field categories accessed: salary, bonus, tax_deduction, account_number

Access log (last 5 of 34):
  14:51  EMP-00762  salary, bonus
  14:58  EMP-00801  salary, bonus, tax_deduction
  15:04  EMP-00834  salary, bonus
  15:11  EMP-00867  salary, bonus, account_number  ← account_number flagged
  15:18  EMP-00891  salary, bonus, tax_deduction

[View full session log]  [Flag for HR review]  
[Suspend session]  [Mark as legitimate - add note]  [Dismiss]
```

**ZTA constraint:** The monitor can alert and flag. It cannot take action on users. Session suspension requires the IT head to actively click — it is never automatic unless the IT admin has explicitly enabled auto-suspend for critical severity, which is off by default. This prevents false positive disruptions to legitimate work.

### Real Example — Catching an Insider Threat

At 11:45 PM, an HR staff member's session (which started at normal hours but was left open) begins accessing salary records for senior leadership. 22 salary records accessed in 40 minutes.

```
Monitor detects simultaneously:
  Pattern 2: After-hours access (11:45 PM, user's normal pattern is 9am–6pm)
  Pattern 1: Volume spike (22 records in 40 minutes)
  Pattern 3: Result includes account numbers (SENSITIVE tier: FINANCIAL)

Severity: CRITICAL

IT head receives immediate alert (email + SMS if configured):

  ⛔  CRITICAL — Potential Data Exfiltration Detected

  User: [USR-00156] — HR Staff (session started 09:23, now 23:45)
  Time: 23:45 — outside normal working hours
  
  Activity: 22 executive salary records accessed in 40 minutes
  Fields: salary, bonus, bank_account_number, PAN_number
  
  This pattern matches potential data exfiltration indicators:
  ✗ After-hours access
  ✗ Volume spike (22 records, threshold 10/hour)
  ✗ Financial identifiers accessed (account_number, PAN)
  
  Immediate options:
  [Suspend Session Now]  [View Full Log]  [Escalate to CISO]
```

IT head suspends session. Full session log preserved for forensic review. Evidence package generated automatically for potential disciplinary or legal action.

### Implementation Plan

**This agent is infrastructure, not an Action Registry entry.** It runs as a dedicated service that subscribes to the audit event stream.

**Architecture:**

```
All queries and agentic actions
        ↓ (every sensitive field access)
Audit Event Stream (append-only)
        ↓
Sensitive Field Access Monitor Service
  ├── Event ingestion and buffering
  ├── Pattern engines (5 pattern types, configurable thresholds)
  ├── Severity calculator
  ├── Alert router (low → log / medium → email / high → immediate / critical → optional suspend)
  └── Security panel data provider (IT admin dashboard)
```

**What needs to be built:**

1. Event subscriber: subscribes to audit event stream, filters for sensitive field access events
2. Session accumulator: maintains rolling event window per session and per user (Redis, TTL-based)
3. Pattern Engine 1 — Volume spike: count events per field category per time window, compare to threshold
4. Pattern Engine 2 — After-hours: compare access timestamp to user's 30-day rolling access baseline
5. Pattern Engine 3 — Bulk result: check result_row_count on each event against threshold
6. Pattern Engine 4 — Boundary probing: detect progressive field combination expansion across N queries
7. Pattern Engine 5 — Cross-context: compare data subject's context to user's normal access context
8. Severity calculator: combine pattern signals into severity score
9. Alert router: email/SMS for medium+, session flag for high+, optional auto-suspend for critical
10. Security panel API: serve accumulated alerts and session logs to IT admin dashboard
11. Evidence package generator: on IT head request, compile full session log + pattern analysis into exportable report
12. Threshold configuration UI in admin dashboard (all thresholds configurable by IT admin)

**Engineering estimate:** 8–10 days (most complex build — five pattern engines + real-time processing + security panel integration)

**Dependencies:** Audit event stream (prerequisite), Redis for session accumulation, Notification Service for alerts, IT admin dashboard (security panel)

**This agent is a prerequisite for the Payroll Query Agent and should be built before any agent that touches SENSITIVE-classified fields is deployed.**

---

## Implementation Sequencing

Build order across all 11 agents, based on dependencies and risk:

| Order | Agent | Reason |
|-------|-------|--------|
| 1st | Sensitive Field Access Monitor | Prerequisite for all agents touching sensitive data. Must be live before payroll or financial agents go to production. |
| 2nd | Leave Balance Agent (check mode only) | Simplest agent, read-only, low risk. Good first proof of concept for the Action Registry pipeline. |
| 3rd | Result Notification Agent | Event-based, read-only, high value for students. Tests the Trigger Engine. |
| 4th | Fee Reminder Agent | Scheduled trigger, read-only. Tests the scheduled Trigger Engine path. |
| 5th | Email Draft Agent (draft-only mode) | Read + draft, no send. User reviews before anything goes out. Low risk. |
| 6th | Leave Balance Agent (apply mode) | First write-lite agent. Small scope, clear rollback. |
| 7th | Meeting Scheduler Agent | Read + write to calendar. Tests calendar connector. |
| 8th | UPI Payment Agent | Read + external API call. No financial write — safe. |
| 9th | Bulk Notification Agent | Admin-only. Tests bulk dispatch infrastructure. |
| 10th | Email Draft and Send Agent (send mode enabled) | Full send capability. Enable only after draft-only mode is stable and SMTP is trusted. |
| 11th | Payroll Query Agent | Sensitive data. Monitor must be confirmed working first. |
| 12th | Leave Approval Agent | Multi-step workflow. Most complex. Build after all simpler agents are stable. |
| 13th | Refund Processing Agent | Financial workflow. Build last — highest consequence if something goes wrong. |

---

## Shared Infrastructure Required by All Agents

These components are not specific to any one agent but must be built before agents can go to production:

| Component | What it does | Required by |
|-----------|-------------|-------------|
| Action Registry | Stores and versions all agent configurations | All agents |
| Intent Classifier | Determines if a query is agentic or informational | All agents |
| Action Resolver | Maps intent to registered action | All agents |
| Eligibility Check | Validates persona permission for the action | All agents |
| Scope Guard | Enforces data access boundaries | All agents |
| Action Executor | Atomic execution with rollback | All write agents |
| Trigger Engine | Scheduled and event-based triggers | Result Notification, Fee Reminder |
| Notification Service | Email + in-app + SMS dispatch | All agents |
| Audit Event Stream | Immutable append-only event log | All agents |
| Sensitive Field Monitor | Pattern-based anomaly detection | Payroll, Refund, any sensitive field agent |

---

*ZTA-AI · Agentic Agents Reference · April 2026 · CONFIDENTIAL*
