from __future__ import annotations

import os

from app.db.models import Base
from app.db.session import SessionLocal, engine
from scripts.ipeds_import import seed_ipeds_claims


def seed(profile: str | None = None) -> int:
    """Reset schema and seed deterministic campus-university mock data."""
    selected_profile = (profile or os.getenv("ZTA_SEED_PROFILE", "full")).strip().lower()
    if not selected_profile:
        selected_profile = "full"

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        seeded = seed_ipeds_claims(db, profile=selected_profile)
        db.commit()
        print(
            f"Seed completed with {seeded} claims "
            f"(profile={selected_profile}, tenant=ipeds.local)"
        )
        return seeded
    finally:
        db.close()


if __name__ == "__main__":
    seed()
