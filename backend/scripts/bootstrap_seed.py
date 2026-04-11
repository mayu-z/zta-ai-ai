from __future__ import annotations

from sqlalchemy import select

from app.db.models import Tenant
from app.db.session import SessionLocal
from scripts.seed_data import seed


def main() -> None:
    db = SessionLocal()
    try:
        has_tenant = db.scalar(select(Tenant.id).limit(1)) is not None
    finally:
        db.close()

    if has_tenant:
        print("Seed skipped: tenant data already exists")
        return

    print("Seed required: no tenant data found, initializing baseline records")
    seed()
    print("Seed complete")


if __name__ == "__main__":
    main()