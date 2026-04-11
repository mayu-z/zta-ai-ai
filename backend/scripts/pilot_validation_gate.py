from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_REQUIRED_ARTIFACTS = [
    "ZTA_AI_FINAL_PRODUCT_PRODUCTION_PLAN.md",
    "docs/PLAN_ALIGNMENT.md",
    "docs/incident-response-playbook.md",
    "DEPLOYMENT_GUIDE.md",
    "backend/scripts/performance_load_gate.py",
    "backend/scripts/performance_regression_baseline.json",
    ".github/workflows/ci.yaml",
]


@dataclass(slots=True)
class PilotThresholds:
    min_feature_adoption_percent: float
    max_security_incidents: int
    max_policy_violations: int
    max_support_request_rate_percent: float
    max_compliance_findings_critical: int
    max_compliance_findings_medium: int
    require_customer_recommendation: bool
    max_interactive_p95_latency_ms: float
    max_peak_error_rate_percent: float


@dataclass(slots=True)
class ArtifactPreflight:
    overall_status: str
    checks: list[dict[str, Any]]
    missing_artifacts: list[str]


@dataclass(slots=True)
class EvidenceEvaluation:
    overall_status: str
    checks: list[dict[str, Any]]
    errors: list[str]


def _safe_float(value: Any, *, field_name: str) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    raise RuntimeError(f"Field '{field_name}' must be numeric")


