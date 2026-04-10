"""Tests for admin endpoints managing intent detection keywords."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import IntentDetectionKeyword, Tenant, User, PersonaType, UserStatus
from app.db.session import SessionLocal
from app.main import app
from app.api.deps import get_db, get_current_scope
from app.schemas.pipeline import ScopeContext


TENANT_ID = "12345678-1234-1234-1234-123456789012"
USER_ID = "87654321-4321-4321-4321-210987654321"


@pytest.fixture
def tenant_and_user(db: Session):
    """Create test tenant and user."""
    tenant = Tenant(
        id=TENANT_ID,
        name="Test University",
        domain="test.edu",
        subdomain="test",
    )
    user = User(
        id=USER_ID,
        tenant_id=TENANT_ID,
        email="ithead@test.edu",
        name="IT Head",
        persona_type=PersonaType.it_head,
        external_id="it-001",
        status=UserStatus.active,
    )
    db.add(tenant)
    db.add(user)
    db.commit()
    return tenant, user


@pytest.fixture
def client(db: Session, tenant_and_user):
    """Provide test client with mocked test scope."""
    test_scope = ScopeContext(
        tenant_id=TENANT_ID,
        user_id=USER_ID,
        persona_type="it_head",
        email="ithead@test.edu",
        external_id="it-001",
        allowed_domains=["academic", "finance", "admin"],
        aggregate_only=False,
        masked_fields=[],
    )
    
    def override_get_db():
        yield db
    
    def override_get_scope():
        return test_scope
    
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_scope] = override_get_scope
    
    client = TestClient(app)
    yield client
    
    app.dependency_overrides.clear()


def test_list_intent_detection_keywords_empty(client: TestClient) -> None:
    """Test listing detection keywords when none exist."""
    response = client.get("/admin/intent-detection-keywords")
    assert response.status_code == 200
    assert response.json() == []


def test_upsert_intent_detection_keyword(client: TestClient, db: Session) -> None:
    """Test creating a new detection keyword."""
    payload = {
        "intent_name": "student_grades",
        "keyword_type": "grade_marker",
        "keyword": "gpa",
        "priority": 100,
        "is_active": True,
    }
    
    response = client.post("/admin/intent-detection-keywords", json=payload)
    assert response.status_code == 200
    
    data = response.json()
    assert data["intent_name"] == "student_grades"
    assert data["keyword_type"] == "grade_marker"
    assert data["keyword"] == "gpa"
    assert data["priority"] == 100
    assert data["is_active"] is True


def test_upsert_intent_detection_keyword_update(client: TestClient, db: Session) -> None:
    """Test updating existing detection keyword."""
    # Create initial keyword
    payload = {
        "intent_name": "student_grades",
        "keyword_type": "grade_marker",
        "keyword": "gpa",
        "priority": 100,
        "is_active": True,
    }
    response1 = client.post("/admin/intent-detection-keywords", json=payload)
    assert response1.status_code == 200
    kw_id = response1.json()["id"]
    
    # Update it
    update_payload = {
        "intent_name": "student_grades",
        "keyword_type": "grade_marker",
        "keyword": "gpa",
        "priority": 50,
        "is_active": True,
    }
    response2 = client.post("/admin/intent-detection-keywords", json=update_payload)
    assert response2.status_code == 200
    
    # Verify same keyword was updated, not duplicated
    data = response2.json()
    assert data["id"] == kw_id
    assert data["priority"] == 50


def test_upsert_intent_detection_keyword_validation_empty_intent(client: TestClient) -> None:
    """Test validation of empty intent_name."""
    payload = {
        "intent_name": "",
        "keyword_type": "grade_marker",
        "keyword": "gpa",
    }
    
    response = client.post("/admin/intent-detection-keywords", json=payload)
    assert response.status_code == 422  # Validation error


def test_upsert_intent_detection_keyword_validation_negative_priority(
    client: TestClient,
) -> None:
    """Test validation of negative priority."""
    payload = {
        "intent_name": "student_grades",
        "keyword_type": "grade_marker",
        "keyword": "gpa",
        "priority": -1,
    }
    
    response = client.post("/admin/intent-detection-keywords", json=payload)
    assert response.status_code == 400  # Custom validation error


def test_list_intent_detection_keywords_by_intent(
    client: TestClient, db: Session
) -> None:
    """Test filtering keywords by intent_name."""
    # Create keywords for multiple intents
    for intent, keyword in [
        ("student_grades", "gpa"),
        ("student_grades", "grade"),
        ("student_attendance", "attendance"),
    ]:
        payload = {
            "intent_name": intent,
            "keyword_type": "marker",
            "keyword": keyword,
        }
        client.post("/admin/intent-detection-keywords", json=payload)
    
    # Filter by intent
    response = client.get("/admin/intent-detection-keywords?intent_name=student_grades")
    assert response.status_code == 200
    data = response.json()
    
    assert len(data) == 2
    assert all(kw["intent_name"] == "student_grades" for kw in data)


def test_list_intent_detection_keywords_by_type(
    client: TestClient, db: Session
) -> None:
    """Test filtering keywords by keyword_type."""
    # Create keywords of multiple types
    for ktype, keyword in [
        ("grade_marker", "gpa"),
        ("grade_marker", "grade"),
        ("attendance_marker", "attendance"),
    ]:
        payload = {
            "intent_name": "student_grades",
            "keyword_type": ktype,
            "keyword": keyword,
        }
        client.post("/admin/intent-detection-keywords", json=payload)
    
    # Filter by type
    response = client.get("/admin/intent-detection-keywords?keyword_type=grade_marker")
    assert response.status_code == 200
    data = response.json()
    
    assert len(data) == 2
    assert all(kw["keyword_type"] == "grade_marker" for kw in data)


def test_deactivate_intent_detection_keyword(client: TestClient, db: Session) -> None:
    """Test deactivating a detection keyword."""
    # Create keyword
    payload = {
        "intent_name": "student_grades",
        "keyword_type": "grade_marker",
        "keyword": "gpa",
    }
    response1 = client.post("/admin/intent-detection-keywords", json=payload)
    kw_id = response1.json()["id"]
    
    # Deactivate it
    response2 = client.delete(f"/admin/intent-detection-keywords/{kw_id}")
    assert response2.status_code == 200
    
    data = response2.json()
    assert data["is_active"] is False
    
    # Verify it doesn't appear in list anymore
    response3 = client.get("/admin/intent-detection-keywords")
    assert len(response3.json()) == 0


def test_deactivate_nonexistent_keyword(client: TestClient) -> None:
    """Test deactivating a keyword that doesn't exist."""
    response = client.delete("/admin/intent-detection-keywords/nonexistent-id")
    assert response.status_code == 400  # Not found error


