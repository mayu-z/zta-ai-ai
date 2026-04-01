from __future__ import annotations

from app.db.models import (
    Claim,
    ClaimSensitivity,
    PersonaType,
    Tenant,
    TenantStatus,
    User,
    UserStatus,
)
from app.db.models import Base
from app.db.session import SessionLocal, engine
from scripts.ipeds_import import seed_ipeds_claims


CAMPUSEA_TENANT_ID = "11111111-1111-1111-1111-111111111111"


def _seed_campusa_baseline(db: SessionLocal) -> None:
    tenant = Tenant(
        id=CAMPUSEA_TENANT_ID,
        name="Campus A University",
        domain="campusa.edu",
        subdomain="campusa",
        status=TenantStatus.active,
    )
    db.add(tenant)
    db.flush()

    users = [
        User(
            tenant_id=CAMPUSEA_TENANT_ID,
            email="student@campusa.edu",
            name="Campus A Student",
            persona_type=PersonaType.student,
            department="CSE",
            external_id="STU-1001",
            status=UserStatus.active,
        ),
        User(
            tenant_id=CAMPUSEA_TENANT_ID,
            email="faculty@campusa.edu",
            name="Campus A Faculty",
            persona_type=PersonaType.faculty,
            department="CSE",
            external_id="FAC-2001",
            course_ids=["CSE101", "CSE102"],
            status=UserStatus.active,
        ),
        User(
            tenant_id=CAMPUSEA_TENANT_ID,
            email="it.head@campusa.edu",
            name="Campus A IT Head",
            persona_type=PersonaType.it_head,
            department="IT",
            external_id="IT-9001",
            status=UserStatus.active,
        ),
    ]
    db.add_all(users)
    db.flush()

    claims = [
        Claim(
            tenant_id=CAMPUSEA_TENANT_ID,
            domain="academic",
            entity_type="attendance_summary",
            entity_id="student-summary",
            owner_id="STU-1001",
            claim_key="attendance_percentage",
            value_number=78.4,
            sensitivity=ClaimSensitivity.internal,
            compliance_tags=["mock"],
        ),
        Claim(
            tenant_id=CAMPUSEA_TENANT_ID,
            domain="academic",
            entity_type="attendance_summary",
            entity_id="student-summary",
            owner_id="STU-1001",
            claim_key="subject_count",
            value_number=6,
            sensitivity=ClaimSensitivity.internal,
            compliance_tags=["mock"],
        ),
        Claim(
            tenant_id=CAMPUSEA_TENANT_ID,
            domain="academic",
            entity_type="grade_summary",
            entity_id="student-summary",
            owner_id="STU-1001",
            claim_key="gpa",
            value_number=8.1,
            sensitivity=ClaimSensitivity.internal,
            compliance_tags=["mock"],
        ),
        Claim(
            tenant_id=CAMPUSEA_TENANT_ID,
            domain="academic",
            entity_type="grade_summary",
            entity_id="student-summary",
            owner_id="STU-1001",
            claim_key="passed_subjects",
            value_number=5,
            sensitivity=ClaimSensitivity.internal,
            compliance_tags=["mock"],
        ),
    ]
    db.add_all(claims)


def seed() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        _seed_campusa_baseline(db)
        seeded = seed_ipeds_claims(db)
        db.commit()
        print(f"Seed completed with {seeded} CSV-backed IPEDS institutions")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
