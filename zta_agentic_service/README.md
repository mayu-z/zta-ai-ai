# ZTA Agentic Service

Standalone FastAPI microservice for a dynamic, multi-tenant, zero-trust agent registry and execution runtime.

## Current implementation scope
- Project scaffold with explicit control-plane and data-plane boundaries
- Startup invariants and fail-closed checks
- SQLAlchemy data model foundation for registry lifecycle and execution tracking
- Deterministic intent resolver and execution state machine components
- API route skeletons for admin, system, and user execution workflows

## Quick start
1. Create and activate a virtual environment.
2. Install dependencies:
   - `pip install -e .[dev]`
3. Copy `.env.example` to `.env` and adjust values.
4. Run service:
   - `uvicorn app.main:app --reload`

## Notes
- This service is designed for PostgreSQL and Redis in production.
- No raw sensitive data should cross LLM boundaries.
- All runtime execution behavior must remain registry-driven.
