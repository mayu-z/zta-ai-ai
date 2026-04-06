from __future__ import annotations

import base64
import json
import random
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AuditLog,
    Claim,
    ClaimSensitivity,
    DataSource,
    DataSourceStatus,
    DataSourceType,
    DomainSourceBinding,
    DomainKeyword,
    IntentDefinition,
    PersonaType,
    RolePolicy,
    SchemaField,
    Tenant,
    TenantStatus,
    User,
    UserStatus,
)


IPEDS_TENANT_ID = "33333333-3333-3333-3333-333333333333"
TENANT_NAME = "Northbridge University Sandbox"
TENANT_DOMAIN = "ipeds.local"
TENANT_SUBDOMAIN = "ipeds"

DEPARTMENTS: tuple[tuple[str, str], ...] = (
    ("CSE", "Computer Science and Engineering"),
    ("ECE", "Electronics and Communication"),
    ("ME", "Mechanical Engineering"),
    ("CE", "Civil Engineering"),
    ("BBA", "Business Administration"),
    ("LAW", "School of Law"),
    ("MED", "Medical Sciences"),
    ("BIO", "Biological Sciences"),
    ("MATH", "Mathematics"),
    ("ART", "Liberal Arts"),
)

ADMIN_FUNCTIONS: tuple[str, ...] = ("admissions", "finance", "hr", "exam")

BINDING_DOMAINS: tuple[str, ...] = (
    "academic",
    "finance",
    "hr",
    "admissions",
    "exam",
    "department",
    "campus",
    "admin",
    "notices",
)


@dataclass(frozen=True)
class SeedProfile:
    name: str
    student_count: int
    faculty_count: int
    institution_count: int
    months: int
    audit_entries: int


SEED_PROFILES: dict[str, SeedProfile] = {
    "test": SeedProfile(
        name="test",
        student_count=60,
        faculty_count=18,
        institution_count=16,
        months=4,
        audit_entries=30,
    ),
    "full": SeedProfile(
        name="full",
        student_count=2500,
        faculty_count=320,
        institution_count=180,
        months=24,
        audit_entries=320,
    ),
}


def _resolve_profile(profile: str | None) -> SeedProfile:
    key = (profile or "full").strip().lower()
    return SEED_PROFILES.get(key, SEED_PROFILES["full"])


def _profile_seed(profile: SeedProfile) -> int:
    return 20260405 if profile.name == "full" else 424242


def _encode_config(payload: dict[str, object]) -> str:
    raw = json.dumps(payload, ensure_ascii=True, sort_keys=True)
    return base64.b64encode(raw.encode("utf-8")).decode("utf-8")


def _courses_by_department() -> dict[str, list[str]]:
    return {
        code: [f"{code}{100 + i}" for i in range(1, 13)]
        for code, _name in DEPARTMENTS
    }


def _course_window(courses: list[str], start: int, size: int = 3) -> list[str]:
    if not courses:
        return []

    out: list[str] = []
    for i in range(size):
        out.append(courses[(start + i) % len(courses)])
    return out


def _role_policy_defaults() -> list[dict[str, object]]:
    secure_defaults = {
        "sensitive_domains": ["finance", "hr"],
        "require_business_hours_for_sensitive": False,
        "business_hours_start": 8,
        "business_hours_end": 20,
        "require_trusted_device_for_sensitive": True,
        "require_mfa_for_sensitive": True,
    }

    rows = [
        {
            "role_key": "student",
            "display_name": "Student",
            "description": "Personal academics, finance-self, and notice access",
            "allowed_domains": ["academic", "finance", "notices"],
            "masked_fields": ["salary", "bank_account", "ssn", "tax_id"],
            "aggregate_only": False,
            "chat_enabled": True,
            "row_scope_mode": "owner_id",
        },
        {
            "role_key": "faculty",
            "display_name": "Faculty",
            "description": "Course-level academic, HR self, and notice access",
            "allowed_domains": ["academic", "hr", "notices"],
            "masked_fields": ["bank_account", "ssn", "tax_id"],
            "aggregate_only": False,
            "chat_enabled": True,
            "row_scope_mode": "course_ids",
        },
        {
            "role_key": "dept_head",
            "display_name": "Department Head",
            "description": "Department operations across academic/department/exam",
            "allowed_domains": ["academic", "department", "exam", "hr", "notices"],
            "masked_fields": ["bank_account", "ssn", "tax_id"],
            "aggregate_only": False,
            "chat_enabled": True,
            "row_scope_mode": "department_id",
        },
        {
            "role_key": "hod",
            "display_name": "HOD (Alias)",
            "description": "Alias policy for department head compatibility",
            "allowed_domains": ["academic", "department", "exam", "hr", "notices"],
            "masked_fields": ["bank_account", "ssn", "tax_id"],
            "aggregate_only": False,
            "chat_enabled": True,
            "row_scope_mode": "department_id",
        },
        {
            "role_key": "admin_staff:admissions",
            "display_name": "Admissions Office",
            "description": "Admissions operations and admissions notices",
            "allowed_domains": ["admissions", "notices"],
            "masked_fields": ["bank_account", "ssn", "tax_id"],
            "aggregate_only": False,
            "chat_enabled": True,
            "row_scope_mode": "admin_function",
        },
        {
            "role_key": "admin_staff:finance",
            "display_name": "Finance Office",
            "description": "Fee and finance operations",
            "allowed_domains": ["finance", "notices"],
            "masked_fields": ["bank_account", "ssn", "tax_id"],
            "aggregate_only": False,
            "chat_enabled": True,
            "row_scope_mode": "admin_function",
        },
        {
            "role_key": "finance_dept",
            "display_name": "Finance Department (Alias)",
            "description": "Alias policy for finance admin compatibility",
            "allowed_domains": ["finance", "notices"],
            "masked_fields": ["bank_account", "ssn", "tax_id"],
            "aggregate_only": False,
            "chat_enabled": True,
            "row_scope_mode": "admin_function",
        },
        {
            "role_key": "admin_staff:hr",
            "display_name": "HR Office",
            "description": "HR operations and HR notices",
            "allowed_domains": ["hr", "notices"],
            "masked_fields": ["salary", "bank_account", "ssn", "tax_id"],
            "aggregate_only": False,
            "chat_enabled": True,
            "row_scope_mode": "admin_function",
        },
        {
            "role_key": "admin_staff:exam",
            "display_name": "Examination Office",
            "description": "Exam scheduling, outcomes, and notices",
            "allowed_domains": ["exam", "academic", "notices"],
            "masked_fields": ["bank_account", "ssn", "tax_id"],
            "aggregate_only": False,
            "chat_enabled": True,
            "row_scope_mode": "admin_function",
        },
        {
            "role_key": "examination_head",
            "display_name": "Examination Head (Alias)",
            "description": "Alias policy for exam admin compatibility",
            "allowed_domains": ["exam", "academic", "notices"],
            "masked_fields": ["bank_account", "ssn", "tax_id"],
            "aggregate_only": False,
            "chat_enabled": True,
            "row_scope_mode": "admin_function",
        },
        {
            "role_key": "executive",
            "display_name": "Executive",
            "description": "Cross-domain aggregate campus leadership insights",
            "allowed_domains": [
                "campus_aggregate",
                "academic_aggregate",
                "finance_aggregate",
                "hr_aggregate",
                "admissions_aggregate",
                "exam_aggregate",
                "department_aggregate",
                "notices",
            ],
            "masked_fields": ["student_pii", "salary_row", "ssn", "bank_account"],
            "aggregate_only": True,
            "chat_enabled": True,
            "row_scope_mode": None,
        },
        {
            "role_key": "it_head",
            "display_name": "IT Head",
            "description": "Admin-only access, business-domain chat blocked",
            "allowed_domains": ["admin"],
            "masked_fields": [],
            "aggregate_only": False,
            "chat_enabled": False,
            "row_scope_mode": None,
            "sensitive_domains": ["admin"],
        },
        {
            "role_key": "it_admin",
            "display_name": "IT Admin",
            "description": "Admin-only access, business-domain chat blocked",
            "allowed_domains": ["admin"],
            "masked_fields": [],
            "aggregate_only": False,
            "chat_enabled": False,
            "row_scope_mode": None,
            "sensitive_domains": ["admin"],
        },
    ]

    with_security: list[dict[str, object]] = []
    for row in rows:
        merged = {**secure_defaults, **row}
        with_security.append(merged)
    return with_security