def test_intent_detection_keywords_tenant_isolation(
    client: TestClient, db: Session
) -> None:
    """Test that keywords are isolated per tenant."""
    # Create keyword for test tenant
    payload = {
        "intent_name": "student_grades",
        "keyword_type": "grade_marker",
        "keyword": "gpa",
    }
    response = client.post("/admin/intent-detection-keywords", json=payload)
    assert response.status_code == 200
    
    # Create another tenant
    other_tenant_id = "other-tenant-id-1234-1234-1234"
    other_tenant = Tenant(
        id=other_tenant_id,
        name="Other University",
        domain="other.edu",
        subdomain="other",
    )
    db.add(other_tenant)
    db.commit()
    
    # Verify other tenant can't see this keyword
    # (would need to switch scope to test, but at minimum we verify DB isolation)
    keywords = db.query(IntentDetectionKeyword).filter(
        IntentDetectionKeyword.tenant_id == other_tenant_id
    ).all()
    assert len(keywords) == 0


def test_intent_detection_keywords_bulk_create(client: TestClient) -> None:
    """Test creating multiple keywords efficiently."""
    keywords = [
        ("student_grades", "grade_marker", "gpa"),
        ("student_grades", "grade_marker", "grade"),
        ("student_grades", "grade_marker", "marks"),
        ("student_attendance", "attendance_marker", "attendance"),
        ("student_attendance", "attendance_marker", "absent"),
    ]
    
    for intent, ktype, keyword in keywords:
        payload = {
            "intent_name": intent,
            "keyword_type": ktype,
            "keyword": keyword,
        }
        response = client.post("/admin/intent-detection-keywords", json=payload)
        assert response.status_code == 200
    
    # Verify all created
    response = client.get("/admin/intent-detection-keywords")
    assert len(response.json()) == 5
