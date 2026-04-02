from __future__ import annotations

from app.db.models import Base
from app.db.session import SessionLocal, engine
from scripts.ipeds_import import seed_ipeds_claims


def seed() -> None:
    """Seed database with IPEDS institution data only."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        seeded = seed_ipeds_claims(db)
        db.commit()
        print(f"Seed completed with {seeded} IPEDS institutions")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