def _safe_int(value: Any, *, field_name: str) -> int:
    if isinstance(value, bool):
        raise RuntimeError(f"Field '{field_name}' must be an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    raise RuntimeError(f"Field '{field_name}' must be an integer")


def _safe_bool(value: Any, *, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "ready", "production-ready"}:
            return True
        if normalized in {"0", "false", "no", "n", "not-ready", "not_ready"}:
            return False
    raise RuntimeError(f"Field '{field_name}' must be a boolean")


def _resolve_path(repo_root: Path, target: str) -> Path:
    candidate = Path(target)
    if candidate.is_absolute():
        return candidate

    repo_relative = repo_root / candidate
    if repo_relative.exists():
        return repo_relative

    backend_relative = repo_root / "backend" / candidate
    if backend_relative.exists():
        return backend_relative

    # Support common backend-local script paths like "scripts/...".
    if candidate.parts and candidate.parts[0] == "scripts":
        return backend_relative

    return repo_relative


def run_artifact_preflight(*, repo_root: Path, required_artifacts: list[str]) -> ArtifactPreflight:
    checks: list[dict[str, Any]] = []
    missing_artifacts: list[str] = []

    for artifact in required_artifacts:
        resolved_path = _resolve_path(repo_root, artifact)
        exists = resolved_path.is_file()
        checks.append(
            {
                "artifact": artifact,
                "resolved_path": str(resolved_path),
                "exists": exists,
                "met": exists,
            }
        )
        if not exists:
            missing_artifacts.append(artifact)

    overall_status = "pass" if not missing_artifacts else "fail"
    return ArtifactPreflight(
        overall_status=overall_status,
        checks=checks,
        missing_artifacts=missing_artifacts,
    )


def _build_check(
    *,
    code: str,
    description: str,
    expected: str,
    actual: Any,
    met: bool,
) -> dict[str, Any]:
    return {
        "code": code,
        "description": description,
        "expected": expected,
        "actual": actual,
        "met": met,
    }


def _required_field(payload: dict[str, Any], field_name: str) -> Any:
    if field_name not in payload:
        raise RuntimeError(f"Missing required field '{field_name}'")
    return payload[field_name]


def evaluate_pilot_evidence(
    *,
    payload: dict[str, Any],
    thresholds: PilotThresholds,
    require_performance_metrics: bool,
) -> EvidenceEvaluation:
    checks: list[dict[str, Any]] = []
    errors: list[str] = []

    try:
        feature_adoption = _safe_float(
            _required_field(payload, "feature_adoption_percent"),
            field_name="feature_adoption_percent",
        )
        security_incidents = _safe_int(
            _required_field(payload, "security_incidents"),
            field_name="security_incidents",
        )
        policy_violations = _safe_int(
            _required_field(payload, "policy_violations"),
            field_name="policy_violations",
        )
        support_request_rate = _safe_float(
            _required_field(payload, "support_request_rate_percent"),
            field_name="support_request_rate_percent",
        )
        compliance_findings_critical = _safe_int(
            _required_field(payload, "compliance_findings_critical"),
            field_name="compliance_findings_critical",
        )
        compliance_findings_medium = _safe_int(
            _required_field(payload, "compliance_findings_medium"),
            field_name="compliance_findings_medium",
        )
        customer_recommendation = _safe_bool(
            _required_field(payload, "customer_recommendation_ready"),
            field_name="customer_recommendation_ready",
        )
    except RuntimeError as exc:
        errors.append(str(exc))
        return EvidenceEvaluation(overall_status="fail", checks=checks, errors=errors)

    checks.append(
        _build_check(
            code="FEATURE_ADOPTION",
            description="Feature adoption at pilot target users",
            expected=f">= {thresholds.min_feature_adoption_percent:.2f}%",
            actual=feature_adoption,
            met=feature_adoption >= thresholds.min_feature_adoption_percent,
        )
    )
    checks.append(
        _build_check(
            code="SECURITY_INCIDENTS",
            description="Security incidents during pilot",
            expected=f"<= {thresholds.max_security_incidents}",
            actual=security_incidents,
            met=security_incidents <= thresholds.max_security_incidents,
        )
    )
    checks.append(
        _build_check(
            code="POLICY_VIOLATIONS",
            description="Policy violations during pilot",
            expected=f"<= {thresholds.max_policy_violations}",
            actual=policy_violations,
            met=policy_violations <= thresholds.max_policy_violations,
        )
    )
    checks.append(
        _build_check(
            code="SUPPORT_REQUEST_RATE",
            description="Pilot support request rate",
            expected=f"<= {thresholds.max_support_request_rate_percent:.2f}%",
            actual=support_request_rate,
            met=support_request_rate <= thresholds.max_support_request_rate_percent,
        )
    )
    checks.append(
        _build_check(
            code="COMPLIANCE_FINDINGS_CRITICAL",
            description="Critical compliance findings in audit",
            expected=f"<= {thresholds.max_compliance_findings_critical}",
            actual=compliance_findings_critical,
            met=compliance_findings_critical <= thresholds.max_compliance_findings_critical,
        )
    )
    checks.append(
        _build_check(
            code="COMPLIANCE_FINDINGS_MEDIUM",
            description="Medium compliance findings in audit",
            expected=f"<= {thresholds.max_compliance_findings_medium}",
            actual=compliance_findings_medium,
            met=compliance_findings_medium <= thresholds.max_compliance_findings_medium,
        )
    )

    if thresholds.require_customer_recommendation:
        checks.append(
            _build_check(
                code="CUSTOMER_RECOMMENDATION",
                description="Customer recommendation indicates production readiness",
                expected="true",
                actual=customer_recommendation,
                met=customer_recommendation,
            )
        )

    interactive_p95_raw = payload.get("interactive_p95_latency_ms")
    peak_error_rate_raw = payload.get("peak_error_rate_percent")

    if interactive_p95_raw is None:
        if require_performance_metrics:
            checks.append(
                _build_check(
                    code="INTERACTIVE_P95",
                    description="Interactive P95 latency during pilot",
                    expected=f"<= {thresholds.max_interactive_p95_latency_ms:.2f} ms",
                    actual=None,
                    met=False,
                )
            )
    else:
        try:
            interactive_p95 = _safe_float(
                interactive_p95_raw,
                field_name="interactive_p95_latency_ms",
            )
            checks.append(
                _build_check(
                    code="INTERACTIVE_P95",
                    description="Interactive P95 latency during pilot",
                    expected=f"<= {thresholds.max_interactive_p95_latency_ms:.2f} ms",
                    actual=interactive_p95,
                    met=interactive_p95 <= thresholds.max_interactive_p95_latency_ms,
                )
            )
        except RuntimeError as exc:
            errors.append(str(exc))

    if peak_error_rate_raw is None:
        if require_performance_metrics:
            checks.append(
                _build_check(
                    code="PEAK_ERROR_RATE",
                    description="Peak-load error rate during pilot",
                    expected=f"<= {thresholds.max_peak_error_rate_percent:.3f}%",
                    actual=None,
                    met=False,
                )
            )
    else:
        try:
            peak_error_rate = _safe_float(
                peak_error_rate_raw,
                field_name="peak_error_rate_percent",
            )
            checks.append(
                _build_check(
                    code="PEAK_ERROR_RATE",
                    description="Peak-load error rate during pilot",
                    expected=f"<= {thresholds.max_peak_error_rate_percent:.3f}%",
                    actual=peak_error_rate,
                    met=peak_error_rate <= thresholds.max_peak_error_rate_percent,
                )
            )
        except RuntimeError as exc:
            errors.append(str(exc))

    overall_status = "pass" if not errors and all(item["met"] for item in checks) else "fail"
    return EvidenceEvaluation(overall_status=overall_status, checks=checks, errors=errors)


def build_evidence_template() -> dict[str, Any]:
    return {
        "feature_adoption_percent": 90.0,
        "security_incidents": 0,
        "policy_violations": 0,
        "support_request_rate_percent": 4.0,
        "compliance_findings_critical": 0,
        "compliance_findings_medium": 2,
        "customer_recommendation_ready": True,
        "interactive_p95_latency_ms": 980.0,
        "peak_error_rate_percent": 0.08,
        "notes": "Replace with measured pilot environment values.",
    }


def write_evidence_template(destination_file: Path) -> str:
    destination_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "phase": "phase_10_pilot_validation",
        "evidence": build_evidence_template(),
    }
    destination_file.write_text(
        f"{json.dumps(payload, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )
    return str(destination_file)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run Phase 10 pilot validation gate checks "
            "(artifact preflight + optional evidence evaluation)."
        )
    )
    parser.add_argument(
        "--repo-root",
        default=str(REPO_ROOT),
        help="Repository root path used to resolve required artifact paths.",
    )
    parser.add_argument(
        "--required-artifact",
        action="append",
        default=[],
        help="Additional artifact path required for preflight checks (repeatable).",
    )
    parser.add_argument(
        "--pilot-evidence-file",
        default="",
        help=(
            "Path to JSON evidence payload used for Phase 10 threshold evaluation. "
            "When omitted, evidence checks are skipped unless --require-evidence is set."
        ),
    )
    parser.add_argument(
        "--write-evidence-template-file",
        default="",
        help="Write a Phase 10 evidence template JSON file to this path.",
    )
    parser.add_argument(
        "--require-evidence",
        action="store_true",
        help="Fail the gate if no pilot evidence file is provided.",
    )
    parser.add_argument(
        "--require-performance-metrics",
        action="store_true",
        help=(
            "Require interactive_p95_latency_ms and peak_error_rate_percent fields in evidence."
        ),
    )
    parser.add_argument(
        "--min-feature-adoption-percent",
        default=90.0,
        type=float,
        help="Minimum pilot feature adoption rate percent.",
    )
    parser.add_argument(
        "--max-security-incidents",
        default=0,
        type=int,
        help="Maximum allowed security incidents during pilot.",
    )
    parser.add_argument(
        "--max-policy-violations",
        default=0,
        type=int,
        help="Maximum allowed policy violations during pilot.",
    )
    parser.add_argument(
        "--max-support-request-rate-percent",
        default=5.0,
        type=float,
        help="Maximum support request rate percent during pilot.",
    )
    parser.add_argument(
        "--max-compliance-findings-critical",
        default=0,
        type=int,
        help="Maximum allowed critical compliance findings.",
    )
    parser.add_argument(
        "--max-compliance-findings-medium",
        default=2,
        type=int,
        help="Maximum allowed medium compliance findings.",
    )
    parser.add_argument(
        "--max-interactive-p95-latency-ms",
        default=1000.0,
        type=float,
        help="Maximum allowed interactive P95 latency in ms when provided.",
    )
    parser.add_argument(
        "--max-peak-error-rate-percent",
        default=0.1,
        type=float,
        help="Maximum allowed peak error rate percent when provided.",
    )
    parser.add_argument(
        "--allow-missing-customer-recommendation",
        action="store_true",
        help="Do not fail when customer recommendation is false.",
    )
    return parser.parse_args()