def _domain_keyword_defaults() -> dict[str, list[str]]:
    return {
        "academic": [
            "academic",
            "academics",
            "attendance",
            "grade",
            "gpa",
            "course",
            "subject",
            "semester",
            "class",
            "curriculum",
            "performance",
        ],
        "finance": [
            "finance",
            "financial",
            "fee",
            "fees",
            "payment",
            "dues",
            "budget",
            "tuition",
            "invoice",
            "revenue",
            "collection",
            "collections",
        ],
        "hr": [
            "hr",
            "human resources",
            "leave",
            "employee",
            "faculty record",
            "attrition",
            "headcount",
            "payslip",
        ],
        "admissions": [
            "admission",
            "admissions",
            "applicant",
            "application",
            "statistics",
            "intake",
            "enrollment funnel",
        ],
        "exam": [
            "exam",
            "examination",
            "exam office",
            "pass rate",
            "marks",
            "result",
            "backlog",
        ],
        "department": [
            "department",
            "dept",
            "department metric",
            "department performance",
            "hod",
        ],
        "campus": [
            "campus",
            "cross campus",
            "demographics",
            "hbcu",
            "public",
            "private",
            "enrollment",
            "kpi",
            "trend",
            "size distribution",
        ],
        "admin": [
            "audit",
            "audit log",
            "data source",
            "connector",
            "security",
            "incident",
            "schema",
        ],
        "notices": [
            "notice",
            "notices",
            "announcement",
            "circular",
            "alert",
            "bulletin",
        ],
    }


