from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import time
import uuid
from datetime import UTC, datetime
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlencode

import jwt
from jwt import InvalidTokenError, PyJWKClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import AuthenticationError
from app.core.security import create_access_token
from app.core.secret_manager import secret_manager
from app.db.models import (
    DataSource,
    DataSourceStatus,
    DataSourceType,
    DomainSourceBinding,
    DomainKeyword,
    FieldVisibility,
    IntentDefinition,
    IntentDetectionKeyword,
    PersonaType,
    RolePolicy,
    SchemaField,
    Tenant,
    TenantStatus,
    User,
    UserStatus,
)
from app.schemas.pipeline import ScopeContext


@dataclass
class GoogleIdentity:
    email: str
    name: str


ALL_DOMAINS = [
    "academic",
    "finance",
    "hr",
    "admissions",
    "exam",
    "department",
    "campus",
    "admin",
    "notices",
]

DEFAULT_DOMAIN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "academic": (
        "academic",
        "course",
        "student",
        "grade",
        "attendance",
        "subject",
        "class",
        "enrolled",
        "semester",
        "gpa",
    ),
    "finance": (
        "finance",
        "budget",
        "payment",
        "fee",
        "invoice",
        "balance",
        "due",
        "tuition",
    ),
    "hr": (
        "hr",
        "employee",
        "staff",
        "leave",
        "payroll",
        "vacation",
        "workload",
    ),
    "admissions": (
        "admissions",
        "application",
        "enrollment",
        "intake",
        "applicant",
    ),
    "exam": (
        "exam",
        "result",
        "schedule",
        "assessment",
        "marks",
        "score",
    ),
    "department": (
        "department",
        "team",
        "faculty",
        "program",
        "hod",
    ),
    "campus": (
        "campus",
        "facility",
        "operations",
        "transport",
        "institution",
        "infrastructure",
    ),
    "admin": (
        "admin",
        "policy",
        "security",
        "audit",
        "user",
        "access",
        "permission",
    ),
    "notices": (
        "notice",
        "announcement",
        "update",
        "circular",
        "alert",
    ),
}

DEFAULT_DATA_SOURCES: tuple[dict[str, object], ...] = (
    {
        "name": "Campus Claim Store",
        "source_type": DataSourceType.ipeds_claims,
        "config": {
            "connector": "mock_claims",
            "claims_table": "claims",
            "notes": "Trusted claim-backed source",
        },
        "department_scope": [],
        "status": DataSourceStatus.connected,
    },
    {
        "name": "Campus PostgreSQL Mirror",
        "source_type": DataSourceType.postgresql,
        "config": {
            "connection_url": "postgresql://readonly:readonly@db.example.edu:5432/campus",
            "claims_table": "claims",
        },
        "department_scope": [],
        "status": DataSourceStatus.connected,
    },
    {
        "name": "Campus MySQL Mirror",
        "source_type": DataSourceType.mysql,
        "config": {
            "connection_url": "mysql+pymysql://readonly:readonly@db.example.edu:3306/campus",
            "claims_table": "claims",
        },
        "department_scope": [],
        "status": DataSourceStatus.connected,
    },
    {
        "name": "ERP Adapter",
        "source_type": DataSourceType.erpnext,
        "config": {
            "base_url": "https://erp.example.edu",
            "api_key": "seeded-placeholder-key",
            "api_secret": "seeded-placeholder-secret",
        },
        "department_scope": ["BBA", "CSE"],
        "status": DataSourceStatus.paused,
    },
    {
        "name": "Research Sheet Connector",
        "source_type": DataSourceType.google_sheets,
        "config": {
            "service_account_json": {"project_id": "seeded-research-project"},
            "spreadsheet_id": "seeded-sheet-id",
        },
        "department_scope": ["BIO", "MATH"],
        "status": DataSourceStatus.disconnected,
    },
)


