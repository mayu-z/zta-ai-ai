from __future__ import annotations

from pathlib import Path

from scripts import pilot_validation_gate as gate


def _thresholds() -> gate.PilotThresholds:
    return gate.PilotThresholds(
        min_feature_adoption_percent=90.0,
        max_security_incidents=0,
        max_policy_violations=0,
        max_support_request_rate_percent=5.0,
        max_compliance_findings_critical=0,
        max_compliance_findings_medium=2,
        require_customer_recommendation=True,
        max_interactive_p95_latency_ms=1000.0,
        max_peak_error_rate_percent=0.1,
    )


def test_run_artifact_preflight_flags_missing_artifacts(tmp_path: Path) -> None:
    (tmp_path / "present.md").write_text("ok\n", encoding="utf-8")

    result = gate.run_artifact_preflight(
        repo_root=tmp_path,
        required_artifacts=["present.md", "missing.md"],
    )

    assert result.overall_status == "fail"
    assert result.missing_artifacts == ["missing.md"]

    checks = {item["artifact"]: item for item in result.checks}
    assert checks["present.md"]["met"] is True
    assert checks["missing.md"]["met"] is False


def test_evaluate_pilot_evidence_passes_with_required_metrics() -> None:
    payload = {
        "feature_adoption_percent": 92.0,
        "security_incidents": 0,
        "policy_violations": 0,
        "support_request_rate_percent": 4.5,
        "compliance_findings_critical": 0,
        "compliance_findings_medium": 1,
        "customer_recommendation_ready": True,
        "interactive_p95_latency_ms": 940.0,
        "peak_error_rate_percent": 0.06,
    }

    result = gate.evaluate_pilot_evidence(
        payload=payload,
        thresholds=_thresholds(),
        require_performance_metrics=True,
    )

    assert result.errors == []
    assert result.overall_status == "pass"
    assert all(item["met"] for item in result.checks)


def test_evaluate_pilot_evidence_fails_when_feature_adoption_below_target() -> None:
    payload = {
        "feature_adoption_percent": 74.0,
        "security_incidents": 0,
        "policy_violations": 0,
        "support_request_rate_percent": 3.0,
        "compliance_findings_critical": 0,
        "compliance_findings_medium": 1,
        "customer_recommendation_ready": True,
        "interactive_p95_latency_ms": 900.0,
        "peak_error_rate_percent": 0.05,
    }

    result = gate.evaluate_pilot_evidence(
        payload=payload,
        thresholds=_thresholds(),
        require_performance_metrics=True,
    )

    assert result.overall_status == "fail"
    feature_checks = [item for item in result.checks if item["code"] == "FEATURE_ADOPTION"]
    assert len(feature_checks) == 1
    assert feature_checks[0]["met"] is False


def test_evaluate_pilot_evidence_requires_performance_metrics_when_enabled() -> None:
    payload = {
        "feature_adoption_percent": 93.0,
        "security_incidents": 0,
        "policy_violations": 0,
        "support_request_rate_percent": 4.2,
        "compliance_findings_critical": 0,
        "compliance_findings_medium": 1,
        "customer_recommendation_ready": True,
    }

    result = gate.evaluate_pilot_evidence(
        payload=payload,
        thresholds=_thresholds(),
        require_performance_metrics=True,
    )

    assert result.overall_status == "fail"
    interactive_checks = [item for item in result.checks if item["code"] == "INTERACTIVE_P95"]
    peak_checks = [item for item in result.checks if item["code"] == "PEAK_ERROR_RATE"]
    assert len(interactive_checks) == 1
    assert len(peak_checks) == 1
    assert interactive_checks[0]["met"] is False
    assert peak_checks[0]["met"] is False


def test_run_artifact_preflight_accepts_backend_relative_script_paths(
    tmp_path: Path,
) -> None:
    script_path = tmp_path / "backend" / "scripts" / "pilot.json"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text("{}\n", encoding="utf-8")

    result = gate.run_artifact_preflight(
        repo_root=tmp_path,
        required_artifacts=["scripts/pilot.json"],
    )

    assert result.overall_status == "pass"
    assert result.missing_artifacts == []
    assert result.checks[0]["exists"] is True
