from __future__ import annotations

from app.services.action_registry import (
    ACTION_TEMPLATE_REGISTRY,
    action_registry_health,
    get_action_template,
    list_action_templates,
    validate_action_registry,
)


def test_action_registry_has_12_templates() -> None:
    assert len(ACTION_TEMPLATE_REGISTRY) == 12


def test_action_registry_validation_has_no_errors() -> None:
    assert validate_action_registry() == []


def test_action_registry_health_reports_healthy() -> None:
    health = action_registry_health()

    assert health["healthy"] is True
    assert health["template_count"] == 12
    assert health["errors"] == []


def test_action_registry_contains_expected_template_ids() -> None:
    expected = {
        "DSAR_EXECUTE",
        "ERASURE_EXECUTE",
        "ESCALATE_TO_MANAGER",
        "BULK_SOFT_DELETE",
        "FIELD_MASKING_UPDATE",
        "CONSENT_WITHDRAWAL",
        "INCIDENT_RESPONSE",
        "POLICY_UPDATE",
        "CONNECTOR_REFRESH",
        "AUDIT_EXPORT",
        "SEGMENT_ACTIVATION",
        "SCHEDULED_REPORTING",
    }

    assert set(ACTION_TEMPLATE_REGISTRY.keys()) == expected


def test_get_action_template_returns_none_for_unknown() -> None:
    assert get_action_template("UNKNOWN_ACTION") is None


def test_list_action_templates_returns_structured_payload() -> None:
    templates = list_action_templates()

    assert len(templates) == 12
    first = templates[0]
    assert "action_id" in first
    assert "trigger" in first
    assert "required_permissions" in first
    assert "execution_steps" in first
