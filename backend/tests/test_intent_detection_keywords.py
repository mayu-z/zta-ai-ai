"""Tests for intent detection keywords database functionality."""

import pytest
from sqlalchemy.orm import Session

from app.db.models import IntentDetectionKeyword, Tenant, IntentDefinition
from app.interpreter.registry import load_intent_detection_keywords
from app.db.session import SessionLocal
from app.core.exceptions import ValidationError


TENANT_ID = "12345678-1234-1234-1234-123456789012"


@pytest.fixture
def db_session() -> Session:
    """Provide a database session for testing."""
    db = SessionLocal()
    db.begin()
    yield db
    db.rollback()
    db.close()


def test_load_intent_detection_keywords_empty(db_session: Session) -> None:
    """Test loading detection keywords when none exist returns empty dict."""
    result = load_intent_detection_keywords(db_session, TENANT_ID)
    assert isinstance(result, dict)
    assert len(result) == 0


def test_load_intent_detection_keywords_single_keyword(db_session: Session) -> None:
    """Test loading a single detection keyword."""
    # Create a detection keyword directly
    keyword = IntentDetectionKeyword(
        tenant_id=TENANT_ID,
        intent_name="student_grades",
        keyword_type="grade_marker",
        keyword="gpa",
        is_active=True,
    )
    db_session.add(keyword)
    db_session.commit()

    result = load_intent_detection_keywords(db_session, TENANT_ID)
    
    assert "student_grades" in result
    assert "grade_marker" in result["student_grades"]
    assert "gpa" in result["student_grades"]["grade_marker"]


def test_load_intent_detection_keywords_multiple_keywords(db_session: Session) -> None:
    """Test loading multiple keywords for same intent."""
    keywords = [
        ("student_grades", "grade_marker", "gpa"),
        ("student_grades", "grade_marker", "grade"),
        ("student_grades", "grade_marker", "marks"),
    ]
    
    for intent_name, keyword_type, keyword in keywords:
        kw = IntentDetectionKeyword(
            tenant_id=TENANT_ID,
            intent_name=intent_name,
            keyword_type=keyword_type,
            keyword=keyword,
            is_active=True,
        )
        db_session.add(kw)
    
    db_session.commit()
    result = load_intent_detection_keywords(db_session, TENANT_ID)
    
    assert len(result["student_grades"]["grade_marker"]) == 3
    assert set(result["student_grades"]["grade_marker"]) == {"gpa", "grade", "marks"}


def test_load_intent_detection_keywords_multiple_types(db_session: Session) -> None:
    """Test loading multiple keyword types for same intent."""
    keywords = [
        ("student_grades", "grade_marker", "gpa"),
        ("student_grades", "grade_marker", "grade"),
        ("student_grades", "subject_marker", "subject"),
        ("student_grades", "subject_marker", "course"),
    ]
    
    for intent_name, keyword_type, keyword in keywords:
        kw = IntentDetectionKeyword(
            tenant_id=TENANT_ID,
            intent_name=intent_name,
            keyword_type=keyword_type,
            keyword=keyword,
            is_active=True,
        )
        db_session.add(kw)
    
    db_session.commit()
    result = load_intent_detection_keywords(db_session, TENANT_ID)
    
    assert len(result["student_grades"]) == 2
    assert "grade_marker" in result["student_grades"]
    assert "subject_marker" in result["student_grades"]


def test_load_intent_detection_keywords_multiple_intents(db_session: Session) -> None:
    """Test loading keywords for multiple intents."""
    keywords = [
        ("student_grades", "grade_marker", "gpa"),
        ("student_attendance", "attendance_marker", "attendance"),
        ("student_fee", "fee_marker", "fee"),
    ]
    
    for intent_name, keyword_type, keyword in keywords:
        kw = IntentDetectionKeyword(
            tenant_id=TENANT_ID,
            intent_name=intent_name,
            keyword_type=keyword_type,
            keyword=keyword,
            is_active=True,
        )
        db_session.add(kw)
    
    db_session.commit()
    result = load_intent_detection_keywords(db_session, TENANT_ID)
    
    assert len(result) == 3
    assert "student_grades" in result
    assert "student_attendance" in result
    assert "student_fee" in result


def test_load_intent_detection_keywords_ignores_inactive(db_session: Session) -> None:
    """Test that inactive keywords are not loaded."""
    active = IntentDetectionKeyword(
        tenant_id=TENANT_ID,
        intent_name="student_grades",
        keyword_type="grade_marker",
        keyword="gpa",
        is_active=True,
    )
    inactive = IntentDetectionKeyword(
        tenant_id=TENANT_ID,
        intent_name="student_grades",
        keyword_type="grade_marker",
        keyword="marks",
        is_active=False,
    )
    db_session.add(active)
    db_session.add(inactive)
    db_session.commit()

    result = load_intent_detection_keywords(db_session, TENANT_ID)
    
    assert "gpa" in result["student_grades"]["grade_marker"]
    assert "marks" not in result["student_grades"]["grade_marker"]


def test_load_intent_detection_keywords_tenant_isolation(db_session: Session) -> None:
    """Test that keywords from different tenants are not mixed."""
    tenant_a = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    tenant_b = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    
    kw_a = IntentDetectionKeyword(
        tenant_id=tenant_a,
        intent_name="student_grades",
        keyword_type="grade_marker",
        keyword="gpa",
        is_active=True,
    )
    kw_b = IntentDetectionKeyword(
        tenant_id=tenant_b,
        intent_name="student_grades",
        keyword_type="grade_marker",
        keyword="marks",
        is_active=True,
    )
    db_session.add(kw_a)
    db_session.add(kw_b)
    db_session.commit()

    result_a = load_intent_detection_keywords(db_session, tenant_a)
    result_b = load_intent_detection_keywords(db_session, tenant_b)
    
    assert "gpa" in result_a["student_grades"]["grade_marker"]
    assert "gpa" not in result_b.get("student_grades", {}).get("grade_marker", [])
    
    assert "marks" in result_b["student_grades"]["grade_marker"]
    assert "marks" not in result_a.get("student_grades", {}).get("grade_marker", [])
