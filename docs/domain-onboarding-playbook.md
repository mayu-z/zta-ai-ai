# Domain Onboarding Playbook

**Plan Alignment:** This playbook starts Phase 5 (Interpreter Maturity) from `ZTA_AI_FINAL_PRODUCT_PRODUCTION_PLAN.md` and focuses on domain-agnostic onboarding with policy-safe defaults.

## Purpose

Use this procedure to onboard a new domain (for example: legal, procurement, operations) without hardcoding application logic.

## Prerequisites

- Tenant is created and active.
- At least one active role policy exists for target personas.
- Connector/source binding strategy is defined for the domain.

## Step 1: Create Domain Keywords

Create `domain_keywords` entries for the tenant:

- `domain`: canonical domain name (for example `procurement`)
- `keywords`: business terms users naturally ask for
- `is_active`: true

Guidelines:

- Include both entity and action words (for example `purchase order`, `vendor`, `spend`, `renewal`).
- Avoid broad words such as `data`, `report`, and `summary`.

## Step 2: Create Intent Definitions

Create one or more `intent_definitions` rows per domain:

- `intent_name`: deterministic action name (for example `procurement_po_status`)
- `domain`: must match a configured domain
- `entity_type`: stable business entity (for example `purchase_order_summary`)
- `slot_keys`: deterministic output keys used by compiler/detokenizer
- `keywords`: intent-specific trigger terms
- `persona_types`: who may trigger this intent
- `is_default`: mark one safe fallback intent per domain/persona

Guidelines:

- Keep `slot_keys` stable and schema-safe.
- Use narrow, business-specific `keywords` before adding general terms.

## Step 3: Add Detection Keywords (Optional but Recommended)

Use `intent_detection_keywords` to bias intent selection where overlapping intent keywords exist.

Examples:

- `keyword_type=priority_marker` for urgent escalation words.
- `keyword_type=cost_marker` for finance-sensitive prompts.

## Step 4: Bind Data Sources

Create `domain_source_bindings`:

- Bind each domain to local-store or external source type.
- Ensure `data_source_id` is present for non-local source types.

## Step 5: Validate in Staging

Run validation before production rollout:

1. Domain detection:
   - Positive: domain-specific prompts map correctly.
   - Negative: unrelated prompts do not map to the new domain.
2. Intent extraction:
   - Required persona maps to expected intent.
   - Out-of-scope persona is blocked by policy.
3. Query execution:
   - Scoped rows only.
   - Masked fields remain masked.
4. Audit:
   - Query and policy decisions are logged with tenant context.

## Runtime Fallback Behavior

If tenant domain keyword config is temporarily missing, interpreter fallback derives domain hints from configured intent definitions.

Operational note:

- This fallback is a bootstrap safety net, not a substitute for explicit `domain_keywords` data.
- Keep explicit domain keyword configuration as source of truth.

## Rollback

If onboarding quality checks fail:

1. Deactivate newly added `intent_definitions`.
2. Deactivate new `domain_keywords` rows.
3. Revert `domain_source_bindings` to previous state.
4. Re-run smoke tests for existing domains.

## Exit Criteria

A domain onboarding is complete when:

- Domain detection is deterministic for top prompt patterns.
- At least one safe default intent exists per relevant persona.
- Source binding is active and policy-safe.
- Staging validation and audit verification pass.