DEFAULT_INTENT_DEFINITIONS: tuple[dict[str, object], ...] = (
    {
        "intent_name": "executive_kpi",
        "domain": "campus",
        "entity_type": "executive_summary",
        "slot_keys": ["kpi_value", "trend_delta"],
        "keywords": ["kpi", "overview", "trend", "campus performance"],
        "persona_types": [PersonaType.executive.value],
        "requires_aggregation": True,
        "is_default": True,
        "priority": 40,
    },
    {
        "intent_name": "executive_enrollment_overview",
        "domain": "campus",
        "entity_type": "institution_enrollment_summary",
        "slot_keys": ["total_enrollment", "institution_count"],
        "keywords": ["enrollment", "headcount", "students", "institutions"],
        "persona_types": [PersonaType.executive.value],
        "requires_aggregation": True,
        "is_default": False,
        "priority": 45,
    },
    {
        "intent_name": "institution_demographics",
        "domain": "campus",
        "entity_type": "institution_demographics",
        "slot_keys": ["hbcu_count", "public_count", "private_count", "total_institutions"],
        "keywords": ["demographics", "hbcu", "public", "private", "sector"],
        "persona_types": [PersonaType.executive.value],
        "requires_aggregation": True,
        "is_default": False,
        "priority": 50,
    },
    {
        "intent_name": "institution_size_distribution",
        "domain": "campus",
        "entity_type": "institution_size_summary",
        "slot_keys": ["small_count", "medium_count", "large_count", "total_institutions"],
        "keywords": ["size", "distribution", "small", "medium", "large"],
        "persona_types": [PersonaType.executive.value],
        "requires_aggregation": True,
        "is_default": False,
        "priority": 55,
    },
    {
        "intent_name": "executive_finance_overview",
        "domain": "finance",
        "entity_type": "executive_finance_summary",
        "slot_keys": ["tuition_collected", "outstanding_dues"],
        "keywords": ["finance", "tuition", "dues", "collections"],
        "persona_types": [PersonaType.executive.value],
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
        "persona_types": [PersonaType.executive.value],
        "requires_aggregation": True,
        "is_default": False,
        "priority": 65,
    },
    {
        "intent_name": "executive_admissions_overview",
        "domain": "admissions",
        "entity_type": "executive_admissions_summary",
        "slot_keys": ["total_applications", "admitted_count"],
        "keywords": ["admissions", "applications", "admitted", "intake"],
        "persona_types": [PersonaType.executive.value],
        "requires_aggregation": True,
        "is_default": False,
        "priority": 70,
    },
    {
        "intent_name": "executive_exam_overview",
        "domain": "exam",
        "entity_type": "executive_exam_summary",
        "slot_keys": ["total_exams", "passed_exams"],
        "keywords": ["exam", "results", "outcomes", "passed exams"],
        "persona_types": [PersonaType.executive.value],
        "requires_aggregation": True,
        "is_default": False,
        "priority": 75,
    },
    {
        "intent_name": "executive_department_overview",
        "domain": "department",
        "entity_type": "executive_department_summary",
        "slot_keys": ["department_metric", "student_count"],
        "keywords": ["department summary", "department metric", "department"],
        "persona_types": [PersonaType.executive.value],
        "requires_aggregation": True,
        "is_default": False,
        "priority": 78,
    },
    {
        "intent_name": "student_attendance",
        "domain": "academic",
        "entity_type": "attendance_summary",
        "slot_keys": ["attendance_percentage", "subject_count"],
        "keywords": ["attendance", "present", "absent", "class attendance"],
        "persona_types": [PersonaType.student.value],
        "requires_aggregation": False,
        "is_default": True,
        "priority": 90,
    },
    {
        "intent_name": "student_grades",
        "domain": "academic",
        "entity_type": "grade_summary",
        "slot_keys": ["gpa", "passed_subjects"],
        "keywords": ["grade", "gpa", "marks", "result"],
        "persona_types": [PersonaType.student.value],
        "requires_aggregation": False,
        "is_default": False,
        "priority": 95,
    },
    {
        "intent_name": "student_fee",
        "domain": "finance",
        "entity_type": "fee_summary",
        "slot_keys": ["fee_balance", "due_date"],
        "keywords": ["fee", "fees", "balance", "dues", "payment", "tuition"],
        "persona_types": [PersonaType.student.value],
        "requires_aggregation": False,
        "is_default": True,
        "priority": 100,
    },
    {
        "intent_name": "faculty_course_attendance",
        "domain": "academic",
        "entity_type": "faculty_course_summary",
        "slot_keys": ["course_count", "avg_attendance"],
        "keywords": ["my courses", "course attendance", "class performance", "teaching load"],
        "persona_types": [PersonaType.faculty.value],
        "requires_aggregation": False,
        "is_default": True,
        "priority": 110,
    },
    {
        "intent_name": "faculty_leave_status",
        "domain": "hr",
        "entity_type": "faculty_hr_summary",
        "slot_keys": ["leave_balance", "pending_requests"],
        "keywords": ["leave", "pending leave", "vacation", "hr status"],
        "persona_types": [PersonaType.faculty.value],
        "requires_aggregation": False,
        "is_default": True,
        "priority": 115,
    },
    {
        "intent_name": "department_metrics",
        "domain": "department",
        "entity_type": "department_summary",
        "slot_keys": ["department_metric", "student_count"],
        "keywords": ["department", "dept", "department performance", "utilization"],
        "persona_types": [PersonaType.dept_head.value],
        "requires_aggregation": False,
        "is_default": True,
        "priority": 120,
    },
    {
        "intent_name": "dept_exam_summary",
        "domain": "exam",
        "entity_type": "department_exam_summary",
        "slot_keys": ["exam_backlog", "pass_rate"],
        "keywords": ["exam backlog", "pass rate", "department exam"],
        "persona_types": [PersonaType.dept_head.value],
        "requires_aggregation": False,
        "is_default": False,
        "priority": 125,
    },
    {
        "intent_name": "admissions_overview",
        "domain": "admissions",
        "entity_type": "admin_function_summary",
        "slot_keys": ["function_metric", "record_count"],
        "keywords": ["admissions", "admission", "applicant", "applications", "intake"],
        "persona_types": [PersonaType.admin_staff.value],
        "requires_aggregation": True,
        "is_default": True,
        "priority": 130,
    },
    {
        "intent_name": "finance_office_summary",
        "domain": "finance",
        "entity_type": "admin_function_summary",
        "slot_keys": ["function_metric", "record_count"],
        "keywords": ["finance", "collections", "payments", "fee operations", "receipts"],
        "persona_types": [PersonaType.admin_staff.value],
        "requires_aggregation": True,
        "is_default": True,
        "priority": 135,
    },
    {
        "intent_name": "hr_office_summary",
        "domain": "hr",
        "entity_type": "admin_function_summary",
        "slot_keys": ["function_metric", "record_count"],
        "keywords": ["hr", "employee", "leave operations", "attrition", "recruitment"],
        "persona_types": [PersonaType.admin_staff.value],
        "requires_aggregation": True,
        "is_default": True,
        "priority": 140,
    },
    {
        "intent_name": "exam_office_summary",
        "domain": "exam",
        "entity_type": "admin_function_summary",
        "slot_keys": ["function_metric", "record_count"],
        "keywords": ["exam office", "examination office", "exam records", "evaluation"],
        "persona_types": [PersonaType.admin_staff.value],
        "requires_aggregation": True,
        "is_default": True,
        "priority": 145,
    },
    {
        "intent_name": "campus_notices",
        "domain": "notices",
        "entity_type": "notices_summary",
        "slot_keys": ["notices_count", "critical_notices"],
        "keywords": ["notice", "announcement", "circular", "alert"],
        "persona_types": [
            PersonaType.student.value,
            PersonaType.faculty.value,
            PersonaType.dept_head.value,
            PersonaType.admin_staff.value,
            PersonaType.executive.value,
        ],
        "requires_aggregation": True,
        "is_default": True,
        "priority": 180,
    },
    {
        "intent_name": "institution_profile",
        "domain": "admin",
        "entity_type": "institution_catalog",
        "slot_keys": ["profile"],
        "keywords": ["institution profile", "campus profile", "university profile", "details"],
        "persona_types": [PersonaType.it_head.value],
        "requires_aggregation": False,
        "is_default": True,
        "priority": 185,
    },
    {
        "intent_name": "admin_security_posture",
        "domain": "admin",
        "entity_type": "security_summary",
        "slot_keys": ["unresolved_incidents", "critical_alerts"],
        "keywords": ["security", "incident", "alerts", "vulnerability"],
        "persona_types": [PersonaType.it_head.value],
        "requires_aggregation": True,
        "is_default": False,
        "priority": 190,
    },
    {
        "intent_name": "admin_data_sources",
        "domain": "admin",
        "entity_type": "admin_data_sources",
        "slot_keys": ["sources"],
        "keywords": ["data sources", "connectors", "connections"],
        "persona_types": [PersonaType.it_head.value],
        "requires_aggregation": False,
        "is_default": False,
        "priority": 195,
    },
    {
        "intent_name": "admin_audit_log",
        "domain": "admin",
        "entity_type": "admin_audit_log",
        "slot_keys": ["entries"],
        "keywords": ["audit log", "audit", "activity log", "events"],
        "persona_types": [PersonaType.it_head.value],
        "requires_aggregation": False,
        "is_default": False,
        "priority": 200,
    },
)


