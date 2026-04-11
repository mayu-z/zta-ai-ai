# ZTA-AI Incident Response Playbook

**Plan Alignment:** This runbook aligns to `ZTA_AI_FINAL_PRODUCT_PRODUCTION_PLAN.md` (v3.0, April 11, 2026), especially Phase 2 security hardening and Phase 7 compliance operations. See `docs/PLAN_ALIGNMENT.md`.

## Purpose

This playbook defines the operational response for security events in ZTA-AI environments. It is aligned with the production plan requirements for Phase 2 security hardening and Phase 7 compliance operations.

## Scope

- Cloud SaaS and customer on-prem deployments
- API, worker, connector, policy, identity, and audit components
- Security events including access abuse, exfiltration attempts, and credential compromise

## Severity Levels

| Severity | Description | Initial Response SLA | Executive Notification |
| --- | --- | --- | --- |
| SEV-1 | Active breach, confirmed data exfiltration, or policy bypass with sensitive impact | 15 minutes | Immediate |
| SEV-2 | Confirmed unauthorized attempt, contained connector compromise, or widespread auth failures | 30 minutes | Within 60 minutes |
| SEV-3 | Suspicious behavior, failed exploit attempts, localized service degradation | 60 minutes | Daily summary |

## Roles and Responsibilities

| Role | Responsibility |
| --- | --- |
| Incident Commander (IC) | Owns timeline, decisions, and incident closure |
| Security Lead | Threat triage, containment strategy, forensics direction |
| Platform Lead | Infrastructure/network controls, rollout/rollback, service recovery |
| Compliance Officer | Legal/regulatory assessment, disclosure decisions, evidence governance |
| Communications Lead | Customer/internal updates and approved messaging |

## Trigger Sources

- Policy denial spikes (RBAC/ABAC/FLS/RLS violations)
- Unusual audit patterns (mass access attempts, repeated blocked requests)
- mTLS or secret rotation failures
- Connector anomaly alerts (unexpected outbound patterns, auth failure bursts)
- Vulnerability scanner alerts for critical CVEs in production images

## Standard Response Workflow

1. Detect and declare
- Open incident channel and assign IC.
- Create incident ID in the format `INC-YYYYMMDD-###`.
- Classify severity and start incident clock.

2. Triage
- Confirm whether event is true positive.
- Determine impacted tenant(s), systems, and data classifications.
- Snapshot volatile evidence before containment changes.

3. Contain
- Apply least-disruptive controls first (token revocation, connector disable, namespace egress restriction).
- If needed, isolate impacted workloads at network layer.
- Preserve forensic chain of custody for all artifacts.

4. Eradicate
- Remove root cause (credential rotation, vulnerable image replacement, mispolicy rollback).
- Re-run validation checks for policy enforcement and auth boundaries.

5. Recover
- Restore controlled service access in stages.
- Monitor for recurrence for a minimum of 24 hours.
- Confirm SLO recovery and policy/audit integrity.

6. Close and improve
- Publish post-incident report within 5 business days.
- Track corrective actions with owners and due dates.
- Schedule tabletop if control gaps were identified.

## Evidence Collection Checklist

- Incident timeline with UTC timestamps
- Affected tenant IDs and user/session IDs
- Relevant policy decisions and denial records
- Audit log slices for impacted windows
- Service logs from API/worker/connectors
- Container image digests and deployed config snapshots
- Secret rotation and certificate events
- Network policy state before/after containment

## Operational Commands (Docker Compose)

```bash
# Collect API and worker logs for last 4 hours
docker compose logs api --since 4h > incident_api.log
docker compose logs worker --since 4h > incident_worker.log

# Capture running service and image state
docker compose ps > incident_services_state.txt

# Snapshot environment-specific config values for review
# (do not export secrets to chat/tickets)
docker compose exec api env | grep -E 'AUTH_PROVIDER|SECRETS_BACKEND|EGRESS_ALLOWED_HOSTS|SERVICE_MTLS_ENABLED' > incident_security_config.txt
```

## Operational Commands (Kubernetes)

```bash
# Snapshot deployment and policy state
kubectl get deploy,po,svc,networkpolicy -n zta-ai -o wide > incident_k8s_state.txt

# Collect recent application logs
kubectl logs deploy/zta-api -n zta-ai --since=4h > incident_api.log
kubectl logs deploy/zta-worker -n zta-ai --since=4h > incident_worker.log

# Quarantine example: restrict external egress by applying stricter policy set
kubectl apply -f deploy/k8s/security/network-policies.yaml
```

## Scenario Playbooks

### 1) Unauthorized Access Attempt (Blocked by Policy)

- Confirm event was blocked and no data was returned.
- Identify actor, role, tenant, and attempted resource.
- If repeated or scripted, disable account/session and escalate to SEV-2.
- File compliance note with evidence that controls worked.

### 2) Suspected Secret Leak

- Rotate impacted secret(s) immediately via configured backend.
- Invalidate application caches and restart affected workloads.
- Review access logs for use of leaked credential window.
- Require post-rotation validation for auth, OIDC, and SLM paths.

### 3) Suspected Connector Exfiltration Path

- Disable affected connector integration path.
- Restrict egress to approved CIDRs only.
- Export connector operation logs and API failure details.
- Re-enable only after root-cause remediation and test pass.

### 4) mTLS Certificate Compromise

- Revoke compromised cert and issue replacement.
- Re-issue trust bundle and client/server certs using `backend/scripts/generate_mtls_artifacts.sh`.
- Update trust bundles and restart clients.
- Confirm all service-to-service requests require valid client certs.
- Verify no successful requests occurred from untrusted cert after revocation.

## Communication Templates

### Internal Initial Update

`Incident INC-YYYYMMDD-### declared as SEV-X. We are investigating [summary]. Current impact: [impact]. Next update in [interval].`

### Customer Update (When Required)

`We detected and contained a security event affecting [scope]. Current status: [contained/investigating/recovered]. We will provide the next update by [time].`

## Post-Incident Report Template

- Incident ID and severity
- Executive summary
- Root cause
- Impacted systems/tenants/data classes
- Detection and response timeline
- Containment and recovery actions
- Compliance/regulatory outcomes
- Corrective actions with owner and due date

## Readiness Checks (Monthly)

- Verify on-call roster and escalation paths.
- Run one tabletop exercise for one high-severity scenario.
- Validate forensic export workflow and storage retention.
- Confirm network policy manifests still match deployed labels/selectors.
- Re-verify secret rotation runbook and mTLS cert replacement process.
