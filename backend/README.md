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

## 4. Initialize Schema + Seed IPEDS Data

```bash
python scripts/seed_data.py
```

This seeds 5,826 real institutions from IPEDS CSV data (87,390 claims).

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

## 9. IPEDS Users

| User | Persona | Description |
|------|---------|-------------|
| `executive@ipeds.local` | Executive | Aggregate institution data (enrollment, demographics) |
| `admissions@ipeds.local` | Admin Staff | Admissions statistics |
| `ithead@ipeds.local` | IT Head | Admin dashboard only (chat blocked) |

All use `mock:<email>` token format.

## 10. Tests

```bash
pytest -q tests -p no:cacheprovider
```
