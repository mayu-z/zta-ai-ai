from __future__ import annotations

import base64
import csv
import json
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.db.models import (
    Claim,
    ClaimSensitivity,
    DataSource,
    DataSourceStatus,
    DataSourceType,
    PersonaType,
    Tenant,
    TenantStatus,
    User,
    UserStatus,
)


BASE_DIR = Path(__file__).resolve().parent.parent
CSV_PATHS = {
    "hd": BASE_DIR / "hd2024.csv",
    "ic": BASE_DIR / "ic2024.csv",
    "ef2024a": BASE_DIR / "ef2024a.csv",
    "efia2024": BASE_DIR / "efia2024.csv",
}

IPEDS_TENANT_ID = "33333333-3333-3333-3333-333333333333"


@dataclass(frozen=True)
class IpedInstitution:
    unitid: str
    name: str
    city: str
    state: str
    website: str
    open_admissions_flag: int
    total_enrollment: float
    total_fte: float
    graduate_mix_delta: float
    # New fields for expanded claims
    sector: int  # 1=Public 4yr, 2=Private nonprofit 4yr, etc.
    control: int  # 1=Public, 2=Private nonprofit, 3=Private for-profit
    hbcu: int  # 1=Yes, 2=No
    locale: int  # 11-13=City, 21-23=Suburb, 31-33=Town, 41-43=Rural
    inst_size: int  # 1=Under 1000, 2=1000-4999, 3=5000-9999, 4=10000-19999, 5=20000+
    degree_granting: int  # 1=Yes, 2=No


def _csv_exists() -> bool:
    return all(path.exists() for path in CSV_PATHS.values())


def _safe_float(value: str | None) -> float:
    if value is None:
        return 0.0

    cleaned = value.strip()
    if not cleaned or cleaned in {"A", "B", "G", "R", "-1", "-2"}:
        return 0.0

    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def _safe_int(value: str | None) -> int:
    return int(_safe_float(value))


