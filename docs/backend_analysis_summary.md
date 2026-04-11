# Backend Analysis Summary

**Plan Alignment:** This analysis snapshot is aligned to `ZTA_AI_FINAL_PRODUCT_PRODUCTION_PLAN.md` (v3.0, April 11, 2026). For production expectations and phased outcomes, use the plan as authority. See `docs/PLAN_ALIGNMENT.md`.

## Base URL and Routing
- Base URL: `http://localhost:8000`
- Route groups:
  - `/health`
  - `/auth/*`
  - `/chat/*`
  - `/admin/*`

## Authentication Mechanism
- Auth type: JWT Bearer (`Authorization: Bearer <token>`)
- Login endpoints: `POST /auth/google` (development), `POST /auth/oidc` (production)
- MFA endpoints: `POST /auth/mfa/totp/enroll`, `POST /auth/mfa/totp/verify`
- Token refresh: `POST /auth/refresh`
- Logout/revocation: `POST /auth/logout`
- WebSocket auth: query token (`/chat/stream?token=<jwt>`)

## Middleware and Error Handling
- CORS middleware enabled for all origins/methods/headers.
- Custom exception handler for `ZTAError`.
- Global fallback exception handler returning `500 INTERNAL_ERROR`.
- Per-request auth dependency validates:
  - token signature/expiry
  - tenant active
  - user active
  - deny-list revocation
  - kill-switch revocation

## API Documentation

### GET /health
- Auth: none
- Request: none
- Response `200`:
```json
{ "status": "ok", "service": "ZTA-AI" }
```

### POST /auth/google
- Auth: none
- Body:
```json
{ "google_token": "mock:student@campusa.edu" }
```
- Response `200`:
```json
{
  "jwt": "<token>",
  "user": {
    "id": "...",
    "email": "student@campusa.edu",
    "name": "Asha Student",
    "persona": "student",
    "department": "CSE"
  }
}
```
- Errors: `401` (`GOOGLE_TOKEN_INVALID`, `UNKNOWN_TENANT`, `USER_NOT_FOUND`)

### POST /auth/refresh
- Auth: none (takes existing JWT in body)
- Body:
```json
{ "jwt": "<existing_token>" }
```
- Response `200`:
```json
{ "jwt": "<refreshed_token>" }
```
- Errors: `401` (`TOKEN_EXPIRED`, `TOKEN_REFRESH_TOO_EARLY`, `INVALID_TOKEN`)

### POST /auth/logout
- Auth: Bearer required
- Body: none
- Response `200`:
```json
{ "message": "Logged out successfully" }
```
- Errors: `401` (`TOKEN_REQUIRED`, `INVALID_TOKEN`)

### GET /chat/suggestions
- Auth: Bearer required
- Query/Body: none
- Response `200`:
```json
[
  { "id": "q1", "text": "What is my attendance percentage this semester?" }
]
```
- Errors: `401`, `403` (persona/domain restrictions)

### GET /chat/history
- Auth: Bearer required
- Query/Body: none
- Response `200`:
```json
[
  {
    "role": "assistant",
    "content": "Your attendance this semester is 78.4% across 6 subjects.",
    "created_at": "2026-03-27T..."
  }
]
```

### WS /chat/stream?token=<jwt>
- Auth: token query param
- Client message:
```json
{ "query": "What is my attendance percentage this semester?" }
```
- Stream frames:
```json
{ "type": "token", "content": "Your " }
```
```json
{ "type": "done", "source": "mock_claims", "latency_ms": 42 }
```
```json
{ "type": "error", "message": "..." }
```

### GET /admin/users
- Auth: Bearer required, IT Head only
- Query: `page`, `limit`, `search`, `persona`, `department`, `status`
- Response `200`:
```json
{
  "page": 1,
  "limit": 50,
  "items": [
    {
      "id": "...",
      "email": "student@campusa.edu",
      "name": "Asha Student",
      "persona_type": "student",
      "department": "CSE",
      "status": "active",
      "last_login": null
    }
  ]
}
```
- Errors: `403 ADMIN_ONLY`

### POST /admin/users/import
- Auth: Bearer required, IT Head only
- Body: multipart CSV file
- Response `200`:
```json
{ "imported": 3, "failed": 1, "errors": [{ "row": 5, "reason": "Invalid email" }] }
```

### PUT /admin/users/{user_id}
- Auth: Bearer required, IT Head only
- Body:
```json
{ "persona_type": "faculty", "department": "CSE", "status": "active" }
```
- Response `200` user snapshot

### GET /admin/data-sources
- Auth: Bearer required, IT Head only
- Response `200`: list of data sources

### POST /admin/data-sources
- Auth: Bearer required, IT Head only
- Body:
```json
{
  "name": "Finance DB",
  "source_type": "postgresql",
  "config": { "host": "db" },
  "department_scope": ["finance"]
}
```
- Response `200`: created source metadata

### GET /admin/data-sources/{source_id}/schema
- Auth: Bearer required, IT Head only
- Response `200`: aliased schema field metadata

### GET /admin/audit-log
- Auth: Bearer required, IT Head only
- Query: `page`, `limit`, `user_id`, `start_date`, `end_date`, `blocked_only`
- Response `200`: paged append-only audit events

### POST /admin/security/kill
- Auth: Bearer required, IT Head only
- Body:
```json
{ "scope": "all", "target_id": null }
```
- Scope values: `all | department | user`
- Response `200`: kill summary

## Core Data Models (SQLAlchemy)
- `tenants`: tenant identity and status
- `users`: persona, department/function scope, status, course/access context
- `data_sources`: connector config and lifecycle
- `schema_fields`: real schema -> alias mapping + visibility/PII controls
- `claims`: scoped claim-value store (domain/entity/owner/department/course/function)
- `intent_cache`: hashed normalized intent cache with TTL
- `audit_log`: append-only decision/response audit trail

## Relationships and Isolation
- `users.tenant_id -> tenants.id`
- `claims.tenant_id -> tenants.id`
- `audit_log.tenant_id -> tenants.id`
- Request processing always includes tenant filter + persona scope filters.

## Core Features and Data Flow
- Flow: Client -> Identity -> Interpreter -> Compiler -> Policy -> Tool Layer -> Data -> Compiler de-tokenization -> Response
- Interpreter: sanitize prompt, enforce domain gate, alias schema, extract intent, compute SHA-256 intent hash, read cache.
- Compiler: inject tenant + persona scope constraints and build parameterized query plan.
- Policy: RBAC + ABAC + domain checks + aggregate-only controls.
- Tool layer: executes connector plan with trusted scoped filters.
- SLM layer: template-only placeholder rendering (`[SLOT_n]`) with output guard checks.
- Audit: append-only logging for both success and blocked outcomes.

## Frontend Integration Contract
- Login obtains JWT via `/auth/google`.
- Frontend stores token and sends Bearer header for REST.
- Chat streaming uses `/chat/stream?token=<jwt>`.
- Admin UI requires IT Head token.

## Test Coverage
- Current tests validate:
  - student happy path
  - student cross-user block
  - IT Head chat block
  - intent cache model-skip behavior
  - output guard leak blocking
  - compiler faculty scope injection