"""Tests for intent extraction with database-driven detection keywords."""

import pytest

from app.interpreter.intent_extractor import extract_intent, IntentRule
from app.core.exceptions import ValidationError


def test_extract_intent_with_grade_markers_from_db() -> None:
    """Test that grade markers loaded from DB trigger student_grades intent."""
    # Create intent rules
    rules = (
        IntentRule(
            name="student_grades",
            domain="academic",
            entity_type="student_grades",
            slot_keys=("subject", "grade"),
            keywords=(),
            persona_types=("student",),
            is_default=False,
            priority=50,
        ),
        IntentRule(
            name="student_attendance",
            domain="academic",
            entity_type="student_attendance",
            slot_keys=("subject", "attendance"),
            keywords=("attendance", "present", "absent"),
            persona_types=("student",),
            is_default=True,
            priority=100,
        ),
    )
    
    # Simulate detection keywords loaded from DB
    detection_keywords = {
        "student_grades": {
            "grade_marker": ["gpa", "grade", "grades", "marks"],
        },
        "student_attendance": {
            "attendance_marker": ["attendance", "present", "absent"],
        },
    }

    prompt = "show me my gpa"
    interpreted = extract_intent(
        raw_prompt=prompt,
        sanitized_prompt=prompt,
        aliased_prompt=prompt,
        detected_domains=["academic"],
        persona_type="student",
        intent_rules=rules,
        detection_keywords=detection_keywords,
    )

    # Should select student_grades due to "gpa" grade marker
    assert interpreted.name == "student_grades"
    assert interpreted.domain == "academic"


def test_extract_intent_without_grade_markers() -> None:
    """Test fallback behavior when no grade markers match."""
    rules = (
        IntentRule(
            name="student_grades",
            domain="academic",
            entity_type="student_grades",
            slot_keys=("subject", "grade"),
            keywords=(),
            persona_types=("student",),
            is_default=False,
            priority=50,
        ),
        IntentRule(
            name="student_attendance",
            domain="academic",
            entity_type="student_attendance",
            slot_keys=("subject", "attendance"),
            keywords=("attendance", "present", "absent"),
            persona_types=("student",),
            is_default=True,
            priority=100,
        ),
    )
    
    detection_keywords = {
        "student_grades": {
            "grade_marker": ["gpa", "grade", "grades"],
        },
    }

    prompt = "show my attendance"
    interpreted = extract_intent(
        raw_prompt=prompt,
        sanitized_prompt=prompt,
        aliased_prompt=prompt,
        detected_domains=["academic"],
        persona_type="student",
        intent_rules=rules,
        detection_keywords=detection_keywords,
    )

    # Should use default rule for student_attendance
    assert interpreted.name == "student_attendance"


def test_extract_intent_empty_detection_keywords() -> None:
    """Test that empty detection_keywords dict doesn't break extraction."""
    rules = (
        IntentRule(
            name="student_attendance",
            domain="academic",
            entity_type="student_attendance",
            slot_keys=("subject", "attendance"),
            keywords=("attendance",),
            persona_types=("student",),
            is_default=True,
            priority=100,
        ),
    )

    prompt = "show attendance"
    interpreted = extract_intent(
        raw_prompt=prompt,
        sanitized_prompt=prompt,
        aliased_prompt=prompt,
        detected_domains=["academic"],
        persona_type="student",
        intent_rules=rules,
        detection_keywords={},  # Empty detection keywords
    )

    # Should still work normally
    assert interpreted.name == "student_attendance"


def test_extract_intent_no_detection_keywords_parameter() -> None:
    """Test backward compatibility when detection_keywords not provided."""
    rules = (
        IntentRule(
            name="student_attendance",
            domain="academic",
            entity_type="student_attendance",
            slot_keys=("subject", "attendance"),
            keywords=("attendance",),
            persona_types=("student",),
            is_default=True,
            priority=100,
        ),
    )

    prompt = "show attendance"
    interpreted = extract_intent(
        raw_prompt=prompt,
        sanitized_prompt=prompt,
        aliased_prompt=prompt,
        detected_domains=["academic"],
        persona_type="student",
        intent_rules=rules,
        # detection_keywords not provided (None)
    )

    # Should work with default (empty) detection keywords
    assert interpreted.name == "student_attendance"


def test_extract_intent_non_student_ignores_grade_marker() -> None:
    """Test that non-student personas don't get grade marker override."""
    rules = (
        IntentRule(
            name="faculty_grades",
            domain="academic",
            entity_type="faculty_grades",
            slot_keys=("student", "grade"),
            keywords=("grade", "gpa"),
            persona_types=("faculty",),
            is_default=False,
            priority=50,
        ),
        IntentRule(
            name="faculty_attendance",
            domain="academic",
            entity_type="faculty_attendance",
            slot_keys=("student", "attendance"),
            keywords=("attendance",),
            persona_types=("faculty",),
            is_default=True,
            priority=100,
        ),
    )
    
    detection_keywords = {
        "student_grades": {
            "grade_marker": ["gpa", "grade"],
        },
    }

    prompt = "show gpa for students"
    interpreted = extract_intent(
        raw_prompt=prompt,
        sanitized_prompt=prompt,
        aliased_prompt=prompt,
        detected_domains=["academic"],
        persona_type="faculty",
        intent_rules=rules,
        detection_keywords=detection_keywords,
    )

    # Faculty persona should use keyword matching, not grade marker override
    # Should match faculty_grades by keyword
    assert interpreted.name == "faculty_grades"
    assert interpreted.persona_types == ("faculty",)


def test_extract_intent_raises_when_no_rules() -> None:
    """Test that extraction fails when no rules provided."""
    detection_keywords = {}

    prompt = "show grades"
    with pytest.raises(ValidationError, match="No intent rules"):
        extract_intent(
            raw_prompt=prompt,
            sanitized_prompt=prompt,
            aliased_prompt=prompt,
            detected_domains=["academic"],
            persona_type="student",
            intent_rules=None,  # No rules
            detection_keywords=detection_keywords,
        )


def test_extract_intent_preserves_filters() -> None:
    """Test that filters are correctly extracted during intent detection."""
    rules = (
        IntentRule(
            name="student_grades",
            domain="academic",
            entity_type="student_grades",
            slot_keys=("subject", "grade"),
            keywords=("grade",),
            persona_types=("student",),
            is_default=False,
            priority=50,
        ),
    )
    
    detection_keywords = {
        "student_grades": {
            "grade_marker": ["grade"],
        },
    }

    prompt = "show my grades for Q1"
    interpreted = extract_intent(
        raw_prompt=prompt,
        sanitized_prompt=prompt,
        aliased_prompt=prompt.lower(),
        detected_domains=["academic"],
        persona_type="student",
        intent_rules=rules,
        detection_keywords=detection_keywords,
    )

    # Should extract Q1 as quarter filter
    assert "quarter" in interpreted.filters
    assert interpreted.filters["quarter"] == "Q1"