DEFAULT_INTENT_DETECTION_KEYWORDS: tuple[dict[str, str], ...] = (
    {"intent": "student_grades", "keyword_type": "grade_marker", "keyword": "gpa"},
    {"intent": "student_grades", "keyword_type": "grade_marker", "keyword": "grade"},
    {"intent": "student_grades", "keyword_type": "grade_marker", "keyword": "grades"},
    {"intent": "student_grades", "keyword_type": "grade_marker", "keyword": "marks"},
    {"intent": "student_grades", "keyword_type": "grade_marker", "keyword": "result"},
    {"intent": "student_grades", "keyword_type": "grade_marker", "keyword": "cgpa"},
    {"intent": "student_attendance", "keyword_type": "attendance_marker", "keyword": "attendance"},
    {"intent": "student_attendance", "keyword_type": "attendance_marker", "keyword": "present"},
    {"intent": "student_attendance", "keyword_type": "attendance_marker", "keyword": "absent"},
    {"intent": "student_attendance", "keyword_type": "attendance_marker", "keyword": "attend"},
    {"intent": "student_fee", "keyword_type": "fee_marker", "keyword": "fee"},
    {"intent": "student_fee", "keyword_type": "fee_marker", "keyword": "fees"},
    {"intent": "student_fee", "keyword_type": "fee_marker", "keyword": "balance"},
    {"intent": "student_fee", "keyword_type": "fee_marker", "keyword": "dues"},
    {"intent": "student_fee", "keyword_type": "fee_marker", "keyword": "payment"},
    {"intent": "student_fee", "keyword_type": "fee_marker", "keyword": "tuition"},
    {"intent": "faculty_leave_status", "keyword_type": "leave_marker", "keyword": "leave"},
    {"intent": "faculty_leave_status", "keyword_type": "leave_marker", "keyword": "vacation"},
    {"intent": "faculty_leave_status", "keyword_type": "leave_marker", "keyword": "pending leave"},
    {"intent": "faculty_course_attendance", "keyword_type": "course_marker", "keyword": "my courses"},
    {"intent": "faculty_course_attendance", "keyword_type": "course_marker", "keyword": "teaching load"},
    {"intent": "department_metrics", "keyword_type": "department_marker", "keyword": "department performance"},
    {"intent": "department_metrics", "keyword_type": "department_marker", "keyword": "utilization"},
    {"intent": "dept_exam_summary", "keyword_type": "exam_marker", "keyword": "exam backlog"},
    {"intent": "dept_exam_summary", "keyword_type": "exam_marker", "keyword": "pass rate"},
    {"intent": "admissions_overview", "keyword_type": "admissions_marker", "keyword": "admissions"},
    {"intent": "admissions_overview", "keyword_type": "admissions_marker", "keyword": "applications"},
    {"intent": "finance_office_summary", "keyword_type": "finance_marker", "keyword": "collections"},
    {"intent": "finance_office_summary", "keyword_type": "finance_marker", "keyword": "receipts"},
    {"intent": "hr_office_summary", "keyword_type": "hr_marker", "keyword": "attrition"},
    {"intent": "hr_office_summary", "keyword_type": "hr_marker", "keyword": "recruitment"},
    {"intent": "exam_office_summary", "keyword_type": "exam_office_marker", "keyword": "exam records"},
    {"intent": "exam_office_summary", "keyword_type": "exam_office_marker", "keyword": "evaluation"},
    {"intent": "executive_kpi", "keyword_type": "executive_marker", "keyword": "kpi"},
    {"intent": "executive_kpi", "keyword_type": "executive_marker", "keyword": "trend"},
    {"intent": "campus_notices", "keyword_type": "notice_marker", "keyword": "notice"},
    {"intent": "campus_notices", "keyword_type": "notice_marker", "keyword": "announcement"},
    {"intent": "admin_security_posture", "keyword_type": "security_marker", "keyword": "security"},
    {"intent": "admin_security_posture", "keyword_type": "security_marker", "keyword": "incident"},
    {"intent": "institution_profile", "keyword_type": "profile_marker", "keyword": "institution profile"},
)


DEFAULT_CLAIM_SCHEMA_FIELDS: tuple[dict[str, object], ...] = (
    {
        "real_table": "claims",
        "real_column": "domain",
        "alias_token": "claim_domain",
        "display_name": "Claim Domain",
        "data_type": "text",
        "visibility": FieldVisibility.visible,
        "pii_flag": False,
        "masked_for_personas": [],
    },
    {
        "real_table": "claims",
        "real_column": "entity_type",
        "alias_token": "claim_entity_type",
        "display_name": "Entity Type",
        "data_type": "text",
        "visibility": FieldVisibility.visible,
        "pii_flag": False,
        "masked_for_personas": [],
    },
    {
        "real_table": "claims",
        "real_column": "entity_id",
        "alias_token": "claim_entity_id",
        "display_name": "Entity Identifier",
        "data_type": "text",
        "visibility": FieldVisibility.visible,
        "pii_flag": False,
        "masked_for_personas": [],
    },
    {
        "real_table": "claims",
        "real_column": "owner_id",
        "alias_token": "record_owner",
        "display_name": "Record Owner",
        "data_type": "text",
        "visibility": FieldVisibility.masked,
        "pii_flag": True,
        "masked_for_personas": [
            PersonaType.executive.value,
            PersonaType.faculty.value,
            PersonaType.dept_head.value,
            PersonaType.admin_staff.value,
        ],
    },
    {
        "real_table": "claims",
        "real_column": "department_id",
        "alias_token": "record_department",
        "display_name": "Department",
        "data_type": "text",
        "visibility": FieldVisibility.visible,
        "pii_flag": False,
        "masked_for_personas": [],
    },
    {
        "real_table": "claims",
        "real_column": "course_id",
        "alias_token": "record_course",
        "display_name": "Course",
        "data_type": "text",
        "visibility": FieldVisibility.visible,
        "pii_flag": False,
        "masked_for_personas": [],
    },
    {
        "real_table": "claims",
        "real_column": "admin_function",
        "alias_token": "record_function",
        "display_name": "Admin Function",
        "data_type": "text",
        "visibility": FieldVisibility.visible,
        "pii_flag": False,
        "masked_for_personas": [],
    },
    {
        "real_table": "claims",
        "real_column": "claim_key",
        "alias_token": "metric_key",
        "display_name": "Metric Key",
        "data_type": "text",
        "visibility": FieldVisibility.visible,
        "pii_flag": False,
        "masked_for_personas": [],
    },
    {
        "real_table": "claims",
        "real_column": "value_number",
        "alias_token": "metric_value",
        "display_name": "Metric Value",
        "data_type": "number",
        "visibility": FieldVisibility.visible,
        "pii_flag": False,
        "masked_for_personas": [],
    },
    {
        "real_table": "claims",
        "real_column": "value_text",
        "alias_token": "metric_text",
        "display_name": "Metric Text",
        "data_type": "text",
        "visibility": FieldVisibility.visible,
        "pii_flag": False,
        "masked_for_personas": [],
    },
    {
        "real_table": "claims",
        "real_column": "value_json",
        "alias_token": "metric_payload",
        "display_name": "Metric Payload",
        "data_type": "json",
        "visibility": FieldVisibility.visible,
        "pii_flag": False,
        "masked_for_personas": [],
    },
    {
        "real_table": "claims",
        "real_column": "sensitivity",
        "alias_token": "data_sensitivity",
        "display_name": "Data Sensitivity",
        "data_type": "text",
        "visibility": FieldVisibility.visible,
        "pii_flag": False,
        "masked_for_personas": [],
    },
    {
        "real_table": "claims",
        "real_column": "created_at",
        "alias_token": "record_created_at",
        "display_name": "Created At",
        "data_type": "timestamp",
        "visibility": FieldVisibility.visible,
        "pii_flag": False,
        "masked_for_personas": [],
    },
)