def _load_rows_by_unitid(path: Path) -> dict[str, dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return {row["UNITID"]: row for row in reader if row.get("UNITID")}


def _load_fall_enrollment_rows(path: Path) -> dict[str, dict[str, str]]:
    preferred = [("1", "1"), ("99", "1"), ("29", "3"), ("14", "1")]
    ranked: dict[str, tuple[int, dict[str, str]]] = {}

    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            unitid = row.get("UNITID")
            if not unitid:
                continue

            signature = (row.get("LINE", ""), row.get("SECTION", ""))
            if signature not in preferred:
                continue

            rank = preferred.index(signature)
            current = ranked.get(unitid)
            if current is None or rank < current[0]:
                ranked[unitid] = (rank, row)

    return {unitid: row for unitid, (_rank, row) in ranked.items()}


def _build_institutions() -> list[IpedInstitution]:
    hd_rows = _load_rows_by_unitid(CSV_PATHS["hd"])
    ic_rows = _load_rows_by_unitid(CSV_PATHS["ic"])
    efia_rows = _load_rows_by_unitid(CSV_PATHS["efia2024"])
    ef_rows = _load_fall_enrollment_rows(CSV_PATHS["ef2024a"])

    institutions: list[IpedInstitution] = []
    for unitid in sorted(set(hd_rows) & set(ic_rows) & set(efia_rows) & set(ef_rows)):
        hd = hd_rows[unitid]
        ic = ic_rows[unitid]
        efia = efia_rows[unitid]
        ef = ef_rows[unitid]

        undergrad_fte = _safe_float(efia.get("EFTEUG"))
        graduate_fte = _safe_float(efia.get("EFTEGD")) + _safe_float(efia.get("FTEDPP"))
        total_fte = undergrad_fte + graduate_fte
        total_enrollment = _safe_float(ef.get("EFTOTLT"))
        if total_fte <= 0 or total_enrollment <= 0:
            continue

        graduate_mix_delta = round(((graduate_fte - undergrad_fte) / max(total_fte, 1.0)) * 100, 2)

        # Extract institution characteristics from hd2024
        sector = _safe_int(hd.get("SECTOR"))
        control = _safe_int(hd.get("CONTROL"))
        hbcu = _safe_int(hd.get("HBCU"))
        locale = _safe_int(hd.get("LOCALE"))
        inst_size = _safe_int(hd.get("INSTSIZE"))
        degree_granting = _safe_int(hd.get("DEGGRANT"))

        institutions.append(
            IpedInstitution(
                unitid=unitid,
                name=hd.get("INSTNM", f"Institution {unitid}").strip(),
                city=hd.get("CITY", "").strip(),
                state=hd.get("STABBR", "").strip(),
                website=hd.get("WEBADDR", "").strip(),
                open_admissions_flag=1 if ic.get("OPENADMP") == "1" else 0,
                total_enrollment=total_enrollment,
                total_fte=round(total_fte, 2),
                graduate_mix_delta=graduate_mix_delta,
                sector=sector,
                control=control,
                hbcu=hbcu,
                locale=locale,
                inst_size=inst_size,
                degree_granting=degree_granting,
            )
        )

    return institutions


def _seed_tenant(db: Session) -> None:
    tenant = Tenant(
        id=IPEDS_TENANT_ID,
        name="IPEDS CSV Claims Tenant",
        domain="ipeds.local",
        subdomain="ipeds",
        status=TenantStatus.active,
        google_workspace_domain=None,
    )
    db.add(tenant)


def _seed_users(db: Session) -> None:
    """Seed users required for authentication."""
    users = [
        User(
            tenant_id=IPEDS_TENANT_ID,
            email="executive@ipeds.local",
            name="IPEDS Executive",
            persona_type=PersonaType.executive,
            department="Executive Office",
            external_id="EXEC-001",
            status=UserStatus.active,
        ),
        User(
            tenant_id=IPEDS_TENANT_ID,
            email="admissions@ipeds.local",
            name="Admissions Staff",
            persona_type=PersonaType.admin_staff,
            admin_function="admissions",
            department="Admissions",
            external_id="ADM-001",
            status=UserStatus.active,
        ),
        User(
            tenant_id=IPEDS_TENANT_ID,
            email="ithead@ipeds.local",
            name="IT Head",
            persona_type=PersonaType.it_head,
            department="Information Technology",
            external_id="IT-001",
            status=UserStatus.active,
        ),
    ]
    db.add_all(users)
    print(f"Seeded {len(users)} users")


def _seed_data_sources(db: Session) -> None:
    """Seed default admin-visible data source records for IT Head workflows."""
    config = base64.b64encode(
        json.dumps(
            {
                "dataset": "ipeds_2024",
                "description": "Seeded IPEDS claims source for admin dashboard.",
            },
            ensure_ascii=True,
            sort_keys=True,
        ).encode("utf-8")
    ).decode("utf-8")
    row = DataSource(
        tenant_id=IPEDS_TENANT_ID,
        name="IPEDS Claims Source",
        source_type=DataSourceType.ipeds_claims,
        config_encrypted=config,
        department_scope=["campus", "admissions"],
        status=DataSourceStatus.connected,
    )
    db.add(row)
    print("Seeded 1 data source")


def _build_claims(institutions: list[IpedInstitution]) -> list[Claim]:
    claims: list[Claim] = []
    for institution in institutions:
        entity_id = f"ipeds-{institution.unitid}"
        provenance = f"ipeds:{institution.unitid}"

        claims.extend(
            [
                # Executive KPI claims
                Claim(
                    tenant_id=IPEDS_TENANT_ID,
                    domain="campus",
                    entity_type="executive_summary",
                    entity_id=entity_id,
                    claim_key="kpi_value",
                    value_number=institution.total_fte,
                    provenance=provenance,
                    sensitivity=ClaimSensitivity.internal,
                    compliance_tags=["IPEDS"],
                ),
                Claim(
                    tenant_id=IPEDS_TENANT_ID,
                    domain="campus",
                    entity_type="executive_summary",
                    entity_id=entity_id,
                    claim_key="trend_delta",
                    value_number=institution.graduate_mix_delta,
                    provenance=provenance,
                    sensitivity=ClaimSensitivity.internal,
                    compliance_tags=["IPEDS"],
                ),
                # Enrollment overview claims
                Claim(
                    tenant_id=IPEDS_TENANT_ID,
                    domain="campus",
                    entity_type="institution_enrollment_summary",
                    entity_id=entity_id,
                    claim_key="total_enrollment",
                    value_number=institution.total_enrollment,
                    provenance=provenance,
                    sensitivity=ClaimSensitivity.internal,
                    compliance_tags=["IPEDS"],
                ),
                Claim(
                    tenant_id=IPEDS_TENANT_ID,
                    domain="campus",
                    entity_type="institution_enrollment_summary",
                    entity_id=entity_id,
                    claim_key="institution_count",
                    value_number=1,
                    provenance=provenance,
                    sensitivity=ClaimSensitivity.internal,
                    compliance_tags=["IPEDS"],
                ),
                # Admissions claims
                Claim(
                    tenant_id=IPEDS_TENANT_ID,
                    domain="admissions",
                    entity_type="admin_function_summary",
                    entity_id=entity_id,
                    admin_function="admissions",
                    claim_key="function_metric",
                    value_number=100 if institution.open_admissions_flag else 0,
                    provenance=provenance,
                    sensitivity=ClaimSensitivity.internal,
                    compliance_tags=["IPEDS"],
                ),
                Claim(
                    tenant_id=IPEDS_TENANT_ID,
                    domain="admissions",
                    entity_type="admin_function_summary",
                    entity_id=entity_id,
                    admin_function="admissions",
                    claim_key="record_count",
                    value_number=1,
                    provenance=provenance,
                    sensitivity=ClaimSensitivity.internal,
                    compliance_tags=["IPEDS"],
                ),
                # Institution demographics claims (HBCU, public/private)
                Claim(
                    tenant_id=IPEDS_TENANT_ID,
                    domain="campus",
                    entity_type="institution_demographics",
                    entity_id=entity_id,
                    claim_key="hbcu_count",
                    value_number=1 if institution.hbcu == 1 else 0,
                    provenance=provenance,
                    sensitivity=ClaimSensitivity.low,
                    compliance_tags=["IPEDS"],
                ),
                Claim(
                    tenant_id=IPEDS_TENANT_ID,
                    domain="campus",
                    entity_type="institution_demographics",
                    entity_id=entity_id,
                    claim_key="public_count",
                    value_number=1 if institution.control == 1 else 0,
                    provenance=provenance,
                    sensitivity=ClaimSensitivity.low,
                    compliance_tags=["IPEDS"],
                ),
                Claim(
                    tenant_id=IPEDS_TENANT_ID,
                    domain="campus",
                    entity_type="institution_demographics",
                    entity_id=entity_id,
                    claim_key="private_count",
                    value_number=1 if institution.control in (2, 3) else 0,
                    provenance=provenance,
                    sensitivity=ClaimSensitivity.low,
                    compliance_tags=["IPEDS"],
                ),
                Claim(
                    tenant_id=IPEDS_TENANT_ID,
                    domain="campus",
                    entity_type="institution_demographics",
                    entity_id=entity_id,
                    claim_key="total_institutions",
                    value_number=1,
                    provenance=provenance,
                    sensitivity=ClaimSensitivity.low,
                    compliance_tags=["IPEDS"],
                ),
                # Institution size distribution claims
                Claim(
                    tenant_id=IPEDS_TENANT_ID,
                    domain="campus",
                    entity_type="institution_size_summary",
                    entity_id=entity_id,
                    claim_key="small_count",
                    value_number=1 if institution.inst_size in (1, 2) else 0,  # Under 5000
                    provenance=provenance,
                    sensitivity=ClaimSensitivity.low,
                    compliance_tags=["IPEDS"],
                ),
                Claim(
                    tenant_id=IPEDS_TENANT_ID,
                    domain="campus",
                    entity_type="institution_size_summary",
                    entity_id=entity_id,
                    claim_key="medium_count",
                    value_number=1 if institution.inst_size == 3 else 0,  # 5000-9999
                    provenance=provenance,
                    sensitivity=ClaimSensitivity.low,
                    compliance_tags=["IPEDS"],
                ),
                Claim(
                    tenant_id=IPEDS_TENANT_ID,
                    domain="campus",
                    entity_type="institution_size_summary",
                    entity_id=entity_id,
                    claim_key="large_count",
                    value_number=1 if institution.inst_size in (4, 5) else 0,  # 10000+
                    provenance=provenance,
                    sensitivity=ClaimSensitivity.low,
                    compliance_tags=["IPEDS"],
                ),
                Claim(
                    tenant_id=IPEDS_TENANT_ID,
                    domain="campus",
                    entity_type="institution_size_summary",
                    entity_id=entity_id,
                    claim_key="total_institutions",
                    value_number=1,
                    provenance=provenance,
                    sensitivity=ClaimSensitivity.low,
                    compliance_tags=["IPEDS"],
                ),
                # Institution profile (JSON catalog)
                Claim(
                    tenant_id=IPEDS_TENANT_ID,
                    domain="admin",
                    entity_type="institution_catalog",
                    entity_id=entity_id,
                    claim_key="profile",
                    value_json={
                        "unitid": institution.unitid,
                        "name": institution.name,
                        "city": institution.city,
                        "state": institution.state,
                        "website": institution.website,
                        "sector": institution.sector,
                        "control": "Public" if institution.control == 1 else "Private",
                        "hbcu": institution.hbcu == 1,
                        "size_category": institution.inst_size,
                    },
                    provenance=provenance,
                    sensitivity=ClaimSensitivity.low,
                    compliance_tags=["IPEDS"],
                ),
            ]
        )

    return claims


def seed_ipeds_claims(db: Session) -> int:
    if not _csv_exists():
        print("IPEDS seed skipped: one or more CSV files are missing")
        return 0

    institutions = _build_institutions()
    if not institutions:
        print("IPEDS seed skipped: no matching institution rows were found")
        return 0

    _seed_tenant(db)
    db.flush()
    _seed_users(db)
    db.flush()
    _seed_data_sources(db)
    db.flush()
    db.add_all(_build_claims(institutions))
    print(f"Seeded IPEDS CSV claims with {len(institutions)} institutions")
    return len(institutions)
