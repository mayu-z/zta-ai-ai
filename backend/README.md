# ZTA-AI Backend (SLM-Strict, Zero Trust)

**Plan Alignment:** This backend guide is aligned to `ZTA_AI_FINAL_PRODUCT_PRODUCTION_PLAN.md` (v3.0, April 11, 2026). If this guide conflicts with the plan, use the plan. See `docs/PLAN_ALIGNMENT.md`.

This backend implements the ZTA-AI security pipeline from the Engineering Specification:

Client -> Identity -> Interpreter -> Compiler -> Policy Engine -> Tool Layer -> Data Sources -> Compiler De-tokenization -> Response

The SLM layer generates dynamic templates via a hosted OpenAI-compatible model and outputs `[SLOT_N]` placeholders only. No hardcoded templates are used.

By default, the hosted reasoning layer uses OpenAI-compatible APIs and applies control-plane knowledge graph context (role policy + domain/source lineage + masking metadata) when producing templates.

## 1. Prerequisites

- Python 3.11+
- PostgreSQL 15
- Redis 7

## 2. Setup

```bash
cd backend
python -m venv .venv
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

## 3. Start Infrastructure (optional via Docker)

```bash
docker compose up -d postgres redis
```

## 4. Initialize Schema (Seedless Default)

Schema tables are created automatically on API startup. Demo/data seeding is disabled in default local flow.

In development, first successful mock login auto-provisions:

- tenant for the email domain
- user identity for that email
- baseline role policies and interpreter defaults

## 5. Start API and Worker

Terminal 1:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Terminal 2:
```bash
celery -A app.tasks.celery_app.celery_app worker --loglevel=INFO
```

## 6. Authentication

Select provider mode with `AUTH_PROVIDER`:

- `mock_google` for local development/testing only
- `oidc` for production-compatible OIDC login
- `saml` reserved for SAML integration rollout

For local mock login (`AUTH_PROVIDER=mock_google` and `USE_MOCK_GOOGLE_OAUTH=true`):

`POST /auth/google`

```json
{
  "google_token": "mock:ithead@local.test"
}
```

Global system-admin mock login (separate from tenant users):

`POST /auth/system-admin/mock-login`

```json
{
  "admin_token": "mock_admin:sysadmin@zta.local"
}
```

Create tenant + bootstrap mock university users/data:

`POST /system-admin/tenants`

```json
{
  "tenant_name": "College One",
  "email_domain": "college1.com",
  "seed_mock_users": true,
  "seed_mock_claims": true
}
```

After a tenant is onboarded, any `*@college1.com` mock login can auto-provision user identity/role mapping on first sign-in.

For OIDC login (`AUTH_PROVIDER=oidc`):

`POST /auth/oidc`

```json
{
  "id_token": "<oidc-id-token>"
}
```

For TOTP MFA (after login):

1. Enroll TOTP secret:

`POST /auth/mfa/totp/enroll`

2. Verify current TOTP code and receive an MFA-verified JWT:

`POST /auth/mfa/totp/verify`

```json
{
  "code": "123456"
}
```

The returned JWT must be passed in:

- `Authorization: Bearer <jwt>` for REST endpoints.
- `ws://localhost:8000/chat/stream?token=<jwt>` for chat streaming.

## 7. Core Security Guarantees

- No model DB access, no tool calling, no memory.
- Model receives only abstract intent and returns slot templates.
- Compiler injects scope constraints and executes parameterized queries.
- Output guard blocks schema leakage and raw values from model output.
- Intent cache key is SHA-256(normalized_intent + tenant_id), TTL 24h.
- Audit log is append-only and records blocked/successful requests.
- Tenant isolation enforced in identity, query compiler, and claim retrieval.

## 8. Production Hardening

Run `scripts/postgres_hardening.sql` in production to enforce DB-level append-only triggers for `audit_log`.

Set `EGRESS_ALLOWED_HOSTS` in production so outbound calls are limited to approved domains (for example `integrate.api.nvidia.com`). Startup fails in production if this allowlist is missing or does not include the configured SLM host.

