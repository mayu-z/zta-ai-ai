from __future__ import annotations

import os

from sqlalchemy import select, func

from app.db.models import Base, Tenant, IntentDefinition
from app.db.session import SessionLocal, engine
from scripts.ipeds_import import ensure_ipeds_runtime_config
from scripts.seed_data import seed


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _is_bootstrap_initialized(db) -> bool:
    """Check if bootstrap has already been run for existing tenants.

    Uses a proxy check: if IntentDefinition table has active records,
    bootstrap has already been initialized. This prevents re-seeding of
    runtime configuration on every container restart.
    """
    count = db.scalar(
        select(func.count(IntentDefinition.id)).where(
            IntentDefinition.is_active.is_(True)
        )
    )
    return (count or 0) > 0


def main() -> None:
    # Ensure a fresh database has the schema before checking seeded records.
    Base.metadata.create_all(bind=engine)

    selected_profile = os.getenv("ZTA_SEED_PROFILE", "full").strip().lower() or "full"
    force_reseed = _truthy(os.getenv("ZTA_FORCE_RESEED"))

    if force_reseed:
        print(f"Forced reseed enabled (profile={selected_profile})")
        seed(profile=selected_profile)
        print("Seed complete")
        return

    db = SessionLocal()
    try:
        has_tenant = db.scalar(select(Tenant.id).limit(1)) is not None
    finally:
        db.close()

    if has_tenant:
        db = SessionLocal()
        try:
            is_initialized = _is_bootstrap_initialized(db)
        finally:
            db.close()

        if is_initialized:
            print("Bootstrap already initialized for existing tenant; skipping re-seed")
            print("(To force re-seed, set ZTA_FORCE_RESEED=true)")
            return

        # Bootstrap needed: runtime config not yet populated
        db = SessionLocal()
        try:
            backfill = ensure_ipeds_runtime_config(db)
            db.commit()
        finally:
            db.close()

        print("Seed complete: runtime config bootstrapped for existing tenant")
        if any(backfill.values()):
            print(backfill)
        return

    print(
        "Seed required: no tenant data found, "
        f"initializing baseline records (profile={selected_profile})"
    )
    seed(profile=selected_profile)
    print("Seed complete")


if __name__ == "__main__":
    main()
