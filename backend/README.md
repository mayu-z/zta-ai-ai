# ZTA-AI Backend (SLM-Strict, Zero Trust)

This backend implements the ZTA-AI security pipeline from the Engineering Specification:

Client -> Identity -> Interpreter -> Compiler -> Policy Engine -> Tool Layer -> Data Sources -> Compiler De-tokenization -> Response

The SLM layer generates dynamic templates via a hosted model (NVIDIA Phi-3) and outputs `[SLOT_N]` placeholders only. No hardcoded templates are used.

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

## 4. Initialize Schema + Seed Campus Mock Data

```bash
python scripts/seed_data.py
```

This performs a full reset (`drop_all/create_all`) and seeds a large, deterministic campus-university mock dataset across all domains (`academic`, `finance`, `hr`, `admissions`, `exam`, `department`, `campus`, `admin`, `notices`).

Seed profiles:

- `full` (default): high-volume data for end-to-end validation.
- `test`: lightweight dataset for fast test runs.

Use a profile explicitly:

```bash
ZTA_SEED_PROFILE=full python scripts/seed_data.py
```

## 5. Start API and Worker

Terminal 1:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Terminal 2:
```bash
celery -A app.tasks.celery_app.celery_app worker --loglevel=INFO
```

## 6. Mock Login

`POST /auth/google`

```json
{
  "google_token": "mock:executive@ipeds.local"
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

## 9. Default Seed Users

| User | Persona | Description |
|------|---------|-------------|
| `executive@ipeds.local` | Executive | Aggregate campus and cross-domain KPI views |
| `admissions@ipeds.local` | Admin Staff | Admissions office scoped summaries |
| `finance@ipeds.local` | Admin Staff | Finance office scoped summaries |
| `hr@ipeds.local` | Admin Staff | HR office scoped summaries|
| `exam@ipeds.local` | Admin Staff | Examination office scoped summaries |
| `ithead@ipeds.local` | IT Head | Admin-domain only (business chat blocked) |
| `faculty@ipeds.local` | Faculty | Course-scoped faculty data |
| `student@ipeds.local` | Student | Owner-scoped student data |

All use `mock:<email>` token format.

## 10. Tests

```bash
pytest -q tests -p no:cacheprovider
```
