from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime, timedelta
from typing import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.db.models import (
    Claim,
    ClaimSensitivity,
    PersonaType,
    PlanTier,
    Tenant,
    TenantStatus,
    User,
    UserStatus,
)
from app.identity.service import ALL_DOMAINS, identity_service
from app.schemas.system_admin import SystemAdminTenantCreateRequest
from app.services.control_plane_graph_service import control_plane_graph_service


_DOMAIN_REGEX = re.compile(r"^[a-z0-9][a-z0-9.-]*\.[a-z]{2,}$")


class TenantOnboardingService:
    def _normalize_domain(self, raw: str) -> str:
        value = raw.strip().lower()
        if value.startswith("@"):
            value = value[1:]
        if "@" in value:
            value = value.split("@", 1)[1]
        value = value.strip(".")
        if not _DOMAIN_REGEX.fullmatch(value):
            raise ValidationError(
                message="email_domain must be a valid domain like college1.com",
                code="TENANT_DOMAIN_INVALID",
            )
        return value

    def _slugify(self, value: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
        slug = re.sub(r"-+", "-", slug).strip("-")
        return slug[:90] or "tenant"

    def _next_available_subdomain(self, db: Session, base: str) -> str:
        candidate = base
        suffix = 2
        while db.scalar(select(Tenant.id).where(Tenant.subdomain == candidate)):
            suffix_text = f"-{suffix}"
            candidate = f"{base[: 90 - len(suffix_text)]}{suffix_text}"
            suffix += 1
        return candidate

    def _coerce_plan_tier(self, raw: str) -> PlanTier:
        normalized = raw.strip().lower()
        try:
            return PlanTier(normalized)
        except ValueError as exc:
            raise ValidationError(
                message="plan_tier must be one of starter, growth, enterprise",
                code="TENANT_PLAN_TIER_INVALID",
            ) from exc

    def _derive_external_id(self, email: str, prefix: str) -> str:
        digest = hashlib.sha256(email.encode("utf-8")).hexdigest()[:8].upper()
        return f"{prefix}-{digest}"

    def _create_user(
        self,
        *,
        tenant_id: str,
        email: str,
        name: str,
        persona: PersonaType,
        department: str | None = None,
        admin_function: str | None = None,
        course_ids: list[str] | None = None,
        external_prefix: str,
    ) -> User:
        return User(
            tenant_id=tenant_id,
            email=email,
            name=name,
            persona_type=persona,
            department=department,
            external_id=self._derive_external_id(email, external_prefix),
            admin_function=admin_function,
            course_ids=list(course_ids or []),
            masked_fields=[],
            status=UserStatus.active,
        )

    def _build_mock_users(self, tenant_id: str, domain: str) -> list[User]:
        users: list[User] = []

        users.append(
            self._create_user(
                tenant_id=tenant_id,
                email=f"tenant.admin@{domain}",
                name="Tenant Admin",
                persona=PersonaType.it_head,
                external_prefix="ADM",
            )
        )
        users.append(
            self._create_user(
                tenant_id=tenant_id,
                email=f"dean@{domain}",
                name="Dean",
                persona=PersonaType.executive,
                external_prefix="EXE",
            )
        )
        users.append(
            self._create_user(
                tenant_id=tenant_id,
                email=f"hod.cse@{domain}",
                name="CSE Department Head",
                persona=PersonaType.dept_head,
                department="cse",
                external_prefix="HOD",
            )
        )

        users.append(
            self._create_user(
                tenant_id=tenant_id,
                email=f"admissions@{domain}",
                name="Admissions Office",
                persona=PersonaType.admin_staff,
                admin_function="admissions",
                external_prefix="ADM",
            )
        )
        users.append(
            self._create_user(
                tenant_id=tenant_id,
                email=f"finance@{domain}",
                name="Finance Office",
                persona=PersonaType.admin_staff,
                admin_function="finance",
                external_prefix="FIN",
            )
        )
        users.append(
            self._create_user(
                tenant_id=tenant_id,
                email=f"hr@{domain}",
                name="HR Office",
                persona=PersonaType.admin_staff,
                admin_function="hr",
                external_prefix="HR",
            )
        )
        users.append(
            self._create_user(
                tenant_id=tenant_id,
                email=f"exam@{domain}",
                name="Exam Office",
                persona=PersonaType.admin_staff,
                admin_function="exam",
                external_prefix="EXM",
            )
        )

        for idx in range(1, 6):
            users.append(
                self._create_user(
                    tenant_id=tenant_id,
                    email=f"faculty{idx}@{domain}",
                    name=f"Faculty {idx}",
                    persona=PersonaType.faculty,
                    department="cse",
                    course_ids=[f"CSE10{idx}", f"CSE20{idx}"],
                    external_prefix="FAC",
                )
            )

        for idx in range(1, 11):
            users.append(
                self._create_user(
                    tenant_id=tenant_id,
                    email=f"student{idx}@{domain}",
                    name=f"Student {idx}",
                    persona=PersonaType.student,
                    external_prefix="STU",
                )
            )

        return users

    def _claim(
        self,
        *,
        tenant_id: str,
        domain: str,
        entity_type: str,
        entity_id: str,
        claim_key: str,
        value_text: str | None = None,
        value_number: float | None = None,
        value_json: dict[str, object] | None = None,
        owner_id: str | None = None,
        department_id: str | None = None,
        course_id: str | None = None,
        admin_function: str | None = None,
        sensitivity: ClaimSensitivity = ClaimSensitivity.internal,
    ) -> Claim:
        return Claim(
            tenant_id=tenant_id,
            domain=domain,
            entity_type=entity_type,
            entity_id=entity_id,
            owner_id=owner_id,
            department_id=department_id,
            course_id=course_id,
            admin_function=admin_function,
            claim_key=claim_key,
            value_text=value_text,
            value_number=value_number,
            value_json=value_json,
            provenance="mock-tenant-onboarding",
            sensitivity=sensitivity,
            compliance_tags=[],
        )

    def _build_overview_claims(self, tenant_id: str) -> list[Claim]:
        claims: list[Claim] = []

        profile_payload = {
            "institution_id": "inst-college-one",
            "name": "College One",
            "state": "CA",
            "control": "Private",
            "website": "https://college1.com",
            "enrollment_band": "small",
        }

        claims.extend(
            [
                self._claim(
                    tenant_id=tenant_id,
                    domain="campus",
                    entity_type="executive_summary",
                    entity_id="campus-overview",
                    claim_key="kpi_value",
                    value_number=87.4,
                ),
                self._claim(
                    tenant_id=tenant_id,
                    domain="campus",
                    entity_type="executive_summary",
                    entity_id="campus-overview",
                    claim_key="trend_delta",
                    value_number=2.1,
                ),
                self._claim(
                    tenant_id=tenant_id,
                    domain="campus",
                    entity_type="institution_enrollment_summary",
                    entity_id="campus-overview",
                    claim_key="total_enrollment",
                    value_number=4520,
                ),
                self._claim(
                    tenant_id=tenant_id,
                    domain="campus",
                    entity_type="institution_enrollment_summary",
                    entity_id="campus-overview",
                    claim_key="institution_count",
                    value_number=1,
                ),
                self._claim(
                    tenant_id=tenant_id,
                    domain="campus",
                    entity_type="institution_demographics",
                    entity_id="campus-overview",
                    claim_key="hbcu_count",
                    value_number=0,
                ),
                self._claim(
                    tenant_id=tenant_id,
                    domain="campus",
                    entity_type="institution_demographics",
                    entity_id="campus-overview",
                    claim_key="public_count",
                    value_number=0,
                ),
                self._claim(
                    tenant_id=tenant_id,
                    domain="campus",
                    entity_type="institution_demographics",
                    entity_id="campus-overview",
                    claim_key="private_count",
                    value_number=1,
                ),
                self._claim(
                    tenant_id=tenant_id,
                    domain="campus",
                    entity_type="institution_demographics",
                    entity_id="campus-overview",
                    claim_key="total_institutions",
                    value_number=1,
                ),
                self._claim(
                    tenant_id=tenant_id,
                    domain="campus",
                    entity_type="institution_size_summary",
                    entity_id="campus-overview",
                    claim_key="small_count",
                    value_number=1,
                ),
                self._claim(
                    tenant_id=tenant_id,
                    domain="campus",
                    entity_type="institution_size_summary",
                    entity_id="campus-overview",
                    claim_key="medium_count",
                    value_number=0,
                ),
                self._claim(
                    tenant_id=tenant_id,
                    domain="campus",
                    entity_type="institution_size_summary",
                    entity_id="campus-overview",
                    claim_key="large_count",
                    value_number=0,
                ),
                self._claim(
                    tenant_id=tenant_id,
                    domain="campus",
                    entity_type="institution_size_summary",
                    entity_id="campus-overview",
                    claim_key="total_institutions",
                    value_number=1,
                ),
                self._claim(
                    tenant_id=tenant_id,
                    domain="academic",
                    entity_type="executive_academic_summary",
                    entity_id="academic-overview",
                    claim_key="total_passed_students",
                    value_number=3980,
                ),
                self._claim(
                    tenant_id=tenant_id,
                    domain="academic",
                    entity_type="executive_academic_summary",
                    entity_id="academic-overview",
                    claim_key="total_course_registrations",
                    value_number=5120,
                ),
                self._claim(
                    tenant_id=tenant_id,
                    domain="finance",
                    entity_type="executive_finance_summary",
                    entity_id="finance-overview",
                    claim_key="tuition_collected",
                    value_number=28450000.0,
                    sensitivity=ClaimSensitivity.confidential,
                ),
                self._claim(
                    tenant_id=tenant_id,
                    domain="finance",
                    entity_type="executive_finance_summary",
                    entity_id="finance-overview",
                    claim_key="outstanding_dues",
                    value_number=1285000.0,
                    sensitivity=ClaimSensitivity.confidential,
                ),
                self._claim(
                    tenant_id=tenant_id,
                    domain="hr",
                    entity_type="executive_hr_summary",
                    entity_id="hr-overview",
                    claim_key="headcount",
                    value_number=620,
                    sensitivity=ClaimSensitivity.confidential,
                ),
                self._claim(
                    tenant_id=tenant_id,
                    domain="hr",
                    entity_type="executive_hr_summary",
                    entity_id="hr-overview",
                    claim_key="attrition_events",
                    value_number=26,
                    sensitivity=ClaimSensitivity.confidential,
                ),
                self._claim(
                    tenant_id=tenant_id,
                    domain="admissions",
                    entity_type="executive_admissions_summary",
                    entity_id="admissions-overview",
                    claim_key="total_applications",
                    value_number=6100,
                ),
                self._claim(
                    tenant_id=tenant_id,
                    domain="admissions",
                    entity_type="executive_admissions_summary",
                    entity_id="admissions-overview",
                    claim_key="admitted_count",
                    value_number=2480,
                ),
                self._claim(
                    tenant_id=tenant_id,
                    domain="exam",
                    entity_type="executive_exam_summary",
                    entity_id="exam-overview",
                    claim_key="total_exams",
                    value_number=3850,
                ),
                self._claim(
                    tenant_id=tenant_id,
                    domain="exam",
                    entity_type="executive_exam_summary",
                    entity_id="exam-overview",
                    claim_key="passed_exams",
                    value_number=3325,
                ),
                self._claim(
                    tenant_id=tenant_id,
                    domain="department",
                    entity_type="executive_department_summary",
                    entity_id="department-overview",
                    claim_key="department_metric",
                    value_number=82.5,
                ),
                self._claim(
                    tenant_id=tenant_id,
                    domain="department",
                    entity_type="executive_department_summary",
                    entity_id="department-overview",
                    claim_key="student_count",
                    value_number=4520,
                ),
                self._claim(
                    tenant_id=tenant_id,
                    domain="admin",
                    entity_type="security_summary",
                    entity_id="security-overview",
                    claim_key="unresolved_incidents",
                    value_number=3,
                    sensitivity=ClaimSensitivity.restricted,
                ),
                self._claim(
                    tenant_id=tenant_id,
                    domain="admin",
                    entity_type="security_summary",
                    entity_id="security-overview",
                    claim_key="critical_alerts",
                    value_number=1,
                    sensitivity=ClaimSensitivity.restricted,
                ),
                self._claim(
                    tenant_id=tenant_id,
                    domain="admin",
                    entity_type="institution_catalog",
                    entity_id="institution-profile",
                    claim_key="profile",
                    value_json=profile_payload,
                ),
                self._claim(
                    tenant_id=tenant_id,
                    domain="notices",
                    entity_type="notices_summary",
                    entity_id="notices-overview",
                    claim_key="notices_count",
                    value_number=36,
                    sensitivity=ClaimSensitivity.low,
                ),
                self._claim(
                    tenant_id=tenant_id,
                    domain="notices",
                    entity_type="notices_summary",
                    entity_id="notices-overview",
                    claim_key="critical_notices",
                    value_number=2,
                    sensitivity=ClaimSensitivity.low,
                ),
            ]
        )

        return claims

    def _build_scoped_claims(self, tenant_id: str, users: Iterable[User]) -> list[Claim]:
        claims: list[Claim] = []
        today = datetime.now(tz=UTC).date()

        students = [u for u in users if u.persona_type == PersonaType.student]
        faculties = [u for u in users if u.persona_type == PersonaType.faculty]
        dept_heads = [u for u in users if u.persona_type == PersonaType.dept_head]
        admin_staff = [u for u in users if u.persona_type == PersonaType.admin_staff]

        for idx, student in enumerate(students, start=1):
            attendance = 82.0 + float((idx % 11))
            subject_count = 5 + (idx % 4)
            gpa = round(2.3 + (idx % 14) * 0.11, 2)
            passed_subjects = max(3, subject_count - 1)
            fee_balance = float(3500 - (idx % 6) * 420)
            if fee_balance < 0:
                fee_balance = 0.0
            due_date = (today + timedelta(days=5 + (idx % 21))).isoformat()

            claims.append(
                self._claim(
                    tenant_id=tenant_id,
                    domain="academic",
                    entity_type="attendance_summary",
                    entity_id=f"student-{idx:03d}",
                    claim_key="attendance_percentage",
                    value_number=attendance,
                    owner_id=student.external_id,
                )
            )
            claims.append(
                self._claim(
                    tenant_id=tenant_id,
                    domain="academic",
                    entity_type="attendance_summary",
                    entity_id=f"student-{idx:03d}",
                    claim_key="subject_count",
                    value_number=float(subject_count),
                    owner_id=student.external_id,
                )
            )
            claims.append(
                self._claim(
                    tenant_id=tenant_id,
                    domain="academic",
                    entity_type="grade_summary",
                    entity_id=f"student-{idx:03d}",
                    claim_key="gpa",
                    value_number=gpa,
                    owner_id=student.external_id,
                )
            )
            claims.append(
                self._claim(
                    tenant_id=tenant_id,
                    domain="academic",
                    entity_type="grade_summary",
                    entity_id=f"student-{idx:03d}",
                    claim_key="passed_subjects",
                    value_number=float(passed_subjects),
                    owner_id=student.external_id,
                )
            )
            claims.append(
                self._claim(
                    tenant_id=tenant_id,
                    domain="finance",
                    entity_type="fee_summary",
                    entity_id=f"student-{idx:03d}",
                    claim_key="fee_balance",
                    value_number=fee_balance,
                    owner_id=student.external_id,
                    sensitivity=ClaimSensitivity.confidential,
                )
            )
            claims.append(
                self._claim(
                    tenant_id=tenant_id,
                    domain="finance",
                    entity_type="fee_summary",
                    entity_id=f"student-{idx:03d}",
                    claim_key="due_date",
                    value_text=due_date,
                    owner_id=student.external_id,
                    sensitivity=ClaimSensitivity.confidential,
                )
            )
            claims.append(
                self._claim(
                    tenant_id=tenant_id,
                    domain="notices",
                    entity_type="notices_summary",
                    entity_id=f"student-{idx:03d}",
                    claim_key="notices_count",
                    value_number=float(3 + (idx % 6)),
                    owner_id=student.external_id,
                    sensitivity=ClaimSensitivity.low,
                )
            )
            claims.append(
                self._claim(
                    tenant_id=tenant_id,
                    domain="notices",
                    entity_type="notices_summary",
                    entity_id=f"student-{idx:03d}",
                    claim_key="critical_notices",
                    value_number=float(idx % 2),
                    owner_id=student.external_id,
                    sensitivity=ClaimSensitivity.low,
                )
            )

        for idx, faculty in enumerate(faculties, start=1):
            primary_course = (faculty.course_ids or [f"CSE30{idx}"])[0]
            course_count = float(max(1, len(faculty.course_ids or [])))
            avg_attendance = round(74.0 + (idx % 18) * 1.1, 2)

            claims.append(
                self._claim(
                    tenant_id=tenant_id,
                    domain="academic",
                    entity_type="faculty_course_summary",
                    entity_id=f"faculty-{idx:03d}",
                    claim_key="course_count",
                    value_number=course_count,
                    owner_id=faculty.external_id,
                    department_id=faculty.department,
                    course_id=primary_course,
                )
            )
            claims.append(
                self._claim(
                    tenant_id=tenant_id,
                    domain="academic",
                    entity_type="faculty_course_summary",
                    entity_id=f"faculty-{idx:03d}",
                    claim_key="avg_attendance",
                    value_number=avg_attendance,
                    owner_id=faculty.external_id,
                    department_id=faculty.department,
                    course_id=primary_course,
                )
            )
            claims.append(
                self._claim(
                    tenant_id=tenant_id,
                    domain="hr",
                    entity_type="faculty_hr_summary",
                    entity_id=f"faculty-{idx:03d}",
                    claim_key="leave_balance",
                    value_number=float(12 + (idx % 8)),
                    owner_id=faculty.external_id,
                    department_id=faculty.department,
                    course_id=primary_course,
                    sensitivity=ClaimSensitivity.confidential,
                )
            )
            claims.append(
                self._claim(
                    tenant_id=tenant_id,
                    domain="hr",
                    entity_type="faculty_hr_summary",
                    entity_id=f"faculty-{idx:03d}",
                    claim_key="pending_requests",
                    value_number=float(idx % 3),
                    owner_id=faculty.external_id,
                    department_id=faculty.department,
                    course_id=primary_course,
                    sensitivity=ClaimSensitivity.confidential,
                )
            )
            claims.append(
                self._claim(
                    tenant_id=tenant_id,
                    domain="notices",
                    entity_type="notices_summary",
                    entity_id=f"faculty-{idx:03d}",
                    claim_key="notices_count",
                    value_number=float(2 + (idx % 5)),
                    owner_id=faculty.external_id,
                    department_id=faculty.department,
                    course_id=primary_course,
                    sensitivity=ClaimSensitivity.low,
                )
            )
            claims.append(
                self._claim(
                    tenant_id=tenant_id,
                    domain="notices",
                    entity_type="notices_summary",
                    entity_id=f"faculty-{idx:03d}",
                    claim_key="critical_notices",
                    value_number=float(idx % 2),
                    owner_id=faculty.external_id,
                    department_id=faculty.department,
                    course_id=primary_course,
                    sensitivity=ClaimSensitivity.low,
                )
            )

        for idx, head in enumerate(dept_heads, start=1):
            department_id = (head.department or "cse").lower()
            claims.append(
                self._claim(
                    tenant_id=tenant_id,
                    domain="department",
                    entity_type="department_summary",
                    entity_id=f"department-{department_id}",
                    claim_key="department_metric",
                    value_number=78.5 + idx,
                    department_id=department_id,
                )
            )
            claims.append(
                self._claim(
                    tenant_id=tenant_id,
                    domain="department",
                    entity_type="department_summary",
                    entity_id=f"department-{department_id}",
                    claim_key="student_count",
                    value_number=float(420 + idx * 35),
                    department_id=department_id,
                )
            )
            claims.append(
                self._claim(
                    tenant_id=tenant_id,
                    domain="exam",
                    entity_type="department_exam_summary",
                    entity_id=f"department-exam-{department_id}",
                    claim_key="exam_backlog",
                    value_number=float(4 + idx),
                    department_id=department_id,
                )
            )
            claims.append(
                self._claim(
                    tenant_id=tenant_id,
                    domain="exam",
                    entity_type="department_exam_summary",
                    entity_id=f"department-exam-{department_id}",
                    claim_key="pass_rate",
                    value_number=83.0 + idx,
                    department_id=department_id,
                )
            )
            claims.append(
                self._claim(
                    tenant_id=tenant_id,
                    domain="notices",
                    entity_type="notices_summary",
                    entity_id=f"department-notice-{department_id}",
                    claim_key="notices_count",
                    value_number=float(6 + idx),
                    department_id=department_id,
                    sensitivity=ClaimSensitivity.low,
                )
            )
            claims.append(
                self._claim(
                    tenant_id=tenant_id,
                    domain="notices",
                    entity_type="notices_summary",
                    entity_id=f"department-notice-{department_id}",
                    claim_key="critical_notices",
                    value_number=float(idx % 2),
                    department_id=department_id,
                    sensitivity=ClaimSensitivity.low,
                )
            )

        for idx, staff in enumerate(admin_staff, start=1):
            function = (staff.admin_function or "admin").lower()
            domain = function if function in ALL_DOMAINS else "admin"

            if function == "admissions":
                function_metric = float(1200 + idx * 75)
                record_count = float(280 + idx * 14)
            elif function == "finance":
                function_metric = float(850000 + idx * 32000)
                record_count = float(190 + idx * 11)
            elif function == "hr":
                function_metric = float(18 + idx)
                record_count = float(35 + idx * 4)
            elif function == "exam":
                function_metric = float(88 + idx)
                record_count = float(210 + idx * 17)
            else:
                function_metric = float(70 + idx)
                record_count = float(100 + idx * 8)

            claims.append(
                self._claim(
                    tenant_id=tenant_id,
                    domain=domain,
                    entity_type="admin_function_summary",
                    entity_id=f"{function}-ops",
                    claim_key="function_metric",
                    value_number=function_metric,
                    admin_function=function,
                    sensitivity=(
                        ClaimSensitivity.confidential
                        if function in {"finance", "hr"}
                        else ClaimSensitivity.internal
                    ),
                )
            )
            claims.append(
                self._claim(
                    tenant_id=tenant_id,
                    domain=domain,
                    entity_type="admin_function_summary",
                    entity_id=f"{function}-ops",
                    claim_key="record_count",
                    value_number=record_count,
                    admin_function=function,
                    sensitivity=(
                        ClaimSensitivity.confidential
                        if function in {"finance", "hr"}
                        else ClaimSensitivity.internal
                    ),
                )
            )
            claims.append(
                self._claim(
                    tenant_id=tenant_id,
                    domain="notices",
                    entity_type="notices_summary",
                    entity_id=f"notice-{function}",
                    claim_key="notices_count",
                    value_number=float(4 + idx),
                    admin_function=function,
                    sensitivity=ClaimSensitivity.low,
                )
            )
            claims.append(
                self._claim(
                    tenant_id=tenant_id,
                    domain="notices",
                    entity_type="notices_summary",
                    entity_id=f"notice-{function}",
                    claim_key="critical_notices",
                    value_number=float(idx % 2),
                    admin_function=function,
                    sensitivity=ClaimSensitivity.low,
                )
            )

        return claims

    def create_tenant(
        self,
        *,
        db: Session,
        payload: SystemAdminTenantCreateRequest,
        created_by: str,
    ) -> dict[str, object]:
        domain = self._normalize_domain(payload.email_domain)
        existing = db.scalar(select(Tenant.id).where(Tenant.domain == domain))
        if existing:
            raise ValidationError(
                message="Tenant domain already exists",
                code="TENANT_DOMAIN_EXISTS",
            )

        requested_subdomain = payload.subdomain.strip().lower() if payload.subdomain else ""
        base_subdomain = self._slugify(
            requested_subdomain or domain.split(".", 1)[0]
        )
        subdomain = self._next_available_subdomain(db, base_subdomain)

        tenant = Tenant(
            name=payload.tenant_name.strip(),
            domain=domain,
            subdomain=subdomain,
            plan_tier=self._coerce_plan_tier(payload.plan_tier),
            status=TenantStatus.active,
            google_workspace_domain=domain,
        )
        db.add(tenant)
        db.flush()

        identity_service.bootstrap_tenant_runtime(db, tenant.id)

        seeded_users: list[User] = []
        if payload.seed_mock_users:
            seeded_users = self._build_mock_users(tenant.id, domain)
            db.add_all(seeded_users)
            db.flush()

        if payload.seed_mock_claims:
            claims = self._build_overview_claims(tenant.id)
            claims.extend(self._build_scoped_claims(tenant.id, seeded_users))
            db.add_all(claims)

        graph_counts = control_plane_graph_service.rebuild_tenant_graph(
            db=db,
            tenant_id=tenant.id,
        )

        db.commit()
        db.refresh(tenant)

        users_count = int(
            db.scalar(select(func.count(User.id)).where(User.tenant_id == tenant.id)) or 0
        )
        claims_count = int(
            db.scalar(select(func.count(Claim.id)).where(Claim.tenant_id == tenant.id)) or 0
        )

        notes = [
            f"Provisioned by system admin: {created_by}",
            f"Domain onboarding active for *@{domain}",
            "Control-plane graph compiled for governance and lineage APIs",
        ]

        return {
            "tenant_id": tenant.id,
            "tenant_name": tenant.name,
            "email_domain": tenant.domain,
            "subdomain": tenant.subdomain,
            "status": tenant.status.value,
            "plan_tier": tenant.plan_tier.value,
            "users_count": users_count,
            "claims_count": claims_count,
            "graph_node_count": int(graph_counts.get("node_count", 0)),
            "graph_edge_count": int(graph_counts.get("edge_count", 0)),
            "created_at": tenant.created_at,
            "seeded_user_emails": [user.email for user in seeded_users],
            "notes": notes,
        }


tenant_onboarding_service = TenantOnboardingService()
