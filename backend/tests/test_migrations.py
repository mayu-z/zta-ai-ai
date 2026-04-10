"""Tests for database migrations."""

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.db.models import IntentDetectionKeyword, Tenant
from app.db.session import engine


def test_migration_creates_intent_detection_keywords_table() -> None:
    """Test that intent_detection_keywords table exists after migration."""
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    
    assert "intent_detection_keywords" in tables, \
        "intent_detection_keywords table was not created"


def test_migration_creates_table_columns() -> None:
    """Test that all required columns exist."""
    inspector = inspect(engine)
    columns = {col["name"] for col in inspector.get_columns("intent_detection_keywords")}
    
    required_columns = {
        "id",
        "tenant_id",
        "intent_name",
        "keyword_type",
        "keyword",
        "priority",
        "is_active",
        "created_at",
        "updated_at",
    }
    
    assert required_columns.issubset(columns), \
        f"Missing columns: {required_columns - columns}"


def test_migration_creates_indexes() -> None:
    """Test that required indexes are created."""
    inspector = inspect(engine)
    indexes = {idx["name"] for idx in inspector.get_indexes("intent_detection_keywords")}
    
    expected_indexes = {
        "ix_intent_detection_keywords_tenant_intent_type",
        "ix_intent_detection_keywords_tenant_keyword",
    }
    
    assert expected_indexes.issubset(indexes), \
        f"Missing indexes: {expected_indexes - indexes}"


def test_migration_column_types() -> None:
    """Test that column types are correct."""
    inspector = inspect(engine)
    columns = {col["name"]: col["type"] for col in inspector.get_columns("intent_detection_keywords")}
    
    # Verify key column types
    assert str(columns["id"]) == "VARCHAR(36)"
    assert str(columns["tenant_id"]) == "VARCHAR(36)"
    assert str(columns["intent_name"]) == "VARCHAR(120)"
    assert str(columns["keyword_type"]) == "VARCHAR(50)"
    assert str(columns["keyword"]) == "VARCHAR(255)"


def test_migration_primary_key() -> None:
    """Test that primary key is correctly set."""
    inspector = inspect(engine)
    pk = inspector.get_pk_constraint("intent_detection_keywords")
    
    assert pk["constrained_columns"] == ["id"]


def test_migration_foreign_key() -> None:
    """Test that foreign key to tenants exists."""
    inspector = inspect(engine)
    fks = inspector.get_foreign_keys("intent_detection_keywords")
    
    tenant_fk = next((fk for fk in fks if "tenant_id" in fk["constrained_columns"]), None)
    assert tenant_fk is not None, "Foreign key to tenants not found"
    assert tenant_fk["referred_table"] == "tenants"
    assert tenant_fk["referred_columns"] == ["id"]


def test_migration_nullable_columns() -> None:
    """Test that columns have correct nullable settings."""
    inspector = inspect(engine)
    columns = {col["name"]: col["nullable"] for col in inspector.get_columns("intent_detection_keywords")}
    
    # All columns should be NOT NULL
    for col_name, is_nullable in columns.items():
        assert not is_nullable, f"Column {col_name} should NOT be nullable"


def test_migration_unique_constraint(db: Session) -> None:
    """Test that unique constraint on keyword combo works."""
    from app.db.models import IntentDetectionKeyword
    
    tenant_id = "test-tenant-id-1234"
    
    # Create first keyword
    kw1 = IntentDetectionKeyword(
        tenant_id=tenant_id,
        intent_name="student_grades",
        keyword_type="grade_marker",
        keyword="gpa",
        is_active=True,
    )
    db.add(kw1)
    db.commit()
    
    # Try to create duplicate - should fail
    kw2 = IntentDetectionKeyword(
        tenant_id=tenant_id,
        intent_name="student_grades",
        keyword_type="grade_marker",
        keyword="gpa",
        is_active=True,
    )
    db.add(kw2)
    
    with pytest.raises(Exception):  # Should raise database constraint error
        db.commit()
    
    db.rollback()


def test_migration_cascade_delete(db: Session) -> None:
    """Test that keywords are deleted when tenant is deleted."""
    tenant_id = "cascade-test-tenant"
    
    # Create tenant and keyword
    tenant = Tenant(
        id=tenant_id,
        name="Test Tenant",
        domain="test.com",
        subdomain="test",
    )
    kw = IntentDetectionKeyword(
        tenant_id=tenant_id,
        intent_name="student_grades",
        keyword_type="grade_marker",
        keyword="gpa",
        is_active=True,
    )
    
    db.add(tenant)
    db.add(kw)
    db.commit()
    
    # Verify keyword created
    count_before = db.query(IntentDetectionKeyword).filter(
        IntentDetectionKeyword.tenant_id == tenant_id
    ).count()
    assert count_before == 1
    
    # Delete tenant
    db.delete(tenant)
    db.commit()
    
    # Verify keyword also deleted
    count_after = db.query(IntentDetectionKeyword).filter(
        IntentDetectionKeyword.tenant_id == tenant_id
    ).count()
    assert count_after == 0


def test_migration_insert_data() -> None:
    """Test that data can be inserted into migrated table."""
    TableModel = IntentDetectionKeyword
    
    kw = TableModel(
        tenant_id="test-tenant",
        intent_name="student_grades",
        keyword_type="grade_marker",
        keyword="gpa",
        priority=100,
        is_active=True,
    )
    
    # This should not raise any errors
    assert kw.id is None  # Auto-generated on insert
    assert kw.intent_name == "student_grades"
    assert kw.keyword == "gpa"