For OpenAI defaults, include `api.openai.com` in `EGRESS_ALLOWED_HOSTS` and set `OPENAI_API_KEY` (or `OPENAI_API_KEYS`).

Service-to-service mTLS is enforced in production startup checks. Configure:

- `SERVICE_MTLS_ENABLED=true`
- `SERVICE_MTLS_CLIENT_CERT_PATH=/path/to/client.crt`
- `SERVICE_MTLS_CLIENT_KEY_PATH=/path/to/client.key`
- `SERVICE_MTLS_CA_BUNDLE_PATH=/path/to/ca_bundle.crt`

To generate a local CA and issue client/server certificates automatically:

```bash
cd backend
./scripts/generate_mtls_artifacts.sh --out-dir ./certs/mtls/current --force
```

The script prints export-ready values for `SERVICE_MTLS_*` variables and creates:

- `ca.crt` / `ca_bundle.crt`
- `client.crt` + `client.key`
- `server.crt` + `server.key`

Startup fails in production if mTLS is disabled or certificate bundle paths are missing/invalid.

Kubernetes network policy templates for production are available at:

- `deploy/k8s/security/network-policies.yaml`
- `deploy/k8s/security/external-egress-policy.example.yaml`

Use these with the application-level egress allowlist (`EGRESS_ALLOWED_HOSTS`) for defense in depth.

Configure centralized secret retrieval with `SECRETS_BACKEND`:

- `env` (default) reads directly from environment variables.
- `file` reads a JSON secret file from `SECRETS_FILE_PATH`.
- `vault` reads KV v2 secrets from Vault (`VAULT_ADDR`, token, mount, prefix).
- `aws_secrets_manager` reads from AWS Secrets Manager (`AWS_SECRETS_MANAGER_REGION`, optional prefix).

JWT, OIDC shared secret, and SLM API keys are resolved through this secret manager. Non-env backends use short TTL caching (`SECRETS_CACHE_TTL_SECONDS`) so rotated secrets are picked up automatically.

Security incident response runbook:

- `docs/incident-response-playbook.md`

## 9. Development Login (No Seed Required)

In mock mode, login uses `mock:<email>` token format.

Examples:

- `mock:ithead@local.test` (auto-provisions IT Head style admin access)
- `mock:executive@local.test` (auto-provisions executive-style aggregate scope)
- `mock:faculty@local.test` or `mock:student@local.test` (persona inferred from email)

For tenant onboarding-first mode, keep `DEV_AUTO_CREATE_TENANT_ON_LOGIN=false` so unknown domains are rejected until created via `/system-admin/tenants`.

## 10. Tests

```bash
pytest -q tests -p no:cacheprovider
```

Phase 9 performance load gate (plan-aligned admin API normal/peak/burst/recovery plus interactive query-path normal/peak scenarios and baseline regression checks):

```bash
AUTH_PROVIDER=mock_google USE_MOCK_GOOGLE_OAUTH=true python scripts/performance_load_gate.py \
  --query-login-token mock:executive@local.test \
  --query-warmup-requests 10 \
  --regression-baseline-file scripts/performance_regression_baseline.json
```

To regenerate baseline metrics after approved performance improvements:

```bash
AUTH_PROVIDER=mock_google USE_MOCK_GOOGLE_OAUTH=true python scripts/performance_load_gate.py \
  --query-login-token mock:executive@local.test \
  --query-warmup-requests 10 \
  --skip-regression-check \
  --write-regression-baseline-file scripts/performance_regression_baseline.json
```

Phase 10 pilot validation gate (artifact preflight + evidence threshold checks):

```bash
python scripts/pilot_validation_gate.py
```

Evaluate with evidence payload and enforce performance fields:

```bash
python scripts/pilot_validation_gate.py \
  --pilot-evidence-file scripts/pilot_validation_evidence.template.json \
  --require-performance-metrics
```

Generate or refresh a pilot evidence template:

```bash
python scripts/pilot_validation_gate.py \
  --write-evidence-template-file scripts/pilot_validation_evidence.template.json
```