def _intent_defaults() -> list[dict[str, object]]:
    return [
        {
            "intent_name": "it_head_block_academic",
            "domain": "academic",
            "entity_type": "attendance_summary",
            "slot_keys": ["attendance_percentage", "subject_count"],
            "keywords": ["academic", "attendance", "grade", "course"],
            "persona_types": ["it_head"],
            "requires_aggregation": False,
            "is_default": True,
            "priority": 1,
        },
        {
            "intent_name": "it_head_block_finance",
            "domain": "finance",
            "entity_type": "executive_finance_summary",
            "slot_keys": ["tuition_collected", "outstanding_dues"],
            "keywords": ["finance", "fee", "tuition", "dues", "budget"],
            "persona_types": ["it_head"],
            "requires_aggregation": True,
            "is_default": True,
            "priority": 2,
        },
        {
            "intent_name": "it_head_block_hr",
            "domain": "hr",
            "entity_type": "executive_hr_summary",
            "slot_keys": ["headcount", "attrition_events"],
            "keywords": ["hr", "leave", "salary", "headcount", "attrition"],
            "persona_types": ["it_head"],
            "requires_aggregation": True,
            "is_default": True,
            "priority": 3,
        },
        {
            "intent_name": "it_head_block_admissions",
            "domain": "admissions",
            "entity_type": "executive_admissions_summary",
            "slot_keys": ["total_applications", "admitted_count"],
            "keywords": ["admission", "admissions", "application", "applicant"],
            "persona_types": ["it_head"],
            "requires_aggregation": True,
            "is_default": True,
            "priority": 4,
        },
        {
            "intent_name": "it_head_block_exam",
            "domain": "exam",
            "entity_type": "executive_exam_summary",
            "slot_keys": ["total_exams", "passed_exams"],
            "keywords": ["exam", "examination", "result", "marks"],
            "persona_types": ["it_head"],
            "requires_aggregation": True,
            "is_default": True,
            "priority": 5,
        },
        {
            "intent_name": "it_head_block_department",
            "domain": "department",
            "entity_type": "department_summary",
            "slot_keys": ["department_metric", "student_count"],
            "keywords": ["department", "dept", "hod"],
            "persona_types": ["it_head"],
            "requires_aggregation": False,
            "is_default": True,
            "priority": 6,
        },
        {
            "intent_name": "it_head_block_campus",
            "domain": "campus",
            "entity_type": "institution_enrollment_summary",
            "slot_keys": ["total_enrollment", "institution_count"],
            "keywords": ["campus", "enrollment", "institution", "kpi", "overview"],
            "persona_types": ["it_head"],
            "requires_aggregation": True,
            "is_default": True,
            "priority": 7,
        },
        {
            "intent_name": "it_head_block_notices",
            "domain": "notices",
            "entity_type": "notices_summary",
            "slot_keys": ["notices_count", "critical_notices"],
            "keywords": ["notice", "announcement", "circular", "alert"],
            "persona_types": ["it_head"],
            "requires_aggregation": True,
            "is_default": True,
            "priority": 8,
        },
        {
            "intent_name": "executive_kpi",
            "domain": "campus",
            "entity_type": "executive_summary",
            "slot_keys": ["kpi_value", "trend_delta"],
            "keywords": ["kpi", "trend", "overview", "metrics", "performance"],
            "persona_types": ["executive"],
            "requires_aggregation": True,
            "is_default": True,
            "priority": 10,
        },
        {
            "intent_name": "executive_enrollment_overview",
            "domain": "campus",
            "entity_type": "institution_enrollment_summary",
            "slot_keys": ["total_enrollment", "institution_count"],
            "keywords": ["enrollment", "headcount", "students", "enrolled"],
            "persona_types": ["executive"],
            "requires_aggregation": True,
            "is_default": False,
            "priority": 20,
        },
        {
            "intent_name": "institution_demographics",
            "domain": "campus",
            "entity_type": "institution_demographics",
            "slot_keys": ["hbcu_count", "public_count", "private_count", "total_institutions"],
            "keywords": ["demographics", "hbcu", "public", "private", "sector"],
            "persona_types": ["executive"],
            "requires_aggregation": True,
            "is_default": False,
            "priority": 30,
        },
        {
            "intent_name": "institution_size_distribution",
            "domain": "campus",
            "entity_type": "institution_size_summary",
            "slot_keys": ["small_count", "medium_count", "large_count", "total_institutions"],
            "keywords": ["size", "distribution", "small", "medium", "large"],
            "persona_types": ["executive"],
            "requires_aggregation": True,
            "is_default": False,
            "priority": 40,
        },
        {
            "intent_name": "executive_academic_overview",
            "domain": "academic",
            "entity_type": "executive_academic_summary",
            "slot_keys": ["total_passed_students", "total_course_registrations"],
            "keywords": ["academic", "pass", "course registrations", "academic summary"],
            "persona_types": ["executive"],
            "requires_aggregation": True,
            "is_default": False,
            "priority": 50,
        },
        {
            "intent_name": "executive_finance_overview",
            "domain": "finance",
            "entity_type": "executive_finance_summary",
            "slot_keys": ["tuition_collected", "outstanding_dues"],
            "keywords": ["finance", "tuition", "dues", "collections"],
            "persona_types": ["executive"],
            "requires_aggregation": True,
            "is_default": False,
            "priority": 60,
        },
        {
            "intent_name": "executive_hr_overview",
            "domain": "hr",
            "entity_type": "executive_hr_summary",
            "slot_keys": ["headcount", "attrition_events"],
            "keywords": ["hr", "headcount", "attrition", "workforce"],
            "persona_types": ["executive"],
            "requires_aggregation": True,
            "is_default": False,
            "priority": 70,
        },
        {
            "intent_name": "executive_admissions_overview",
            "domain": "admissions",
            "entity_type": "executive_admissions_summary",
            "slot_keys": ["total_applications", "admitted_count"],
            "keywords": ["admissions", "applications", "admitted", "intake"],
            "persona_types": ["executive"],
            "requires_aggregation": True,
            "is_default": False,
            "priority": 80,
        },
        {
            "intent_name": "executive_exam_overview",
            "domain": "exam",
            "entity_type": "executive_exam_summary",
            "slot_keys": ["total_exams", "passed_exams"],
            "keywords": ["exam", "result", "pass", "outcome"],
            "persona_types": ["executive"],
            "requires_aggregation": True,
            "is_default": False,
            "priority": 90,
        },
        {
            "intent_name": "executive_department_overview",
            "domain": "department",
            "entity_type": "executive_department_summary",
            "slot_keys": ["department_metric", "student_count"],
            "keywords": ["department", "dept", "department metric"],
            "persona_types": ["executive"],
            "requires_aggregation": True,
            "is_default": False,
            "priority": 100,
        },
        {
            "intent_name": "student_attendance",
            "domain": "academic",
            "entity_type": "attendance_summary",
            "slot_keys": ["attendance_percentage", "subject_count"],
            "keywords": [
                "attendance",
                "present",
                "class attendance",
                "subject",
                "subjects",
                "my subjects",
                "course",
                "courses",
                "my courses",
            ],
            "persona_types": ["student"],
            "requires_aggregation": False,
            "is_default": True,
            "priority": 110,
        },
        {
            "intent_name": "student_grades",
            "domain": "academic",
            "entity_type": "grade_summary",
            "slot_keys": ["gpa", "passed_subjects"],
            "keywords": ["grade", "gpa", "result", "marks"],
            "persona_types": ["student"],
            "requires_aggregation": False,
            "is_default": False,
            "priority": 120,
        },
        {
            "intent_name": "student_fee",
            "domain": "finance",
            "entity_type": "fee_summary",
            "slot_keys": ["fee_balance", "due_date"],
            "keywords": ["fee", "fees", "balance", "dues", "payment"],
            "persona_types": ["student"],
            "requires_aggregation": False,
            "is_default": True,
            "priority": 130,
        },
        {
            "intent_name": "faculty_course_attendance",
            "domain": "academic",
            "entity_type": "faculty_course_summary",
            "slot_keys": ["course_count", "avg_attendance"],
            "keywords": ["my courses", "course attendance", "class performance"],
            "persona_types": ["faculty"],
            "requires_aggregation": False,
            "is_default": True,
            "priority": 140,
        },
        {
            "intent_name": "faculty_leave_status",
            "domain": "hr",
            "entity_type": "faculty_hr_summary",
            "slot_keys": ["leave_balance", "pending_requests"],
            "keywords": ["leave", "pending leave", "hr status"],
            "persona_types": ["faculty"],
            "requires_aggregation": False,
            "is_default": True,
            "priority": 150,
        },
        {
            "intent_name": "department_metrics",
            "domain": "department",
            "entity_type": "department_summary",
            "slot_keys": ["department_metric", "student_count"],
            "keywords": ["department", "dept", "department performance"],
            "persona_types": ["dept_head"],
            "requires_aggregation": False,
            "is_default": True,
            "priority": 160,
        },
        {
            "intent_name": "dept_exam_summary",
            "domain": "exam",
            "entity_type": "department_exam_summary",
            "slot_keys": ["exam_backlog", "pass_rate"],
            "keywords": ["exam backlog", "department exam", "pass rate"],
            "persona_types": ["dept_head"],
            "requires_aggregation": False,
            "is_default": False,
            "priority": 170,
        },
        {
            "intent_name": "admissions_overview",
            "domain": "admissions",
            "entity_type": "admin_function_summary",
            "slot_keys": ["function_metric", "record_count"],
            "keywords": [
                "admissions",
                "admission",
                "applicant",
                "applicants",
                "applications",
                "intake",
                "admission summary",
            ],
            "persona_types": ["admin_staff"],
            "requires_aggregation": True,
            "is_default": True,
            "priority": 180,
        },
        {
            "intent_name": "finance_office_summary",
            "domain": "finance",
            "entity_type": "admin_function_summary",
            "slot_keys": ["function_metric", "record_count"],
            "keywords": ["finance", "collections", "payments", "fee operations"],
            "persona_types": ["admin_staff"],
            "requires_aggregation": True,
            "is_default": True,
            "priority": 190,
        },
        {
            "intent_name": "hr_office_summary",
            "domain": "hr",
            "entity_type": "admin_function_summary",
            "slot_keys": ["function_metric", "record_count"],
            "keywords": ["hr", "employee", "leave operations", "attrition"],
            "persona_types": ["admin_staff"],
            "requires_aggregation": True,
            "is_default": True,
            "priority": 200,
        },
        {
            "intent_name": "exam_office_summary",
            "domain": "exam",
            "entity_type": "admin_function_summary",
            "slot_keys": ["function_metric", "record_count"],
            "keywords": ["exam office", "examination office", "exam records"],
            "persona_types": ["admin_staff"],
            "requires_aggregation": True,
            "is_default": True,
            "priority": 210,
        },
        {
            "intent_name": "campus_notices",
            "domain": "notices",
            "entity_type": "notices_summary",
            "slot_keys": ["notices_count", "critical_notices"],
            "keywords": ["notice", "announcement", "circular", "alert"],
            "persona_types": ["student", "faculty", "dept_head", "admin_staff", "executive"],
            "requires_aggregation": True,
            "is_default": True,
            "priority": 220,
        },
        {
            "intent_name": "institution_profile",
            "domain": "admin",
            "entity_type": "institution_catalog",
            "slot_keys": ["profile"],
            "keywords": ["institution profile", "campus profile", "university profile", "details"],
            "persona_types": ["it_head"],
            "requires_aggregation": False,
            "is_default": True,
            "priority": 230,
        },
        {
            "intent_name": "admin_security_posture",
            "domain": "admin",
            "entity_type": "security_summary",
            "slot_keys": ["unresolved_incidents", "critical_alerts"],
            "keywords": ["security", "incident", "alerts", "vulnerability"],
            "persona_types": ["it_head"],
            "requires_aggregation": True,
            "is_default": False,
            "priority": 240,
        },
        {
            "intent_name": "admin_data_sources",
            "domain": "admin",
            "entity_type": "admin_data_sources",
            "slot_keys": ["sources"],
            "keywords": ["data sources", "connectors", "connections"],
            "persona_types": ["it_head"],
            "requires_aggregation": False,
            "is_default": False,
            "priority": 250,
        },
        {
            "intent_name": "admin_audit_log",
            "domain": "admin",
            "entity_type": "admin_audit_log",
            "slot_keys": ["entries"],
            "keywords": ["audit log", "audit", "activity log", "events"],
            "persona_types": ["it_head"],
            "requires_aggregation": False,
            "is_default": False,
            "priority": 260,
        },
    ]


def _purge_tenant_data(db: Session, tenant_id: str) -> None:
    db.query(AuditLog).filter(AuditLog.tenant_id == tenant_id).delete(
        synchronize_session=False
    )
    db.query(Claim).filter(Claim.tenant_id == tenant_id).delete(synchronize_session=False)
    db.query(DomainSourceBinding).filter(
        DomainSourceBinding.tenant_id == tenant_id
    ).delete(synchronize_session=False)
    db.query(IntentDefinition).filter(IntentDefinition.tenant_id == tenant_id).delete(
        synchronize_session=False
    )
    db.query(DomainKeyword).filter(DomainKeyword.tenant_id == tenant_id).delete(
        synchronize_session=False
    )
    db.query(RolePolicy).filter(RolePolicy.tenant_id == tenant_id).delete(
        synchronize_session=False
    )
    db.query(SchemaField).filter(SchemaField.tenant_id == tenant_id).delete(
        synchronize_session=False
    )
    db.query(DataSource).filter(DataSource.tenant_id == tenant_id).delete(
        synchronize_session=False
    )
    db.query(User).filter(User.tenant_id == tenant_id).delete(synchronize_session=False)


def _ensure_tenant(db: Session) -> Tenant:
    tenant = db.scalar(select(Tenant).where(Tenant.id == IPEDS_TENANT_ID))
    if tenant is None:
        tenant = Tenant(
            id=IPEDS_TENANT_ID,
            name=TENANT_NAME,
            domain=TENANT_DOMAIN,
            subdomain=TENANT_SUBDOMAIN,
            status=TenantStatus.active,
            google_workspace_domain=TENANT_DOMAIN,
        )
        db.add(tenant)
        return tenant

    tenant.name = TENANT_NAME
    tenant.domain = TENANT_DOMAIN
    tenant.subdomain = TENANT_SUBDOMAIN
    tenant.status = TenantStatus.active
    tenant.google_workspace_domain = TENANT_DOMAIN
    return tenant


