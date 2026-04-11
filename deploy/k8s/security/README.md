# Kubernetes Security Policies

This directory contains baseline Kubernetes network policy manifests for Phase 2 security hardening.

## Files

- `network-policies.yaml`: Default deny + explicit internal traffic allowances (API, worker, Postgres, Redis, DNS, ingress-controller).
- `external-egress-policy.example.yaml`: Template for explicit outbound HTTPS CIDR allowlists.

## Pre-Flight Checks

1. Confirm namespace exists (`zta-ai` by default).
2. Confirm pod labels match selectors used in policy manifests.
3. Resolve approved external domains to CIDR ranges for your cluster network policy implementation.
4. Ensure app-level egress allowlist (`EGRESS_ALLOWED_HOSTS`) matches intended outbound destinations.

## Apply

```bash
kubectl apply -f deploy/k8s/security/network-policies.yaml
# Update CIDRs first, then apply:
kubectl apply -f deploy/k8s/security/external-egress-policy.example.yaml
```

## Verify

```bash
kubectl get networkpolicy -n zta-ai
kubectl describe networkpolicy default-deny-ingress-egress -n zta-ai
```

## Rollback

```bash
kubectl delete -f deploy/k8s/security/external-egress-policy.example.yaml
kubectl delete -f deploy/k8s/security/network-policies.yaml
```