def _run_gate(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()

    required_artifacts = list(dict.fromkeys(DEFAULT_REQUIRED_ARTIFACTS + list(args.required_artifact)))
    preflight = run_artifact_preflight(
        repo_root=repo_root,
        required_artifacts=required_artifacts,
    )

    written_template_file = ""
    if str(args.write_evidence_template_file).strip():
        destination = _resolve_path(repo_root, str(args.write_evidence_template_file)).resolve()
        written_template_file = write_evidence_template(destination)

    thresholds = PilotThresholds(
        min_feature_adoption_percent=max(0.0, float(args.min_feature_adoption_percent)),
        max_security_incidents=max(0, int(args.max_security_incidents)),
        max_policy_violations=max(0, int(args.max_policy_violations)),
        max_support_request_rate_percent=max(0.0, float(args.max_support_request_rate_percent)),
        max_compliance_findings_critical=max(0, int(args.max_compliance_findings_critical)),
        max_compliance_findings_medium=max(0, int(args.max_compliance_findings_medium)),
        require_customer_recommendation=not bool(args.allow_missing_customer_recommendation),
        max_interactive_p95_latency_ms=max(0.0, float(args.max_interactive_p95_latency_ms)),
        max_peak_error_rate_percent=max(0.0, float(args.max_peak_error_rate_percent)),
    )

    evidence_status = "skipped"
    evidence_checks: list[dict[str, Any]] = []
    evidence_errors: list[str] = []
    evidence_source = ""

    if str(args.pilot_evidence_file).strip():
        evidence_path = _resolve_path(repo_root, str(args.pilot_evidence_file)).resolve()
        evidence_source = str(evidence_path)
        if not evidence_path.is_file():
            evidence_status = "fail"
            evidence_errors.append(f"Pilot evidence file not found: {evidence_path}")
        else:
            try:
                payload = json.loads(evidence_path.read_text(encoding="utf-8"))
                raw_evidence = payload.get("evidence", payload)
                if not isinstance(raw_evidence, dict):
                    raise RuntimeError("Pilot evidence must be a JSON object")

                evidence_result = evaluate_pilot_evidence(
                    payload=raw_evidence,
                    thresholds=thresholds,
                    require_performance_metrics=bool(args.require_performance_metrics),
                )
                evidence_status = evidence_result.overall_status
                evidence_checks = evidence_result.checks
                evidence_errors = evidence_result.errors
            except (RuntimeError, json.JSONDecodeError) as exc:
                evidence_status = "fail"
                evidence_errors.append(str(exc))
    elif bool(args.require_evidence):
        evidence_status = "fail"
        evidence_errors.append("Pilot evidence is required but --pilot-evidence-file was not provided")

    evidence_gate_passed = evidence_status == "pass" or (
        evidence_status == "skipped" and not bool(args.require_evidence)
    )
    overall_passed = preflight.overall_status == "pass" and evidence_gate_passed

    report = {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "phase": "phase_10_pilot_validation",
        "repo_root": str(repo_root),
        "overall_status": "pass" if overall_passed else "fail",
        "preflight": asdict(preflight),
        "evidence": {
            "required": bool(args.require_evidence),
            "provided": bool(str(args.pilot_evidence_file).strip()),
            "source_file": evidence_source,
            "require_performance_metrics": bool(args.require_performance_metrics),
            "thresholds": asdict(thresholds),
            "overall_status": evidence_status,
            "checks": evidence_checks,
            "errors": evidence_errors,
        },
        "written_evidence_template_file": written_template_file,
    }

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if overall_passed else 1


def main() -> int:
    args = _parse_args()
    return _run_gate(args)


if __name__ == "__main__":
    raise SystemExit(main())
