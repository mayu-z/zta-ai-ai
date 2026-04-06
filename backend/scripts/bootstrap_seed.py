from __future__ import annotations

import os

from sqlalchemy import select

from app.db.models import Base, Tenant
from app.db.session import SessionLocal, engine
from scripts.ipeds_import import ensure_ipeds_runtime_config
from scripts.seed_data import seed


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


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
            backfill = ensure_ipeds_runtime_config(db)
            db.commit()
        finally:
            db.close()

        if any(backfill.values()):
            print("Seed skipped: tenant data already exists; runtime config backfill applied")
            print(backfill)
        else:
            print("Seed skipped: tenant data and runtime config already exist")
        return

    print(
        "Seed required: no tenant data found, "
        f"initializing baseline records (profile={selected_profile})"
    )
    seed(profile=selected_profile)
    print("Seed complete")


if __name__ == "__main__":
    main()