def _as_str(value: object | None, default: str = "") -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return default
    return str(value)


def _as_bool(value: object | None, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return default


def _as_int(value: object | None, default: int) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if text:
            try:
                return int(text)
            except ValueError:
                return default
    return default


def _as_str_list(value: object | None) -> list[str]:
    if isinstance(value, (list, tuple)):
        out: list[str] = []
        for item in value:
            text = _as_str(item).strip()
            if text:
                out.append(text)
        return out
    return []


def _upsert_runtime_config(db: Session, tenant_id: str) -> dict[str, int]:
    role_defaults = _role_policy_defaults()
    keyword_defaults = _domain_keyword_defaults()
    intent_defaults = _intent_defaults()

    role_policies_seeded = 0
    domain_keywords_seeded = 0
    intent_definitions_seeded = 0
    domain_source_bindings_seeded = 0

    for item in role_defaults:
        role_key = str(item["role_key"])
        row = db.scalar(
            select(RolePolicy).where(
                RolePolicy.tenant_id == tenant_id,
                RolePolicy.role_key == role_key,
            )
        )
        if row is None:
            row = RolePolicy(
                tenant_id=tenant_id,
                role_key=role_key,
                display_name=str(item["display_name"]),
            )
            db.add(row)
            role_policies_seeded += 1

        row.display_name = _as_str(item.get("display_name"), role_key)
        row.description = _as_str(item.get("description"), "")
        row.allowed_domains = _as_str_list(item.get("allowed_domains"))
        row.masked_fields = _as_str_list(item.get("masked_fields"))
        row.aggregate_only = _as_bool(item.get("aggregate_only"), False)
        row.chat_enabled = _as_bool(item.get("chat_enabled"), True)
        row.row_scope_mode = _as_str(item.get("row_scope_mode"), "") or None
        row.sensitive_domains = _as_str_list(item.get("sensitive_domains")) or [
            "finance",
            "hr",
        ]
        row.require_business_hours_for_sensitive = _as_bool(
            item.get("require_business_hours_for_sensitive", False)
        )
        row.business_hours_start = _as_int(item.get("business_hours_start"), 8)
        row.business_hours_end = _as_int(item.get("business_hours_end"), 20)
        row.require_trusted_device_for_sensitive = _as_bool(
            item.get("require_trusted_device_for_sensitive", True)
        )
        row.require_mfa_for_sensitive = _as_bool(
            item.get("require_mfa_for_sensitive", True),
            True,
        )
        row.is_active = True

    for domain, keywords in keyword_defaults.items():
        row = db.scalar(
            select(DomainKeyword).where(
                DomainKeyword.tenant_id == tenant_id,
                DomainKeyword.domain == domain,
            )
        )
        if row is None:
            row = DomainKeyword(
                tenant_id=tenant_id,
                domain=domain,
                keywords=list(keywords),
                is_active=True,
            )
            db.add(row)
            domain_keywords_seeded += 1
        else:
            row.keywords = list(keywords)
            row.is_active = True

    for item in intent_defaults:
        intent_name = str(item["intent_name"])
        row = db.scalar(
            select(IntentDefinition).where(
                IntentDefinition.tenant_id == tenant_id,
                IntentDefinition.intent_name == intent_name,
            )
        )
        if row is None:
            row = IntentDefinition(
                tenant_id=tenant_id,
                intent_name=intent_name,
                domain=str(item["domain"]),
                entity_type=str(item["entity_type"]),
            )
            db.add(row)
            intent_definitions_seeded += 1

        row.domain = _as_str(item.get("domain"), row.domain)
        row.entity_type = _as_str(item.get("entity_type"), row.entity_type)
        row.slot_keys = _as_str_list(item.get("slot_keys"))
        row.keywords = _as_str_list(item.get("keywords"))
        row.persona_types = _as_str_list(item.get("persona_types"))
        row.requires_aggregation = _as_bool(item.get("requires_aggregation"), False)
        row.is_default = _as_bool(item.get("is_default"), False)
        row.priority = _as_int(item.get("priority"), 100)
        row.is_active = True

    for domain in BINDING_DOMAINS:
        row = db.scalar(
            select(DomainSourceBinding).where(
                DomainSourceBinding.tenant_id == tenant_id,
                DomainSourceBinding.domain == domain,
            )
        )
        if row is None:
            row = DomainSourceBinding(
                tenant_id=tenant_id,
                domain=domain,
                source_type=DataSourceType.ipeds_claims,
                data_source_id=None,
                is_active=True,
            )
            db.add(row)
            domain_source_bindings_seeded += 1
        else:
            row.source_type = DataSourceType.ipeds_claims
            row.data_source_id = None
            row.is_active = True

    role_keys = {str(item["role_key"]) for item in role_defaults}
    domains = set(keyword_defaults.keys())
    intents = {str(item["intent_name"]) for item in intent_defaults}

    for row in db.scalars(
        select(RolePolicy).where(RolePolicy.tenant_id == tenant_id)
    ).all():
        if row.role_key not in role_keys:
            row.is_active = False

    for row in db.scalars(
        select(DomainKeyword).where(DomainKeyword.tenant_id == tenant_id)
    ).all():
        if row.domain not in domains:
            row.is_active = False

    for row in db.scalars(
        select(IntentDefinition).where(IntentDefinition.tenant_id == tenant_id)
    ).all():
        if row.intent_name not in intents:
            row.is_active = False

    for row in db.scalars(
        select(DomainSourceBinding).where(DomainSourceBinding.tenant_id == tenant_id)
    ).all():
        if row.domain not in BINDING_DOMAINS:
            row.is_active = False

    return {
        "role_policies_seeded": role_policies_seeded,
        "domain_keywords_seeded": domain_keywords_seeded,
        "intent_definitions_seeded": intent_definitions_seeded,
        "domain_source_bindings_seeded": domain_source_bindings_seeded,
    }


def _seed_users(db: Session, profile: SeedProfile, rng: random.Random) -> dict[str, list[User]]:
    courses = _courses_by_department()

    groups: dict[str, list[User]] = {
        "all": [],
        "executive": [],
        "admin_staff": [],
        "it_head": [],
        "dept_head": [],
        "faculty": [],
        "students": [],
    }

    def register(
        *,
        email: str,
        name: str,
        persona_type: PersonaType,
        department_code: str | None,
        external_id: str,
        group: str,
        admin_function: str | None = None,
        course_ids: list[str] | None = None,
        masked_fields: list[str] | None = None,
    ) -> None:
        user = User(
            tenant_id=IPEDS_TENANT_ID,
            email=email,
            name=name,
            persona_type=persona_type,
            department=department_code,
            external_id=external_id,
            admin_function=admin_function,
            course_ids=list(course_ids or []),
            masked_fields=list(masked_fields or []),
            status=UserStatus.active,
        )
        groups["all"].append(user)
        groups[group].append(user)

    register(
        email="executive@ipeds.local",
        name="Executive Council",
        persona_type=PersonaType.executive,
        department_code="BBA",
        external_id="EXEC-0001",
        group="executive",
    )
    register(
        email="admissions@ipeds.local",
        name="Admissions Office",
        persona_type=PersonaType.admin_staff,
        department_code="BBA",
        external_id="ADM-0001",
        admin_function="admissions",
        group="admin_staff",
    )
    register(
        email="finance@ipeds.local",
        name="Finance Office",
        persona_type=PersonaType.admin_staff,
        department_code="BBA",
        external_id="FIN-0001",
        admin_function="finance",
        group="admin_staff",
    )
    register(
        email="hr@ipeds.local",
        name="HR Office",
        persona_type=PersonaType.admin_staff,
        department_code="BBA",
        external_id="HR-0001",
        admin_function="hr",
        group="admin_staff",
    )
    register(
        email="exam@ipeds.local",
        name="Exam Office",
        persona_type=PersonaType.admin_staff,
        department_code="BBA",
        external_id="EXM-0001",
        admin_function="exam",
        group="admin_staff",
    )
    register(
        email="ithead@ipeds.local",
        name="IT Head",
        persona_type=PersonaType.it_head,
        department_code="CSE",
        external_id="IT-0001",
        group="it_head",
    )
    register(
        email="student@ipeds.local",
        name="Student Primary",
        persona_type=PersonaType.student,
        department_code="CSE",
        external_id="STU-100000",
        group="students",
    )
    register(
        email="faculty@ipeds.local",
        name="Faculty Primary",
        persona_type=PersonaType.faculty,
        department_code="CSE",
        external_id="FAC-100000",
        course_ids=_course_window(courses["CSE"], 0, size=3),
        group="faculty",
    )

    for code, _name in DEPARTMENTS:
        register(
            email=f"hod.{code.lower()}@ipeds.local",
            name=f"{code} Department Head",
            persona_type=PersonaType.dept_head,
            department_code=code,
            external_id=f"HOD-{code}",
            group="dept_head",
        )

    dept_codes = [code for code, _name in DEPARTMENTS]

    faculty_needed = max(profile.faculty_count - len(groups["faculty"]), 0)
    for idx in range(1, faculty_needed + 1):
        code = dept_codes[(idx - 1) % len(dept_codes)]
        register(
            email=f"faculty{idx:04d}@ipeds.local",
            name=f"Faculty {idx:04d}",
            persona_type=PersonaType.faculty,
            department_code=code,
            external_id=f"FAC-{idx:06d}",
            course_ids=_course_window(courses[code], idx, size=3),
            group="faculty",
        )

    students_needed = max(profile.student_count - len(groups["students"]), 0)
    for idx in range(1, students_needed + 1):
        code = rng.choice(dept_codes)
        register(
            email=f"student{idx:05d}@ipeds.local",
            name=f"Student {idx:05d}",
            persona_type=PersonaType.student,
            department_code=code,
            external_id=f"STU-{idx:06d}",
            group="students",
        )

    db.add_all(groups["all"])
    db.flush()
    print(
        "Seeded users:",
        {
            "students": len(groups["students"]),
            "faculty": len(groups["faculty"]),
            "dept_head": len(groups["dept_head"]),
            "admin_staff": len(groups["admin_staff"]),
            "executive": len(groups["executive"]),
            "it_head": len(groups["it_head"]),
        },
    )
    return groups


def _seed_data_sources(db: Session) -> int:
    rows = [
        DataSource(
            tenant_id=IPEDS_TENANT_ID,
            name="Campus Claim Store",
            source_type=DataSourceType.ipeds_claims,
            config_encrypted=_encode_config(
                {
                    "connector": "mock_claims",
                    "claims_table": "claims",
                    "notes": "Trusted claim-backed source",
                }
            ),
            department_scope=[],
            status=DataSourceStatus.connected,
        ),
        DataSource(
            tenant_id=IPEDS_TENANT_ID,
            name="Campus PostgreSQL Mirror",
            source_type=DataSourceType.postgresql,
            config_encrypted=_encode_config(
                {
                    "connection_url": "postgresql://readonly:readonly@db.example.edu:5432/campus",
                    "claims_table": "claims",
                }
            ),
            department_scope=[],
            status=DataSourceStatus.connected,
        ),
        DataSource(
            tenant_id=IPEDS_TENANT_ID,
            name="Campus MySQL Mirror",
            source_type=DataSourceType.mysql,
            config_encrypted=_encode_config(
                {
                    "connection_url": "mysql+pymysql://readonly:readonly@db.example.edu:3306/campus",
                    "claims_table": "claims",
                }
            ),
            department_scope=[],
            status=DataSourceStatus.connected,
        ),
        DataSource(
            tenant_id=IPEDS_TENANT_ID,
            name="ERP Adapter",
            source_type=DataSourceType.erpnext,
            config_encrypted=_encode_config(
                {
                    "base_url": "https://erp.example.edu",
                    "api_key": "seeded-placeholder-key",
                    "api_secret": "seeded-placeholder-secret",
                }
            ),
            department_scope=["BBA", "CSE"],
            status=DataSourceStatus.paused,
        ),
        DataSource(
            tenant_id=IPEDS_TENANT_ID,
            name="Research Sheet Connector",
            source_type=DataSourceType.google_sheets,
            config_encrypted=_encode_config(
                {
                    "service_account_json": {"project_id": "seeded-research-project"},
                    "spreadsheet_id": "seeded-sheet-id",
                }
            ),
            department_scope=["BIO", "MATH"],
            status=DataSourceStatus.disconnected,
        ),
    ]

    db.add_all(rows)
    db.flush()
    print(f"Seeded {len(rows)} data source records")
    return len(rows)


def _claim(
    *,
    domain: str,
    entity_type: str,
    entity_id: str,
    claim_key: str,
    value_number: float | int | None = None,
    value_text: str | None = None,
    value_json: dict[str, object] | None = None,
    owner_id: str | None = None,
    department_id: str | None = None,
    course_id: str | None = None,
    admin_function: str | None = None,
    sensitivity: ClaimSensitivity = ClaimSensitivity.internal,
    compliance_tags: list[str] | None = None,
) -> Claim:
    return Claim(
        tenant_id=IPEDS_TENANT_ID,
        domain=domain,
        entity_type=entity_type,
        entity_id=entity_id,
        owner_id=owner_id,
        department_id=department_id,
        course_id=course_id,
        admin_function=admin_function,
        claim_key=claim_key,
        value_number=float(value_number) if isinstance(value_number, int) else value_number,
        value_text=value_text,
        value_json=value_json,
        provenance=f"campus-mock:{entity_type}:{entity_id}",
        sensitivity=sensitivity,
        compliance_tags=list(compliance_tags or []),
    )


def _build_student_claims(students: list[User], rng: random.Random) -> list[Claim]:
    rows: list[Claim] = []
    today = datetime.now(tz=UTC).date()

    for idx, student in enumerate(students, start=1):
        owner_id = student.external_id
        dept = (student.department or "GEN")[:100]
        entity_id = f"student-{idx:06d}"

        attendance = round(rng.uniform(67.0, 99.0), 2)
        subject_count = rng.randint(5, 9)
        gpa = round(rng.uniform(2.0, 4.0), 2)
        passed = rng.randint(max(2, subject_count - 3), subject_count)
        balance = round(rng.uniform(0.0, 6000.0), 2)
        due_date = (today + timedelta(days=rng.randint(3, 50))).isoformat()

        rows.append(
            _claim(
                domain="academic",
                entity_type="attendance_summary",
                entity_id=entity_id,
                owner_id=owner_id,
                department_id=dept,
                claim_key="attendance_percentage",
                value_number=attendance,
                sensitivity=ClaimSensitivity.internal,
                compliance_tags=["FERPA"],
            )
        )
        rows.append(
            _claim(
                domain="academic",
                entity_type="attendance_summary",
                entity_id=entity_id,
                owner_id=owner_id,
                department_id=dept,
                claim_key="subject_count",
                value_number=subject_count,
                sensitivity=ClaimSensitivity.internal,
                compliance_tags=["FERPA"],
            )
        )
        rows.append(
            _claim(
                domain="academic",
                entity_type="grade_summary",
                entity_id=entity_id,
                owner_id=owner_id,
                department_id=dept,
                claim_key="gpa",
                value_number=gpa,
                sensitivity=ClaimSensitivity.internal,
                compliance_tags=["FERPA"],
            )
        )
        rows.append(
            _claim(
                domain="academic",
                entity_type="grade_summary",
                entity_id=entity_id,
                owner_id=owner_id,
                department_id=dept,
                claim_key="passed_subjects",
                value_number=passed,
                sensitivity=ClaimSensitivity.internal,
                compliance_tags=["FERPA"],
            )
        )
        rows.append(
            _claim(
                domain="finance",
                entity_type="fee_summary",
                entity_id=entity_id,
                owner_id=owner_id,
                department_id=dept,
                claim_key="fee_balance",
                value_number=balance,
                sensitivity=ClaimSensitivity.confidential,
                compliance_tags=["FERPA", "PCI"],
            )
        )
        rows.append(
            _claim(
                domain="finance",
                entity_type="fee_summary",
                entity_id=entity_id,
                owner_id=owner_id,
                department_id=dept,
                claim_key="due_date",
                value_text=due_date,
                sensitivity=ClaimSensitivity.confidential,
                compliance_tags=["FERPA", "PCI"],
            )
        )
        rows.append(
            _claim(
                domain="notices",
                entity_type="notices_summary",
                entity_id=entity_id,
                owner_id=owner_id,
                department_id=dept,
                claim_key="notices_count",
                value_number=rng.randint(1, 14),
                sensitivity=ClaimSensitivity.low,
                compliance_tags=["OPS"],
            )
        )
        rows.append(
            _claim(
                domain="notices",
                entity_type="notices_summary",
                entity_id=entity_id,
                owner_id=owner_id,
                department_id=dept,
                claim_key="critical_notices",
                value_number=rng.randint(0, 2),
                sensitivity=ClaimSensitivity.low,
                compliance_tags=["OPS"],
            )
        )

    return rows


def _build_faculty_claims(faculty_users: list[User], rng: random.Random) -> list[Claim]:
    rows: list[Claim] = []

    for idx, faculty in enumerate(faculty_users, start=1):
        department_id = (faculty.department or "GEN")[:100]
        course_ids = list(faculty.course_ids or [])
        course_id = course_ids[0] if course_ids else None
        entity_id = f"faculty-{idx:05d}"

        rows.append(
            _claim(
                domain="academic",
                entity_type="faculty_course_summary",
                entity_id=entity_id,
                owner_id=faculty.external_id,
                department_id=department_id,
                course_id=course_id,
                claim_key="course_count",
                value_number=max(1, len(course_ids)),
                sensitivity=ClaimSensitivity.internal,
                compliance_tags=["FERPA"],
            )
        )
        rows.append(
            _claim(
                domain="academic",
                entity_type="faculty_course_summary",
                entity_id=entity_id,
                owner_id=faculty.external_id,
                department_id=department_id,
                course_id=course_id,
                claim_key="avg_attendance",
                value_number=round(rng.uniform(68.0, 97.5), 2),
                sensitivity=ClaimSensitivity.internal,
                compliance_tags=["FERPA"],
            )
        )
        rows.append(
            _claim(
                domain="hr",
                entity_type="faculty_hr_summary",
                entity_id=entity_id,
                owner_id=faculty.external_id,
                department_id=department_id,
                course_id=course_id,
                claim_key="leave_balance",
                value_number=rng.randint(2, 28),
                sensitivity=ClaimSensitivity.confidential,
                compliance_tags=["HR"],
            )
        )
        rows.append(
            _claim(
                domain="hr",
                entity_type="faculty_hr_summary",
                entity_id=entity_id,
                owner_id=faculty.external_id,
                department_id=department_id,
                course_id=course_id,
                claim_key="pending_requests",
                value_number=rng.randint(0, 4),
                sensitivity=ClaimSensitivity.confidential,
                compliance_tags=["HR"],
            )
        )
        rows.append(
            _claim(
                domain="notices",
                entity_type="notices_summary",
                entity_id=entity_id,
                owner_id=faculty.external_id,
                department_id=department_id,
                course_id=course_id,
                claim_key="notices_count",
                value_number=rng.randint(1, 10),
                sensitivity=ClaimSensitivity.low,
                compliance_tags=["OPS"],
            )
        )
        rows.append(
            _claim(
                domain="notices",
                entity_type="notices_summary",
                entity_id=entity_id,
                owner_id=faculty.external_id,
                department_id=department_id,
                course_id=course_id,
                claim_key="critical_notices",
                value_number=rng.randint(0, 2),
                sensitivity=ClaimSensitivity.low,
                compliance_tags=["OPS"],
            )
        )

    return rows


def _build_department_claims(students: list[User], rng: random.Random) -> list[Claim]:
    rows: list[Claim] = []
    student_counts = Counter(user.department for user in students if user.department)

    for code, _name in DEPARTMENTS:
        dept_count = int(student_counts.get(code, 0))

        rows.append(
            _claim(
                domain="department",
                entity_type="department_summary",
                entity_id=f"department-{code.lower()}",
                department_id=code,
                claim_key="department_metric",
                value_number=round(rng.uniform(64.0, 98.0), 2),
                sensitivity=ClaimSensitivity.internal,
                compliance_tags=["OPS"],
            )
        )
        rows.append(
            _claim(
                domain="department",
                entity_type="department_summary",
                entity_id=f"department-{code.lower()}",
                department_id=code,
                claim_key="student_count",
                value_number=dept_count,
                sensitivity=ClaimSensitivity.internal,
                compliance_tags=["OPS"],
            )
        )
        rows.append(
            _claim(
                domain="exam",
                entity_type="department_exam_summary",
                entity_id=f"exam-{code.lower()}",
                department_id=code,
                claim_key="exam_backlog",
                value_number=rng.randint(0, max(8, dept_count // 20 + 5)),
                sensitivity=ClaimSensitivity.internal,
                compliance_tags=["EXAM"],
            )
        )
        rows.append(
            _claim(
                domain="exam",
                entity_type="department_exam_summary",
                entity_id=f"exam-{code.lower()}",
                department_id=code,
                claim_key="pass_rate",
                value_number=round(rng.uniform(60.0, 98.0), 2),
                sensitivity=ClaimSensitivity.internal,
                compliance_tags=["EXAM"],
            )
        )
        rows.append(
            _claim(
                domain="notices",
                entity_type="notices_summary",
                entity_id=f"notice-{code.lower()}",
                department_id=code,
                claim_key="notices_count",
                value_number=rng.randint(8, 35),
                sensitivity=ClaimSensitivity.low,
                compliance_tags=["OPS"],
            )
        )
        rows.append(
            _claim(
                domain="notices",
                entity_type="notices_summary",
                entity_id=f"notice-{code.lower()}",
                department_id=code,
                claim_key="critical_notices",
                value_number=rng.randint(0, 3),
                sensitivity=ClaimSensitivity.low,
                compliance_tags=["OPS"],
            )
        )

    return rows


def _build_admin_function_claims(profile: SeedProfile, rng: random.Random) -> list[Claim]:
    rows: list[Claim] = []

    for function_name in ADMIN_FUNCTIONS:
        domain = function_name if function_name != "exam" else "exam"

        for period in range(profile.months):
            year = 2025 + (period // 12)
            month = 1 + (period % 12)
            entity_id = f"{function_name}-{year}-{month:02d}"

            if function_name == "admissions":
                function_metric = rng.randint(1200, 5200)
                record_count = rng.randint(180, 950)
            elif function_name == "finance":
                function_metric = round(rng.uniform(350000.0, 4200000.0), 2)
                record_count = rng.randint(250, 1800)
            elif function_name == "hr":
                function_metric = round(rng.uniform(12.0, 38.0), 2)
                record_count = rng.randint(20, 260)
            else:
                function_metric = round(rng.uniform(68.0, 98.0), 2)
                record_count = rng.randint(120, 900)

            sensitivity = (
                ClaimSensitivity.confidential
                if function_name in {"finance", "hr"}
                else ClaimSensitivity.internal
            )

            rows.append(
                _claim(
                    domain=domain,
                    entity_type="admin_function_summary",
                    entity_id=entity_id,
                    admin_function=function_name,
                    claim_key="function_metric",
                    value_number=function_metric,
                    sensitivity=sensitivity,
                    compliance_tags=["OPS", function_name.upper()],
                )
            )
            rows.append(
                _claim(
                    domain=domain,
                    entity_type="admin_function_summary",
                    entity_id=entity_id,
                    admin_function=function_name,
                    claim_key="record_count",
                    value_number=record_count,
                    sensitivity=sensitivity,
                    compliance_tags=["OPS", function_name.upper()],
                )
            )

        rows.append(
            _claim(
                domain="notices",
                entity_type="notices_summary",
                entity_id=f"notice-{function_name}",
                admin_function=function_name,
                claim_key="notices_count",
                value_number=rng.randint(5, 30),
                sensitivity=ClaimSensitivity.low,
                compliance_tags=["OPS"],
            )
        )
        rows.append(
            _claim(
                domain="notices",
                entity_type="notices_summary",
                entity_id=f"notice-{function_name}",
                admin_function=function_name,
                claim_key="critical_notices",
                value_number=rng.randint(0, 4),
                sensitivity=ClaimSensitivity.low,
                compliance_tags=["OPS"],
            )
        )

    return rows


def _build_institution_claims(profile: SeedProfile, rng: random.Random) -> list[Claim]:
    rows: list[Claim] = []

    prefixes = (
        "Northbridge",
        "Lakeside",
        "Grandview",
        "Redwood",
        "Sapphire",
        "Frontier",
        "Greenfield",
        "Stonehill",
        "Skyline",
        "Riverbend",
    )
    suffixes = (
        "University",
        "Institute",
        "College",
        "Academy",
        "Technical University",
    )
    states = ("CA", "TX", "NY", "FL", "IL", "WA", "MA", "NC", "GA", "AZ")

    for i in range(profile.institution_count):
        entity_id = f"inst-{i + 1:04d}"
        name = f"{prefixes[i % len(prefixes)]} {suffixes[(i // len(prefixes)) % len(suffixes)]}"
        state = states[i % len(states)]

        total_enrollment = rng.randint(1800, 48000)
        institution_count = 1

        is_public = rng.random() < 0.62
        is_hbcu = rng.random() < 0.08

        small_count = 1 if total_enrollment < 8000 else 0
        medium_count = 1 if 8000 <= total_enrollment < 20000 else 0
        large_count = 1 if total_enrollment >= 20000 else 0

        kpi_value = round(total_enrollment * rng.uniform(0.68, 0.95), 2)
        trend_delta = round(rng.uniform(-9.5, 14.0), 2)

        total_passed_students = int(total_enrollment * rng.uniform(0.58, 0.92))
        total_course_registrations = total_passed_students + rng.randint(450, 6500)

        tuition_collected = round(total_enrollment * rng.uniform(7500.0, 22000.0), 2)
        outstanding_dues = round(total_enrollment * rng.uniform(300.0, 2200.0), 2)

        headcount = total_enrollment + rng.randint(250, 3200)
        attrition_events = rng.randint(8, max(30, int(headcount * 0.08)))

        total_applications = rng.randint(total_enrollment, total_enrollment * 3)
        admitted_count = int(total_applications * rng.uniform(0.22, 0.74))

        total_exams = rng.randint(300, 5500)
        passed_exams = int(total_exams * rng.uniform(0.61, 0.97))

        department_metric = round(rng.uniform(65.0, 98.0), 2)

        profile_payload = {
            "institution_id": entity_id,
            "name": name,
            "state": state,
            "control": "Public" if is_public else "Private",
            "hbcu": is_hbcu,
            "enrollment_band": (
                "small"
                if small_count
                else "medium"
                if medium_count
                else "large"
            ),
            "website": f"https://{name.lower().replace(' ', '-')}.edu",
        }

        rows.extend(
            [
                _claim(
                    domain="campus",
                    entity_type="executive_summary",
                    entity_id=entity_id,
                    claim_key="kpi_value",
                    value_number=kpi_value,
                    sensitivity=ClaimSensitivity.internal,
                    compliance_tags=["EXEC"],
                ),
                _claim(
                    domain="campus",
                    entity_type="executive_summary",
                    entity_id=entity_id,
                    claim_key="trend_delta",
                    value_number=trend_delta,
                    sensitivity=ClaimSensitivity.internal,
                    compliance_tags=["EXEC"],
                ),
                _claim(
                    domain="campus",
                    entity_type="institution_enrollment_summary",
                    entity_id=entity_id,
                    claim_key="total_enrollment",
                    value_number=total_enrollment,
                    sensitivity=ClaimSensitivity.internal,
                    compliance_tags=["EXEC"],
                ),
                _claim(
                    domain="campus",
                    entity_type="institution_enrollment_summary",
                    entity_id=entity_id,
                    claim_key="institution_count",
                    value_number=institution_count,
                    sensitivity=ClaimSensitivity.internal,
                    compliance_tags=["EXEC"],
                ),
                _claim(
                    domain="campus",
                    entity_type="institution_demographics",
                    entity_id=entity_id,
                    claim_key="hbcu_count",
                    value_number=1 if is_hbcu else 0,
                    sensitivity=ClaimSensitivity.low,
                    compliance_tags=["EXEC"],
                ),
                _claim(
                    domain="campus",
                    entity_type="institution_demographics",
                    entity_id=entity_id,
                    claim_key="public_count",
                    value_number=1 if is_public else 0,
                    sensitivity=ClaimSensitivity.low,
                    compliance_tags=["EXEC"],
                ),
                _claim(
                    domain="campus",
                    entity_type="institution_demographics",
                    entity_id=entity_id,
                    claim_key="private_count",
                    value_number=0 if is_public else 1,
                    sensitivity=ClaimSensitivity.low,
                    compliance_tags=["EXEC"],
                ),
                _claim(
                    domain="campus",
                    entity_type="institution_demographics",
                    entity_id=entity_id,
                    claim_key="total_institutions",
                    value_number=1,
                    sensitivity=ClaimSensitivity.low,
                    compliance_tags=["EXEC"],
                ),
                _claim(
                    domain="campus",
                    entity_type="institution_size_summary",
                    entity_id=entity_id,
                    claim_key="small_count",
                    value_number=small_count,
                    sensitivity=ClaimSensitivity.low,
                    compliance_tags=["EXEC"],
                ),
                _claim(
                    domain="campus",
                    entity_type="institution_size_summary",
                    entity_id=entity_id,
                    claim_key="medium_count",
                    value_number=medium_count,
                    sensitivity=ClaimSensitivity.low,
                    compliance_tags=["EXEC"],
                ),
                _claim(
                    domain="campus",
                    entity_type="institution_size_summary",
                    entity_id=entity_id,
                    claim_key="large_count",
                    value_number=large_count,
                    sensitivity=ClaimSensitivity.low,
                    compliance_tags=["EXEC"],
                ),
                _claim(
                    domain="campus",
                    entity_type="institution_size_summary",
                    entity_id=entity_id,
                    claim_key="total_institutions",
                    value_number=1,
                    sensitivity=ClaimSensitivity.low,
                    compliance_tags=["EXEC"],
                ),
                _claim(
                    domain="academic",
                    entity_type="executive_academic_summary",
                    entity_id=entity_id,
                    claim_key="total_passed_students",
                    value_number=total_passed_students,
                    sensitivity=ClaimSensitivity.internal,
                    compliance_tags=["ACADEMIC"],
                ),
                _claim(
                    domain="academic",
                    entity_type="executive_academic_summary",
                    entity_id=entity_id,
                    claim_key="total_course_registrations",
                    value_number=total_course_registrations,
                    sensitivity=ClaimSensitivity.internal,
                    compliance_tags=["ACADEMIC"],
                ),
                _claim(
                    domain="finance",
                    entity_type="executive_finance_summary",
                    entity_id=entity_id,
                    claim_key="tuition_collected",
                    value_number=tuition_collected,
                    sensitivity=ClaimSensitivity.confidential,
                    compliance_tags=["FINANCE"],
                ),
                _claim(
                    domain="finance",
                    entity_type="executive_finance_summary",
                    entity_id=entity_id,
                    claim_key="outstanding_dues",
                    value_number=outstanding_dues,
                    sensitivity=ClaimSensitivity.confidential,
                    compliance_tags=["FINANCE"],
                ),
                _claim(
                    domain="hr",
                    entity_type="executive_hr_summary",
                    entity_id=entity_id,
                    claim_key="headcount",
                    value_number=headcount,
                    sensitivity=ClaimSensitivity.confidential,
                    compliance_tags=["HR"],
                ),
                _claim(
                    domain="hr",
                    entity_type="executive_hr_summary",
                    entity_id=entity_id,
                    claim_key="attrition_events",
                    value_number=attrition_events,
                    sensitivity=ClaimSensitivity.confidential,
                    compliance_tags=["HR"],
                ),
                _claim(
                    domain="admissions",
                    entity_type="executive_admissions_summary",
                    entity_id=entity_id,
                    claim_key="total_applications",
                    value_number=total_applications,
                    sensitivity=ClaimSensitivity.internal,
                    compliance_tags=["ADMISSIONS"],
                ),
                _claim(
                    domain="admissions",
                    entity_type="executive_admissions_summary",
                    entity_id=entity_id,
                    claim_key="admitted_count",
                    value_number=admitted_count,
                    sensitivity=ClaimSensitivity.internal,
                    compliance_tags=["ADMISSIONS"],
                ),
                _claim(
                    domain="exam",
                    entity_type="executive_exam_summary",
                    entity_id=entity_id,
                    claim_key="total_exams",
                    value_number=total_exams,
                    sensitivity=ClaimSensitivity.internal,
                    compliance_tags=["EXAM"],
                ),
                _claim(
                    domain="exam",
                    entity_type="executive_exam_summary",
                    entity_id=entity_id,
                    claim_key="passed_exams",
                    value_number=passed_exams,
                    sensitivity=ClaimSensitivity.internal,
                    compliance_tags=["EXAM"],
                ),
                _claim(
                    domain="department",
                    entity_type="executive_department_summary",
                    entity_id=entity_id,
                    claim_key="department_metric",
                    value_number=department_metric,
                    sensitivity=ClaimSensitivity.internal,
                    compliance_tags=["OPS"],
                ),
                _claim(
                    domain="department",
                    entity_type="executive_department_summary",
                    entity_id=entity_id,
                    claim_key="student_count",
                    value_number=total_enrollment,
                    sensitivity=ClaimSensitivity.internal,
                    compliance_tags=["OPS"],
                ),
                _claim(
                    domain="admin",
                    entity_type="institution_catalog",
                    entity_id=entity_id,
                    claim_key="profile",
                    value_json=profile_payload,
                    sensitivity=ClaimSensitivity.internal,
                    compliance_tags=["ADMIN"],
                ),
            ]
        )

    return rows


def _build_security_claims(profile: SeedProfile, rng: random.Random) -> list[Claim]:
    rows: list[Claim] = []
    weekly_points = max(profile.months * 4, 12)

    for idx in range(weekly_points):
        entity_id = f"security-week-{idx + 1:03d}"
        rows.append(
            _claim(
                domain="admin",
                entity_type="security_summary",
                entity_id=entity_id,
                claim_key="unresolved_incidents",
                value_number=rng.randint(1, 18),
                sensitivity=ClaimSensitivity.restricted,
                compliance_tags=["SECURITY"],
            )
        )
        rows.append(
            _claim(
                domain="admin",
                entity_type="security_summary",
                entity_id=entity_id,
                claim_key="critical_alerts",
                value_number=rng.randint(0, 5),
                sensitivity=ClaimSensitivity.restricted,
                compliance_tags=["SECURITY"],
            )
        )

    return rows


def _build_global_notice_claims(profile: SeedProfile, rng: random.Random) -> list[Claim]:
    rows: list[Claim] = []
    cycles = max(profile.months, 8)

    for idx in range(cycles):
        entity_id = f"notice-global-{idx + 1:03d}"
        rows.append(
            _claim(
                domain="notices",
                entity_type="notices_summary",
                entity_id=entity_id,
                claim_key="notices_count",
                value_number=rng.randint(20, 80),
                sensitivity=ClaimSensitivity.low,
                compliance_tags=["OPS"],
            )
        )
        rows.append(
            _claim(
                domain="notices",
                entity_type="notices_summary",
                entity_id=entity_id,
                claim_key="critical_notices",
                value_number=rng.randint(0, 7),
                sensitivity=ClaimSensitivity.low,
                compliance_tags=["OPS"],
            )
        )

    return rows


def _latency_flag(latency_ms: int) -> str:
    if 500 <= latency_ms <= 2000:
        return "normal"
    if latency_ms > 500:
        return "high"
    return "suspicious"


def _seed_audit_log(
    db: Session,
    users: list[User],
    profile: SeedProfile,
    rng: random.Random,
) -> int:
    if not users:
        return 0

    sample_queries = [
        ("Give me campus aggregate KPI summary", "campus", False, None),
        ("Show admissions trend for this quarter", "admissions", False, None),
        ("Show me raw salary rows", "hr", True, "DOMAIN_FORBIDDEN"),
        ("Show audit log entries", "admin", False, None),
        ("List all student records", "academic", True, "EXEC_AGGREGATE_ONLY"),
        ("Show exam pass metrics", "exam", False, None),
    ]

    now = datetime.now(tz=UTC)
    rows: list[AuditLog] = []
    for idx in range(profile.audit_entries):
        user = rng.choice(users)
        query, domain, blocked, reason = rng.choice(sample_queries)
        latency = rng.randint(120, 2800)
        rows.append(
            AuditLog(
                tenant_id=IPEDS_TENANT_ID,
                user_id=user.id,
                session_id=f"seed-session-{idx:05d}",
                query_text=query,
                intent_hash=f"seed-hash-{idx:05d}",
                domains_accessed=[domain],
                was_blocked=blocked,
                block_reason=reason,
                response_summary=(
                    "blocked by seeded policy guard"
                    if blocked
                    else "seeded successful response"
                ),
                latency_ms=latency,
                latency_flag=_latency_flag(latency),
                created_at=now - timedelta(minutes=idx * 5),
            )
        )

    db.add_all(rows)
    return len(rows)


def ensure_ipeds_runtime_config(db: Session) -> dict[str, int]:
    """Backfill runtime policy/registry tables for existing tenant state."""
    exists = db.scalar(select(Tenant.id).where(Tenant.id == IPEDS_TENANT_ID))
    if not exists:
        return {
            "role_policies_seeded": 0,
            "domain_keywords_seeded": 0,
            "intent_definitions_seeded": 0,
            "domain_source_bindings_seeded": 0,
        }
    return _upsert_runtime_config(db, IPEDS_TENANT_ID)


def seed_ipeds_claims(db: Session, profile: str | None = None) -> int:
    """
    Seed a large synthetic campus-university dataset.

    This replaces CSV/IPEDS-derived content with deterministic mock records that
    exercise all configured domains, persona scopes, intent paths, and admin routes.
    """
    selected = _resolve_profile(profile)
    rng = random.Random(_profile_seed(selected))

    tenant_exists = db.scalar(select(Tenant.id).where(Tenant.id == IPEDS_TENANT_ID))
    if tenant_exists:
        _purge_tenant_data(db, IPEDS_TENANT_ID)

    _ensure_tenant(db)
    db.flush()

    runtime_backfill = _upsert_runtime_config(db, IPEDS_TENANT_ID)

    user_groups = _seed_users(db, selected, rng)
    data_source_count = _seed_data_sources(db)

    claims: list[Claim] = []
    claims.extend(_build_student_claims(user_groups["students"], rng))
    claims.extend(_build_faculty_claims(user_groups["faculty"], rng))
    claims.extend(_build_department_claims(user_groups["students"], rng))
    claims.extend(_build_admin_function_claims(selected, rng))
    claims.extend(_build_institution_claims(selected, rng))
    claims.extend(_build_security_claims(selected, rng))
    claims.extend(_build_global_notice_claims(selected, rng))

    db.add_all(claims)
    audit_rows = _seed_audit_log(db, user_groups["all"], selected, rng)

    print(
        "Seeded campus-university mock dataset:",
        {
            "profile": selected.name,
            "claims": len(claims),
            "users": len(user_groups["all"]),
            "data_sources": data_source_count,
            "audit_rows": audit_rows,
            **runtime_backfill,
        },
    )
    return len(claims)
