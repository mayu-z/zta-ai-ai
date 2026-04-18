# Testing Outcomes and Backlash Report

Date: 2026-04-18
Project: zta_agentic_service
Environment: Docker Compose + local Python 3.12.6 (system interpreter)

## Scope Covered (Rough Full E2E Sweep)
- Automated unit/integration tests (`pytest`)
- Container runtime and health
- Admin APIs (tenant-side)
- System APIs (global library/definition-side)
- Tenant version lifecycle (publish + rollback)
- Role/persona execution checks via `/execute`
- Negative access behavior checks

## Executive Summary
Core infrastructure and admin lifecycle flows are healthy.
Main remaining backlash is in intent-driven execution: `/execute` consistently falls back and fails to select a safe registered agent, even after agents are enabled and publish/rollback works.

## Results Matrix

### 1) Automated Tests
Status: PASS
- Initial run failed on missing dependency: `ModuleNotFoundError: No module named 'redis'`
- After installing `redis`, full suite passed:
  - 16 passed
  - 0 failed
  - 0 collection/import errors

### 2) Runtime and Platform Health
Status: PASS
- `docker compose ps` showed API, Postgres (healthy), Redis running
- `GET /health` returned HTTP 200 with `{"status":"ok"}`

### 3) System/Admin Library Endpoints
Status: PASS
- `GET /system/agents` returned HTTP 200
- `GET /admin/agents` returned HTTP 200
- Agent inventory returned successfully

### 4) Tenant Config and Version Inspection
Status: PASS
- `GET /admin/agents/leave_balance_v1/config?...` returned HTTP 200
- `GET /admin/agents/leave_balance_v1/versions?...` returned HTTP 200

### 5) Publish/Rollback Lifecycle (Real IDs, Not Placeholders)
Status: PASS
- Created/updated draft definition version for `leave_balance_v1`
- Created tenant config draft version
- `POST /admin/agents/{id}/publish` returned HTTP 200, status `published`
- `POST /admin/agents/{id}/rollback` returned HTTP 200, status `rolled_back`

### 6) Role/Persona Behavior via `/execute`
Status: PARTIAL / BLOCKED BY INTENT FALLBACK

Observed behavior:
- Multiple persona checks (`student`, `staff`, `admin`, `system`, etc.) returned HTTP 200 but business status:
  - `status: failed`
  - `state: FAILED`
  - `output_summary: I could not map this to a safe registered agent. Please rephrase.`
- Query-per-agent sweeps also returned all failed with same fallback message.

Interpretation:
- Endpoint is reachable and stable (no 5xx crash)
- Failure is logical/path-selection level, likely resolver/candidate-scoring path, not infra

### 7) Negative Access Check
Status: PASS
- Unsupported persona (`guest`) returned business failure with message indicating no enabled agents for that persona.
- This suggests role gating / zero-trust fail-closed behavior is active.

## Backlash / Blockers Identified

1. Intent resolver not selecting candidates in practical runtime calls
- Symptoms: all tested `/execute` calls fail with safe fallback message
- Blast radius: end-user execution path appears broken despite healthy platform
- Priority: HIGH

2. Public API does not expose a direct "execute by agent id" path
- Current public route relies on resolver selection first
- This makes per-agent E2E validation harder when resolver is failing
- Priority: MEDIUM

3. Agent role metadata visibility from `/system/agents` response is limited
- `allowed_personas` and role policy fields are not reliably surfaced in list response
- Slows diagnosis of persona filtering vs resolver scoring
- Priority: MEDIUM

## Likely Root Cause Zone
Most probable failure area is resolver/candidate selection integration in:
- `app/api/routes/execute.py`
- `app/services/intent_resolver.py`
- candidate payload quality from `registry.list_enabled_agents(...)`

## Recommended Next Fix Sequence

1. Add debug logging around resolver input/output in `/execute`
- Log candidate count, candidate ids, resolution decision, selected agent id

2. Add temporary direct execution route for diagnostics (admin/system protected)
- Example: `/execute/by-agent/{agent_id}`
- Bypasses resolver to validate handlers and role checks independently

3. Add integration tests for resolver + runtime registry candidate shapes
- Assert realistic queries map to expected agent ids
- Assert fallback only when truly ambiguous or unauthorized

4. Expose role metadata in `/system/agents` list (or add detailed endpoint)
- Include `allowed_personas` and effective policy fields explicitly

## Workspace Hygiene Findings (.venv and cache)

### Do you still need `.venv`?
Current state: no `.venv` folder detected.
- Not required for Docker runtime.
- Strongly recommended for local Python development/testing isolation.
- If you run local tools often, create one.

### Do you still need cache files?
Current state:
- `.pytest_cache`: not found
- `__pycache__` + `.pyc`: found (36 files)

Guidance:
- `__pycache__` and `.pyc` are disposable build/runtime artifacts.
- Safe to delete anytime.
- They will be regenerated automatically when Python runs.

## Optional Cleanup Commands
Run from `zta_agentic_service`:

```powershell
Get-ChildItem -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force
Get-ChildItem -Recurse -File -Filter *.pyc | Remove-Item -Force
```

## Final Status
- Infrastructure: PASS
- Admin/system APIs: PASS
- Publish/rollback lifecycle: PASS
- Security fail-closed behavior: PASS
- Intent-driven user execution: FAIL (current top blocker)