class IdentityService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def _auth_provider(self) -> str:
        return self.settings.auth_provider.strip().lower()

    def _oidc_algorithms(self) -> list[str]:
        raw = self.settings.oidc_allowed_algorithms
        algorithms = [item.strip() for item in raw.split(",") if item.strip()]
        return algorithms or ["RS256"]

    def _oidc_shared_secret(self) -> str:
        return secret_manager.get_secret(
            "OIDC_SHARED_SECRET",
            fallback=self.settings.oidc_shared_secret,
        ).strip()

    def _decode_base32_secret(self, secret: str) -> bytes:
        normalized = secret.strip().replace(" ", "").upper()
        padding = "=" * (-len(normalized) % 8)
        return base64.b32decode(normalized + padding, casefold=True)

    def _totp_from_counter(self, secret: str, counter: int) -> str:
        secret_bytes = self._decode_base32_secret(secret)
        payload = counter.to_bytes(8, "big")
        digest = hmac.new(secret_bytes, payload, hashlib.sha1).digest()
        offset = digest[-1] & 0x0F
        code_int = (
            ((digest[offset] & 0x7F) << 24)
            | ((digest[offset + 1] & 0xFF) << 16)
            | ((digest[offset + 2] & 0xFF) << 8)
            | (digest[offset + 3] & 0xFF)
        )
        return f"{code_int % 1_000_000:06d}"

    def _totp_counter(self) -> int:
        return int(time.time() // self.settings.mfa_totp_period_seconds)

    def _build_totp_uri(self, email: str, secret: str) -> str:
        issuer = self.settings.mfa_totp_issuer.strip() or "ZTA-AI"
        label = quote(f"{issuer}:{email}")
        query = urlencode(
            {
                "secret": secret,
                "issuer": issuer,
                "algorithm": "SHA1",
                "digits": 6,
                "period": self.settings.mfa_totp_period_seconds,
            }
        )
        return f"otpauth://totp/{label}?{query}"

    def _effective_mfa_verified(
        self,
        user: User,
        requested_mfa_verified: bool | None,
    ) -> bool:
        # Users with TOTP configured must complete MFA verification for each session.
        if user.mfa_method == "totp":
            return bool(requested_mfa_verified)
        if requested_mfa_verified is None:
            return True
        return bool(requested_mfa_verified)

    def _get_active_user_by_id(self, db: Session, user_id: str) -> User:
        user = db.scalar(
            select(User).where(
                User.id == user_id,
                User.status == UserStatus.active,
            )
        )
        if not user:
            raise AuthenticationError(
                message="User account is invalid or inactive",
                code="USER_INVALID",
            )
        return user

    def enroll_totp(self, db: Session, user_id: str) -> dict[str, str]:
        user = self._get_active_user_by_id(db, user_id)
        secret = base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")

        user.mfa_method = "totp"
        user.mfa_totp_secret = secret
        user.mfa_enabled = False
        user.mfa_enrolled_at = None

        db.add(user)
        db.commit()

        return {
            "method": "totp",
            "secret": secret,
            "otpauth_uri": self._build_totp_uri(user.email, secret),
        }

    def verify_totp_code(self, db: Session, user_id: str, code: str) -> None:
        normalized_code = code.strip().replace(" ", "")
        if not normalized_code.isdigit() or len(normalized_code) != 6:
            raise AuthenticationError(
                message="Invalid MFA code",
                code="MFA_CODE_INVALID",
            )

        user = self._get_active_user_by_id(db, user_id)
        if user.mfa_method != "totp" or not user.mfa_totp_secret:
            raise AuthenticationError(
                message="TOTP is not enrolled for this user",
                code="MFA_NOT_ENROLLED",
            )

        counter = self._totp_counter()
        window = max(0, int(self.settings.mfa_totp_window_steps))
        valid = False
        for offset in range(-window, window + 1):
            expected = self._totp_from_counter(user.mfa_totp_secret, counter + offset)
            if hmac.compare_digest(expected, normalized_code):
                valid = True
                break

        if not valid:
            raise AuthenticationError(
                message="Invalid MFA code",
                code="MFA_CODE_INVALID",
            )

        user.mfa_enabled = True
        user.mfa_enrolled_at = user.mfa_enrolled_at or datetime.now(tz=UTC)

        db.add(user)
        db.commit()

    def verify_google_token(self, google_token: str) -> GoogleIdentity:
        provider = self._auth_provider()
        if provider != "mock_google":
            raise AuthenticationError(
                message=(
                    f"Google auth endpoint is disabled because AUTH_PROVIDER={provider}"
                ),
                code="AUTH_PROVIDER_DISABLED",
            )

        if not self.settings.use_mock_google_oauth:
            raise AuthenticationError(
                message="Mock Google OAuth is disabled by configuration",
                code="MOCK_AUTH_DISABLED",
            )

        prefix = self.settings.mock_google_token_prefix
        if google_token.startswith(prefix):
            email = google_token[len(prefix) :].strip().lower()
            return GoogleIdentity(
                email=email, name=email.split("@")[0].replace(".", " ").title()
            )

        try:
            decoded = base64.b64decode(google_token).decode("utf-8")
            data = json.loads(decoded)
            email = str(data["email"]).lower()
            name = str(data.get("name", email.split("@")[0]))
            return GoogleIdentity(email=email, name=name)
        except Exception as exc:  # noqa: BLE001
            raise AuthenticationError(
                message="Mock Google token format is invalid",
                code="GOOGLE_TOKEN_INVALID",
            ) from exc

    def verify_oidc_token(self, id_token: str) -> GoogleIdentity:
        provider = self._auth_provider()
        if provider != "oidc":
            raise AuthenticationError(
                message=f"OIDC auth endpoint is disabled because AUTH_PROVIDER={provider}",
                code="AUTH_PROVIDER_DISABLED",
            )

        issuer = self.settings.oidc_issuer.strip()
        audience = self.settings.oidc_audience.strip()
        if not issuer or not audience:
            raise AuthenticationError(
                message="OIDC provider is not configured",
                code="OIDC_CONFIG_INVALID",
            )

        try:
            if self.settings.oidc_jwks_url:
                jwk_client = PyJWKClient(self.settings.oidc_jwks_url)
                signing_key = jwk_client.get_signing_key_from_jwt(id_token)
                claims = jwt.decode(
                    id_token,
                    key=signing_key.key,
                    algorithms=self._oidc_algorithms(),
                    audience=audience,
                    issuer=issuer,
                    options={"require": ["exp", "iat", "iss", "aud"]},
                )
            elif self._oidc_shared_secret():
                claims = jwt.decode(
                    id_token,
                    key=self._oidc_shared_secret(),
                    algorithms=self._oidc_algorithms(),
                    audience=audience,
                    issuer=issuer,
                    options={"require": ["exp", "iat", "iss", "aud"]},
                )
            else:
                raise AuthenticationError(
                    message="OIDC key source is missing",
                    code="OIDC_CONFIG_INVALID",
                )
        except InvalidTokenError as exc:
            raise AuthenticationError(
                message="OIDC token validation failed",
                code="OIDC_TOKEN_INVALID",
            ) from exc

        email = str(
            claims.get("email")
            or claims.get("upn")
            or claims.get("preferred_username")
            or ""
        ).strip().lower()
        if not email or "@" not in email:
            raise AuthenticationError(
                message="OIDC token is missing a valid email claim",
                code="OIDC_EMAIL_MISSING",
            )

        name = str(
            claims.get("name")
            or claims.get("given_name")
            or email.split("@")[0].replace(".", " ").title()
        )
        return GoogleIdentity(email=email, name=name)

    def _dev_auto_provision_enabled(self) -> bool:
        return (
            self.settings.environment.strip().lower() != "production"
            and bool(self.settings.dev_auto_provision_identity)
        )

    def _default_dev_persona(self) -> PersonaType:
        candidate = str(self.settings.dev_default_persona).strip().lower()
        try:
            return PersonaType(candidate)
        except ValueError:
            return PersonaType.executive

    def _slugify_subdomain(self, value: str) -> str:
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

    def _infer_persona_from_email(self, email: str) -> PersonaType:
        local = email.split("@", 1)[0].lower()
        if any(token in local for token in ("it", "security", "ops", "admin")):
            return PersonaType.it_head
        if any(token in local for token in ("exec", "ceo", "director", "vp", "dean", "principal", "chancellor")):
            return PersonaType.executive
        if any(token in local for token in ("student", "learner")):
            return PersonaType.student
        if any(token in local for token in ("faculty", "prof", "teacher")):
            return PersonaType.faculty
        if any(token in local for token in ("hod", "depthead", "departmenthead")):
            return PersonaType.dept_head
        if any(token in local for token in ("finance", "hr", "admission", "exam")):
            return PersonaType.admin_staff
        return self._default_dev_persona()

    def _infer_admin_function_from_email(self, email: str) -> str | None:
        local = email.split("@", 1)[0].lower()
        if "admission" in local:
            return "admissions"
        if "finance" in local:
            return "finance"
        if "hr" in local:
            return "hr"
        if "exam" in local:
            return "exam"
        return None

    def _derive_external_id(self, email: str) -> str:
        digest = hashlib.sha256(email.encode("utf-8")).hexdigest()[:10].upper()
        return f"USR-{digest}"

    def _encode_source_config(self, payload: dict[str, object]) -> str:
        return base64.b64encode(
            json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        ).decode("utf-8")

    def _ensure_default_role_policies(self, db: Session, tenant_id: str) -> None:
        existing_rows = db.scalars(
            select(RolePolicy).where(RolePolicy.tenant_id == tenant_id)
        ).all()
        existing_by_key = {row.role_key: row for row in existing_rows}

        default_policies: list[dict[str, object]] = [
            {
                "role_key": "executive",
                "display_name": "Executive",
                "allowed_domains": [
                    "academic",
                    "finance",
                    "hr",
                    "admissions",
                    "exam",
                    "department",
                    "campus",
                    "notices",
                ],
                "aggregate_only": True,
                "chat_enabled": True,
                "row_scope_mode": None,
            },
            {
                "role_key": "it_head",
                "display_name": "IT Head",
                "allowed_domains": list(ALL_DOMAINS),
                "aggregate_only": False,
                "chat_enabled": False,
                "row_scope_mode": None,
            },
            {
                "role_key": "faculty",
                "display_name": "Faculty",
                "allowed_domains": ["academic", "hr", "department", "notices"],
                "aggregate_only": False,
                "chat_enabled": True,
                "row_scope_mode": "course_ids",
            },
            {
                "role_key": "student",
                "display_name": "Student",
                "allowed_domains": ["academic", "finance", "notices", "campus"],
                "aggregate_only": False,
                "chat_enabled": True,
                "row_scope_mode": "owner_id",
            },
            {
                "role_key": "dept_head",
                "display_name": "Department Head",
                "allowed_domains": ["academic", "department", "exam", "notices"],
                "aggregate_only": False,
                "chat_enabled": True,
                "row_scope_mode": "department_id",
            },
            {
                "role_key": "admin_staff",
                "display_name": "Admin Staff",
                "allowed_domains": [
                    "admissions",
                    "finance",
                    "hr",
                    "exam",
                    "campus",
                    "notices",
                ],
                "aggregate_only": False,
                "chat_enabled": True,
                "row_scope_mode": "admin_function",
            },
        ]

        for policy in default_policies:
            role_key = str(policy["role_key"])
            if role_key in existing_by_key:
                continue
            db.add(
                RolePolicy(
                    tenant_id=tenant_id,
                    role_key=role_key,
                    display_name=str(policy["display_name"]),
                    allowed_domains=list(policy["allowed_domains"]),
                    masked_fields=[],
                    aggregate_only=bool(policy["aggregate_only"]),
                    chat_enabled=bool(policy["chat_enabled"]),
                    row_scope_mode=policy["row_scope_mode"],
                    sensitive_domains=["finance", "hr"],
                    require_business_hours_for_sensitive=False,
                    business_hours_start=0,
                    business_hours_end=23,
                    require_trusted_device_for_sensitive=False,
                    require_mfa_for_sensitive=False,
                    is_active=True,
                )
            )

    def _ensure_default_domain_keywords(self, db: Session, tenant_id: str) -> None:
        existing_rows = db.scalars(
            select(DomainKeyword).where(DomainKeyword.tenant_id == tenant_id)
        ).all()
        existing_domains = {row.domain for row in existing_rows}
        for domain, keywords in DEFAULT_DOMAIN_KEYWORDS.items():
            if domain in existing_domains:
                continue
            db.add(
                DomainKeyword(
                    tenant_id=tenant_id,
                    domain=domain,
                    keywords=list(keywords),
                    is_active=True,
                )
            )

    def _ensure_default_data_sources(self, db: Session, tenant_id: str) -> None:
        existing_rows = db.scalars(
            select(DataSource).where(DataSource.tenant_id == tenant_id)
        ).all()
        existing_names = {row.name for row in existing_rows}

        for source in DEFAULT_DATA_SOURCES:
            name = str(source["name"])
            if name in existing_names:
                continue

            db.add(
                DataSource(
                    tenant_id=tenant_id,
                    name=name,
                    source_type=source["source_type"],
                    config_encrypted=self._encode_source_config(source["config"]),
                    department_scope=list(source["department_scope"]),
                    status=source["status"],
                )
            )

    def _ensure_default_intent_definitions(self, db: Session, tenant_id: str) -> None:
        existing_rows = db.scalars(
            select(IntentDefinition).where(IntentDefinition.tenant_id == tenant_id)
        ).all()
        existing_by_name = {row.intent_name: row for row in existing_rows}
        existing_names = set(existing_by_name.keys())

        default_personas = [
            PersonaType.student.value,
            PersonaType.faculty.value,
            PersonaType.dept_head.value,
            PersonaType.admin_staff.value,
            PersonaType.executive.value,
        ]

        for item in DEFAULT_INTENT_DEFINITIONS:
            intent_name = str(item["intent_name"])
            row = existing_by_name.get(intent_name)
            if row is None:
                row = IntentDefinition(
                    tenant_id=tenant_id,
                    intent_name=intent_name,
                    domain=str(item["domain"]),
                    entity_type=str(item["entity_type"]),
                )

            row.domain = str(item["domain"])
            row.entity_type = str(item["entity_type"])
            row.slot_keys = list(item["slot_keys"])
            row.keywords = list(item["keywords"])
            row.persona_types = list(item["persona_types"])
            row.requires_aggregation = bool(item["requires_aggregation"])
            row.is_default = bool(item["is_default"])
            row.priority = int(item["priority"])
            row.is_active = True
            db.add(row)

            existing_by_name[intent_name] = row
            existing_names.add(intent_name)

        for domain in ALL_DOMAINS:
            overview_name = f"{domain}_overview"
            if overview_name not in existing_names:
                db.add(
                    IntentDefinition(
                        tenant_id=tenant_id,
                        intent_name=overview_name,
                        domain=domain,
                        entity_type="records",
                        slot_keys=["record_count", "status_summary"],
                        keywords=[domain, "summary", "overview", "status"],
                        persona_types=default_personas,
                        requires_aggregation=True,
                        is_default=True,
                        priority=100,
                        is_active=True,
                    )
                )
                existing_names.add(overview_name)

            list_name = f"{domain}_list"
            if list_name not in existing_names:
                db.add(
                    IntentDefinition(
                        tenant_id=tenant_id,
                        intent_name=list_name,
                        domain=domain,
                        entity_type="records",
                        slot_keys=["record_name", "record_value"],
                        keywords=[domain, "list", "show", "details"],
                        persona_types=default_personas,
                        requires_aggregation=False,
                        is_default=False,
                        priority=140,
                        is_active=True,
                    )
                )
                existing_names.add(list_name)

    def _ensure_default_intent_detection_keywords(
        self,
        db: Session,
        tenant_id: str,
    ) -> None:
        existing_rows = db.scalars(
            select(IntentDetectionKeyword).where(
                IntentDetectionKeyword.tenant_id == tenant_id
            )
        ).all()
        existing_keys = {
            (row.intent_name, row.keyword_type, row.keyword) for row in existing_rows
        }

        for item in DEFAULT_INTENT_DETECTION_KEYWORDS:
            key = (
                str(item["intent"]),
                str(item["keyword_type"]),
                str(item["keyword"]),
            )
            if key in existing_keys:
                continue
            db.add(
                IntentDetectionKeyword(
                    tenant_id=tenant_id,
                    intent_name=key[0],
                    keyword_type=key[1],
                    keyword=key[2],
                    priority=100,
                    is_active=True,
                )
            )
            existing_keys.add(key)

    def _resolve_primary_claim_source(
        self,
        db: Session,
        tenant_id: str,
    ) -> DataSource | None:
        rows = db.scalars(
            select(DataSource).where(DataSource.tenant_id == tenant_id)
        ).all()
        if not rows:
            return None

        preferred = [
            row
            for row in rows
            if row.status == DataSourceStatus.connected
            and row.source_type in {DataSourceType.ipeds_claims, DataSourceType.mock_claims}
        ]
        if preferred:
            return preferred[0]

        connected = [row for row in rows if row.status == DataSourceStatus.connected]
        if connected:
            return connected[0]

        return rows[0]

    def _ensure_default_domain_source_bindings(self, db: Session, tenant_id: str) -> None:
        source = self._resolve_primary_claim_source(db, tenant_id)
        if source is None:
            return

        existing_rows = db.scalars(
            select(DomainSourceBinding).where(DomainSourceBinding.tenant_id == tenant_id)
        ).all()
        existing_by_domain = {row.domain: row for row in existing_rows}

        for domain in ALL_DOMAINS:
            row = existing_by_domain.get(domain)
            if row is None:
                db.add(
                    DomainSourceBinding(
                        tenant_id=tenant_id,
                        domain=domain,
                        source_type=source.source_type,
                        data_source_id=source.id,
                        is_active=True,
                    )
                )
                continue

            row.source_type = source.source_type
            row.data_source_id = source.id
            row.is_active = True
            db.add(row)

    def _claim_alias_token(self, token: str, used_tokens: set[str]) -> str:
        if token not in used_tokens:
            used_tokens.add(token)
            return token

        suffix = 2
        while True:
            suffix_text = f"_{suffix}"
            candidate = f"{token[: 50 - len(suffix_text)]}{suffix_text}"
            if candidate not in used_tokens:
                used_tokens.add(candidate)
                return candidate
            suffix += 1

    def _ensure_default_schema_fields(self, db: Session, tenant_id: str) -> None:
        source = self._resolve_primary_claim_source(db, tenant_id)
        if source is None:
            return

        existing_rows = db.scalars(
            select(SchemaField).where(
                SchemaField.tenant_id == tenant_id,
                SchemaField.data_source_id == source.id,
            )
        ).all()
        existing_by_key = {
            (row.real_table.lower(), row.real_column.lower()): row for row in existing_rows
        }
        used_tokens = {
            token
            for token in db.scalars(
                select(SchemaField.alias_token).where(SchemaField.tenant_id == tenant_id)
            ).all()
            if token
        }

        for field in DEFAULT_CLAIM_SCHEMA_FIELDS:
            real_table = str(field["real_table"])
            real_column = str(field["real_column"])
            key = (real_table.lower(), real_column.lower())
            existing = existing_by_key.get(key)

            if existing is not None:
                if not existing.alias_token:
                    existing.alias_token = self._claim_alias_token(
                        str(field["alias_token"]),
                        used_tokens,
                    )
                    db.add(existing)
                continue

            alias_token = self._claim_alias_token(
                str(field["alias_token"]),
                used_tokens,
            )
            db.add(
                SchemaField(
                    tenant_id=tenant_id,
                    data_source_id=source.id,
                    real_table=real_table,
                    real_column=real_column,
                    alias_token=alias_token,
                    display_name=str(field["display_name"]),
                    data_type=str(field["data_type"]),
                    visibility=field["visibility"],
                    pii_flag=bool(field["pii_flag"]),
                    masked_for_personas=list(field["masked_for_personas"]),
                )
            )

    def _ensure_default_tenant_runtime(self, db: Session, tenant_id: str) -> None:
        self._ensure_default_role_policies(db, tenant_id)
        self._ensure_default_domain_keywords(db, tenant_id)
        self._ensure_default_intent_definitions(db, tenant_id)
        self._ensure_default_data_sources(db, tenant_id)
        self._ensure_default_intent_detection_keywords(db, tenant_id)
        self._ensure_default_domain_source_bindings(db, tenant_id)
        self._ensure_default_schema_fields(db, tenant_id)

    def bootstrap_tenant_runtime(self, db: Session, tenant_id: str) -> None:
        self._ensure_default_tenant_runtime(db, tenant_id)

    def _provision_dev_identity(self, db: Session, email: str) -> None:
        if not self._dev_auto_provision_enabled() or "@" not in email:
            return

        domain = email.split("@", 1)[1].strip().lower()
        local_name = email.split("@", 1)[0].strip()
        if not domain or not local_name:
            return

        tenant = db.scalar(
            select(Tenant).where(
                Tenant.domain == domain,
                Tenant.status == TenantStatus.active,
            )
        )
        if tenant is None:
            if not bool(self.settings.dev_auto_create_tenant_on_login):
                return
            subdomain = self._next_available_subdomain(
                db,
                self._slugify_subdomain(domain.split(".", 1)[0]),
            )
            tenant = Tenant(
                name=domain.split(".", 1)[0].replace("-", " ").title() or "Tenant",
                domain=domain,
                subdomain=subdomain,
                status=TenantStatus.active,
            )
            db.add(tenant)
            db.flush()

        needs_runtime_bootstrap = False
        # Preserve explicit tenant runtime config once it exists.
        if tenant is not None:
            has_role_policy = (
                db.scalar(select(RolePolicy.id).where(RolePolicy.tenant_id == tenant.id))
                is not None
            )
            has_domain_keywords = (
                db.scalar(
                    select(DomainKeyword.id).where(DomainKeyword.tenant_id == tenant.id)
                )
                is not None
            )
            has_intent_definitions = (
                db.scalar(
                    select(IntentDefinition.id).where(IntentDefinition.tenant_id == tenant.id)
                )
                is not None
            )
            needs_runtime_bootstrap = not (
                has_role_policy and has_domain_keywords and has_intent_definitions
            )

            if needs_runtime_bootstrap:
                self._ensure_default_tenant_runtime(db, tenant.id)
            else:
                has_data_sources = (
                    db.scalar(select(DataSource.id).where(DataSource.tenant_id == tenant.id))
                    is not None
                )
                if not has_data_sources:
                    self._ensure_default_data_sources(db, tenant.id)

                has_detection_keywords = (
                    db.scalar(
                        select(IntentDetectionKeyword.id).where(
                            IntentDetectionKeyword.tenant_id == tenant.id
                        )
                    )
                    is not None
                )
                if not has_detection_keywords:
                    self._ensure_default_intent_detection_keywords(db, tenant.id)

                has_domain_bindings = (
                    db.scalar(
                        select(DomainSourceBinding.id).where(
                            DomainSourceBinding.tenant_id == tenant.id
                        )
                    )
                    is not None
                )
                if not has_domain_bindings:
                    self._ensure_default_domain_source_bindings(db, tenant.id)

                has_schema_fields = (
                    db.scalar(
                        select(SchemaField.id).where(SchemaField.tenant_id == tenant.id)
                    )
                    is not None
                )
                if not has_schema_fields:
                    self._ensure_default_schema_fields(db, tenant.id)

        user = db.scalar(
            select(User).where(
                User.tenant_id == tenant.id,
                User.email == email,
                User.status == UserStatus.active,
            )
        )
        if user is None:
            persona = self._infer_persona_from_email(email)
            admin_function = (
                self._infer_admin_function_from_email(email)
                if persona == PersonaType.admin_staff
                else None
            )
            department = "general" if persona == PersonaType.dept_head else None
            course_ids = ["COURSE-INTRO-001"] if persona == PersonaType.faculty else []

            db.add(
                User(
                    tenant_id=tenant.id,
                    email=email,
                    name=local_name.replace(".", " ").title() or "User",
                    persona_type=persona,
                    department=department,
                    external_id=self._derive_external_id(email),
                    admin_function=admin_function,
                    course_ids=course_ids,
                    masked_fields=[],
                    status=UserStatus.active,
                )
            )

        db.commit()

    def resolve_tenant(self, db: Session, email: str) -> Tenant:
        if "@" not in email:
            raise AuthenticationError(
                message="Invalid identity email", code="IDENTITY_EMAIL_INVALID"
            )

        domain = email.split("@", 1)[1].lower()
        tenant = db.scalar(
            select(Tenant).where(
                Tenant.domain == domain, Tenant.status == TenantStatus.active
            )
        )
        if not tenant:
            raise AuthenticationError(
                message="Email domain is not onboarded", code="UNKNOWN_TENANT"
            )
        return tenant

    def resolve_user(self, db: Session, tenant_id: str, email: str) -> User:
        user = db.scalar(
            select(User).where(
                User.tenant_id == tenant_id,
                User.email == email,
                User.status == UserStatus.active,
            )
        )
        if not user:
            raise AuthenticationError(
                message="User is not provisioned for this tenant", code="USER_NOT_FOUND"
            )
        return user

    def _persona_row_scope_mode(self, persona: PersonaType) -> str | None:
        if persona == PersonaType.student:
            return "owner_id"
        if persona == PersonaType.faculty:
            return "course_ids"
        if persona == PersonaType.dept_head:
            return "department_id"
        if persona == PersonaType.admin_staff:
            return "admin_function"
        return None

    def _role_key_candidates(
        self, persona: PersonaType, admin_function: str | None
    ) -> list[str]:
        candidates: list[str] = []
        persona_key = persona.value
        admin_key = (admin_function or "").strip().lower()

        if persona == PersonaType.admin_staff and admin_key:
            candidates.append(f"admin_staff:{admin_key}")
            if admin_key == "finance":
                candidates.append("finance_dept")
            elif admin_key == "exam":
                candidates.append("examination_head")

        candidates.append(persona_key)

        if persona == PersonaType.dept_head:
            candidates.append("hod")
        if persona == PersonaType.it_head:
            candidates.append("it_admin")

        unique_candidates: list[str] = []
        for item in candidates:
            if item and item not in unique_candidates:
                unique_candidates.append(item)
        return unique_candidates

    def _serialize_role_policy(self, policy: RolePolicy) -> dict[str, Any]:
        start = policy.business_hours_start
        end = policy.business_hours_end
        if start < 0 or start > 23:
            start = 9
        if end < 0 or end > 23:
            end = 19
        if end < start:
            end = start

        return {
            "allowed_domains": list(policy.allowed_domains or []),
            "masked_fields": list(policy.masked_fields or []),
            "aggregate_only": bool(policy.aggregate_only),
            "chat_enabled": bool(policy.chat_enabled),
            "row_scope_mode": policy.row_scope_mode,
            "sensitive_domains": list(policy.sensitive_domains or ["finance", "hr"]),
            "require_business_hours_for_sensitive": bool(
                policy.require_business_hours_for_sensitive
            ),
            "business_hours_start": start,
            "business_hours_end": end,
            "require_trusted_device_for_sensitive": bool(
                policy.require_trusted_device_for_sensitive
            ),
            "require_mfa_for_sensitive": bool(policy.require_mfa_for_sensitive),
        }

    def _resolve_role_policy(
        self,
        db: Session,
        tenant_id: str,
        persona: PersonaType,
        admin_function: str | None,
    ) -> tuple[str, dict[str, Any]]:
        candidates = self._role_key_candidates(persona, admin_function)

        if not candidates:
            raise AuthenticationError(
                message="Role policy is not configured for this user role",
                code="ROLE_POLICY_NOT_CONFIGURED",
            )

        rows = db.scalars(
            select(RolePolicy).where(
                RolePolicy.tenant_id == tenant_id,
                RolePolicy.role_key.in_(candidates),
                RolePolicy.is_active.is_(True),
            )
        ).all()
        by_role = {row.role_key: row for row in rows}
        for role_key in candidates:
            policy = by_role.get(role_key)
            if policy is not None:
                return role_key, self._serialize_role_policy(policy)

        raise AuthenticationError(
            message="Role policy is not configured for this user role",
            code="ROLE_POLICY_NOT_CONFIGURED",
        )

    def _row_scope_filters(self, user: User, row_scope_mode: str | None) -> dict[str, Any]:
        if row_scope_mode == "owner_id":
            return {"owner_id": user.external_id}
        if row_scope_mode == "course_ids":
            return {"course_ids": list(user.course_ids or [])}
        if row_scope_mode == "department_id":
            return {"department_id": user.department}
        if row_scope_mode == "admin_function":
            return {"admin_function": user.admin_function}
        return {}

    def build_scope_context(
        self,
        user: User,
        tenant: Tenant,
        session_id: str,
        session_ip: str | None,
        device_trusted: bool,
        mfa_verified: bool,
        db: Session,
    ) -> ScopeContext:
        role_key, role_policy = self._resolve_role_policy(
            db=db,
            tenant_id=tenant.id,
            persona=user.persona_type,
            admin_function=user.admin_function,
        )
        allowed_domains = role_policy["allowed_domains"]
        denied_domains = [
            domain
            for domain in ALL_DOMAINS
            if all(domain not in allowed for allowed in allowed_domains)
        ]
        row_scope_mode = role_policy.get("row_scope_mode") or self._persona_row_scope_mode(
            user.persona_type
        )
        masked_fields = sorted(
            set(
                list(user.masked_fields or []) + list(role_policy["masked_fields"])
            )
        )

        return ScopeContext(
            tenant_id=tenant.id,
            user_id=user.id,
            email=user.email,
            name=user.name,
            persona_type=user.persona_type.value,
            department=user.department,
            external_id=user.external_id,
            admin_function=user.admin_function,
            role_key=role_key,
            course_ids=user.course_ids or [],
            row_scope_mode=row_scope_mode,
            row_scope_filters=self._row_scope_filters(user, row_scope_mode),
            allowed_domains=allowed_domains,
            denied_domains=denied_domains,
            masked_fields=masked_fields,
            aggregate_only=bool(role_policy["aggregate_only"]),
            own_id=user.external_id,
            chat_enabled=bool(role_policy["chat_enabled"]),
            sensitive_domains=list(role_policy["sensitive_domains"]),
            require_business_hours_for_sensitive=bool(
                role_policy["require_business_hours_for_sensitive"]
            ),
            business_hours_start=int(role_policy["business_hours_start"]),
            business_hours_end=int(role_policy["business_hours_end"]),
            require_trusted_device_for_sensitive=bool(
                role_policy["require_trusted_device_for_sensitive"]
            ),
            require_mfa_for_sensitive=bool(role_policy["require_mfa_for_sensitive"]),
            session_id=session_id,
            session_ip=session_ip,
            device_trusted=device_trusted,
            mfa_verified=mfa_verified,
        )

    def _authenticate_identity(
        self,
        db: Session,
        identity: GoogleIdentity,
        session_ip: str | None,
        device_trusted: bool,
        mfa_verified: bool | None,
    ) -> tuple[str, User, ScopeContext]:
        self._provision_dev_identity(db, identity.email)
        tenant = self.resolve_tenant(db, identity.email)
        user = self.resolve_user(db, tenant.id, identity.email)
        effective_mfa_verified = self._effective_mfa_verified(user, mfa_verified)

        session_id = str(uuid.uuid4())
        scope = self.build_scope_context(
            user=user,
            tenant=tenant,
            session_id=session_id,
            session_ip=session_ip,
            device_trusted=device_trusted,
            mfa_verified=effective_mfa_verified,
            db=db,
        )

        payload = {
            "sub": user.id,
            "tenant_id": tenant.id,
            "email": user.email,
            "name": user.name,
            "persona_type": user.persona_type.value,
            "department": user.department,
            "external_id": user.external_id,
            "admin_function": user.admin_function,
            "role_key": scope.role_key,
            "course_ids": user.course_ids or [],
            "row_scope_mode": scope.row_scope_mode,
            "row_scope_filters": scope.row_scope_filters,
            "allowed_domains": scope.allowed_domains,
            "denied_domains": scope.denied_domains,
            "masked_fields": scope.masked_fields,
            "aggregate_only": scope.aggregate_only,
            "chat_enabled": scope.chat_enabled,
            "sensitive_domains": scope.sensitive_domains,
            "require_business_hours_for_sensitive": scope.require_business_hours_for_sensitive,
            "business_hours_start": scope.business_hours_start,
            "business_hours_end": scope.business_hours_end,
            "require_trusted_device_for_sensitive": scope.require_trusted_device_for_sensitive,
            "require_mfa_for_sensitive": scope.require_mfa_for_sensitive,
            "session_id": session_id,
            "session_ip": scope.session_ip,
            "device_trusted": scope.device_trusted,
            "mfa_verified": scope.mfa_verified,
            "jti": str(uuid.uuid4()),
        }
        token = create_access_token(payload)
        return token, user, scope

    def authenticate_google(
        self,
        db: Session,
        google_token: str,
        session_ip: str | None = None,
        device_trusted: bool = True,
        mfa_verified: bool | None = None,
    ) -> tuple[str, User, ScopeContext]:
        identity = self.verify_google_token(google_token)
        return self._authenticate_identity(
            db=db,
            identity=identity,
            session_ip=session_ip,
            device_trusted=device_trusted,
            mfa_verified=mfa_verified,
        )

    def authenticate_oidc(
        self,
        db: Session,
        id_token: str,
        session_ip: str | None = None,
        device_trusted: bool = True,
        mfa_verified: bool | None = None,
    ) -> tuple[str, User, ScopeContext]:
        identity = self.verify_oidc_token(id_token)
        return self._authenticate_identity(
            db=db,
            identity=identity,
            session_ip=session_ip,
            device_trusted=device_trusted,
            mfa_verified=mfa_verified,
        )


identity_service = IdentityService()
