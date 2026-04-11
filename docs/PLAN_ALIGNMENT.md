# Plan Alignment Reference (Authoritative)

This repository contains multiple legacy and domain-focused documents. As of April 11, 2026, the authoritative source of truth is:

- `ZTA_AI_FINAL_PRODUCT_PRODUCTION_PLAN.md` (Version 3.0)

If any document conflicts with the plan file, the plan file takes precedence.

## Canonical Alignment Rules

1. Product scope is domain-agnostic and compliance-first.
2. Authentication for production is OIDC/SAML with MFA; mock auth is development-only.
3. Security baseline includes mTLS, centralized secrets, egress allowlisting, network policies, and incident response operations.
4. SLM/LLM runtime is sandboxed and non-authoritative, with zero-learning guarantees enforced at runtime and operations layers.
5. Performance program target is `<1000ms P95` at launch hardening milestones; prior lower-latency claims are non-authoritative unless validated by benchmark evidence.
6. Deployment supports both cloud SaaS and on-prem with policy parity.
7. Operational readiness requires runbooks, observability, forensic exportability, and compliance evidence workflows.

## Implemented Security Artifacts in This Repository

- Network policies: `deploy/k8s/security/network-policies.yaml`
- External egress template: `deploy/k8s/security/external-egress-policy.example.yaml`
- mTLS certificate issuance automation: `backend/scripts/generate_mtls_artifacts.sh`
- Incident response playbook: `docs/incident-response-playbook.md`

## Usage for Contributors

When updating any architecture, security, integration, or market document:

- Preserve document-specific audience and examples.
- Keep technical and business claims aligned to the production plan.
- Add explicit caveats where a document is legacy, illustrative, or narrower than plan scope.
