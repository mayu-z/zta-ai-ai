from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Callable, Awaitable

import httpx

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_zta.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6399/0")
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6399/1")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6399/2")
os.environ.setdefault(
    "JWT_SECRET_KEY",
    "test-secret-key-that-is-at-least-thirty-two-chars",
)
os.environ.setdefault("AUTH_PROVIDER", "mock_google")
os.environ.setdefault("USE_MOCK_GOOGLE_OAUTH", "true")
os.environ.setdefault("SLM_PROVIDER", "simulator")

from app.api.deps import get_scope_from_token
from app.db.models import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.schemas.pipeline import ScopeContext
from app.services.pipeline import pipeline_service
from scripts.ipeds_import import seed_ipeds_claims


DEFAULT_ENDPOINT = "/admin/system/fleet-health?lookback_hours=24"
DEFAULT_LOGIN_TOKEN = "mock:ithead@local.test"
DEFAULT_QUERY_LOGIN_TOKEN = "mock:executive@local.test"
DEFAULT_QUERY_TEXT = "Give me campus aggregate KPI summary."


@dataclass(slots=True)
class ScenarioConfig:
    name: str
    concurrent_users: int
    requests_per_user: int
    p95_target_ms: float
    p99_target_ms: float
    max_error_rate_percent: float


@dataclass(slots=True)
class ScenarioResult:
    name: str
    total_requests: int
    concurrent_users: int
    inflight_limit: int
    requests_per_user: int
    successful_requests: int
    failed_requests: int
    error_rate_percent: float
    p95_latency_ms: float | None
    p99_latency_ms: float | None
    avg_latency_ms: float | None
    checks: list[dict[str, object]]
    passed: bool


@dataclass(slots=True)
class RecoveryCheckResult:
    timeout_seconds: float
    check_interval_seconds: float
    attempts: int
    recovered_in_seconds: float | None
    passed: bool
    probe_scenario: dict[str, object]
    last_probe: dict[str, object] | None


@dataclass(slots=True)
class QueryPathResult:
    enabled: bool
    login_token: str
    query_text: str
    scenarios: list[dict[str, object]]
    overall_status: str


@dataclass(slots=True)
class RegressionCheckResult:
    enabled: bool
    baseline_file: str
    max_p95_regression_percent: float
    max_p99_regression_percent: float
    max_error_rate_delta_percent: float
    missing_scenario_baselines: list[str]
    checks: list[dict[str, object]]
    overall_status: str


def _percentile(values: list[float], percentile: int) -> float | None:
    if not values:
        return None

    sorted_values = sorted(values)
    if len(sorted_values) == 1:
        return round(sorted_values[0], 3)

    rank = (percentile / 100) * (len(sorted_values) - 1)
    lower_index = int(rank)
    upper_index = min(lower_index + 1, len(sorted_values) - 1)
    weight = rank - lower_index

    lower = sorted_values[lower_index]
    upper = sorted_values[upper_index]
    return round(lower + (upper - lower) * weight, 3)


def _safe_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _metric_snapshot(result: ScenarioResult | dict[str, object]) -> dict[str, float | None]:
    if isinstance(result, ScenarioResult):
        return {
            "p95_latency_ms": result.p95_latency_ms,
            "p99_latency_ms": result.p99_latency_ms,
            "error_rate_percent": result.error_rate_percent,
        }

    return {
        "p95_latency_ms": _safe_float(result.get("p95_latency_ms")),
        "p99_latency_ms": _safe_float(result.get("p99_latency_ms")),
        "error_rate_percent": _safe_float(result.get("error_rate_percent")),
    }


def _collect_current_metrics(
    *,
    scenario_results: list[ScenarioResult],
    recovery_result: RecoveryCheckResult,
    query_path_result: QueryPathResult,
) -> dict[str, dict[str, float | None]]:
    metrics: dict[str, dict[str, float | None]] = {
        item.name: _metric_snapshot(item)
        for item in scenario_results
    }

    if recovery_result.last_probe:
        probe_name = str(recovery_result.last_probe.get("name") or "")
        if probe_name:
            metrics[probe_name] = _metric_snapshot(recovery_result.last_probe)

    for item in query_path_result.scenarios:
        scenario_name = str(item.get("name") or "")
        if scenario_name:
            metrics[scenario_name] = _metric_snapshot(item)

    return metrics


def _load_regression_baseline(
    baseline_file: str,
) -> dict[str, dict[str, float | None]]:
    baseline_path = Path(baseline_file)
    if not baseline_path.is_absolute():
        baseline_path = ROOT_DIR / baseline_path

    if not baseline_path.is_file():
        raise RuntimeError(f"Regression baseline file not found: {baseline_path}")

    payload = json.loads(baseline_path.read_text(encoding="utf-8"))
    scenarios = payload.get("scenarios")
    if not isinstance(scenarios, dict):
        raise RuntimeError(
            "Regression baseline file must contain a top-level 'scenarios' object"
        )

    normalized: dict[str, dict[str, float | None]] = {}
    for raw_name, raw_metrics in scenarios.items():
        scenario_name = str(raw_name).strip()
        if not scenario_name:
            continue
        if not isinstance(raw_metrics, dict):
            continue
        normalized[scenario_name] = {
            "p95_latency_ms": _safe_float(raw_metrics.get("p95_latency_ms")),
            "p99_latency_ms": _safe_float(raw_metrics.get("p99_latency_ms")),
            "error_rate_percent": _safe_float(raw_metrics.get("error_rate_percent")),
        }

    if not normalized:
        raise RuntimeError("Regression baseline file does not include any scenarios")

    return normalized


def _write_regression_baseline(
    *,
    destination_file: str,
    metrics: dict[str, dict[str, float | None]],
) -> str:
    output_path = Path(destination_file)
    if not output_path.is_absolute():
        output_path = ROOT_DIR / output_path

    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "scenarios": metrics,
    }
    output_path.write_text(
        f"{json.dumps(payload, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )
    return str(output_path)


def _regression_percent(
    *,
    baseline_value: float | None,
    actual_value: float | None,
) -> float | None:
    if baseline_value is None or actual_value is None:
        return None
    if baseline_value <= 0:
        return None
    return round(((actual_value - baseline_value) / baseline_value) * 100, 3)


def _run_regression_check(
    *,
    baseline_file: str,
    baseline_metrics: dict[str, dict[str, float | None]],
    current_metrics: dict[str, dict[str, float | None]],
    max_p95_regression_percent: float,
    max_p99_regression_percent: float,
    max_error_rate_delta_percent: float,
) -> RegressionCheckResult:
    checks: list[dict[str, object]] = []
    missing_scenario_baselines: list[str] = []

    for scenario_name, actual in current_metrics.items():
        baseline = baseline_metrics.get(scenario_name)
        if baseline is None:
            missing_scenario_baselines.append(scenario_name)
            continue

        baseline_p95 = _safe_float(baseline.get("p95_latency_ms"))
        actual_p95 = _safe_float(actual.get("p95_latency_ms"))
        p95_regression = _regression_percent(
            baseline_value=baseline_p95,
            actual_value=actual_p95,
        )
        checks.append(
            {
                "scenario": scenario_name,
                "metric": "P95_REGRESSION",
                "baseline_ms": baseline_p95,
                "actual_ms": actual_p95,
                "regression_percent": p95_regression,
                "max_regression_percent": max_p95_regression_percent,
                "met": p95_regression is None or p95_regression <= max_p95_regression_percent,
            }
        )

        baseline_p99 = _safe_float(baseline.get("p99_latency_ms"))
        actual_p99 = _safe_float(actual.get("p99_latency_ms"))
        p99_regression = _regression_percent(
            baseline_value=baseline_p99,
            actual_value=actual_p99,
        )
        checks.append(
            {
                "scenario": scenario_name,
                "metric": "P99_REGRESSION",
                "baseline_ms": baseline_p99,
                "actual_ms": actual_p99,
                "regression_percent": p99_regression,
                "max_regression_percent": max_p99_regression_percent,
                "met": p99_regression is None or p99_regression <= max_p99_regression_percent,
            }
        )

        baseline_error = _safe_float(baseline.get("error_rate_percent")) or 0.0
        actual_error = _safe_float(actual.get("error_rate_percent")) or 0.0
        error_delta = round(actual_error - baseline_error, 3)
        checks.append(
            {
                "scenario": scenario_name,
                "metric": "ERROR_RATE_DELTA",
                "baseline_percent": baseline_error,
                "actual_percent": actual_error,
                "delta_percent": error_delta,
                "max_delta_percent": max_error_rate_delta_percent,
                "met": error_delta <= max_error_rate_delta_percent,
            }
        )

    overall_pass = (
        not missing_scenario_baselines
        and all(bool(item.get("met")) for item in checks)
    )
    return RegressionCheckResult(
        enabled=True,
        baseline_file=baseline_file,
        max_p95_regression_percent=max_p95_regression_percent,
        max_p99_regression_percent=max_p99_regression_percent,
        max_error_rate_delta_percent=max_error_rate_delta_percent,
        missing_scenario_baselines=sorted(missing_scenario_baselines),
        checks=checks,
        overall_status="pass" if overall_pass else "fail",
    )


async def _authenticate(
    client: httpx.AsyncClient,
    *,
    login_token: str,
) -> dict[str, str]:
    response = await client.post("/auth/google", json={"google_token": login_token})
    if response.status_code != 200:
        raise RuntimeError(
            f"Authentication failed with status={response.status_code}, body={response.text}"
        )

    jwt_token = response.json().get("jwt")
    if not jwt_token:
        raise RuntimeError("Authentication response did not include JWT token")

    return {"Authorization": f"Bearer {jwt_token}"}


async def _execute_request(
    client: httpx.AsyncClient,
    *,
    endpoint: str,
    headers: dict[str, str],
) -> tuple[int, float]:
    started = perf_counter()
    response = await client.get(endpoint, headers=headers)
    latency_ms = (perf_counter() - started) * 1000
    return response.status_code, latency_ms


def _build_checks(
    *,
    scenario: ScenarioConfig,
    p95_latency_ms: float | None,
    p99_latency_ms: float | None,
    error_rate_percent: float,
    failed_requests: int,
) -> list[dict[str, object]]:
    return [
        {
            "code": "P95_LATENCY",
            "target_ms": scenario.p95_target_ms,
            "actual_ms": p95_latency_ms,
            "met": p95_latency_ms is not None and p95_latency_ms <= scenario.p95_target_ms,
        },
        {
            "code": "P99_LATENCY",
            "target_ms": scenario.p99_target_ms,
            "actual_ms": p99_latency_ms,
            "met": p99_latency_ms is not None and p99_latency_ms <= scenario.p99_target_ms,
        },
        {
            "code": "ERROR_RATE",
            "target_percent": scenario.max_error_rate_percent,
            "actual_percent": error_rate_percent,
            "met": error_rate_percent <= scenario.max_error_rate_percent,
        },
        {
            "code": "NO_FAILED_REQUESTS",
            "target_count": 0,
            "actual_count": failed_requests,
            "met": failed_requests == 0,
        },
    ]


async def _run_generic_scenario(
    *,
    scenario: ScenarioConfig,
    max_inflight_requests: int,
    request_runner: Callable[[], Awaitable[tuple[int, float]]],
) -> ScenarioResult:
    total_requests = scenario.concurrent_users * scenario.requests_per_user
    inflight_limit = max(1, min(scenario.concurrent_users, max_inflight_requests))
    semaphore = asyncio.Semaphore(inflight_limit)

    statuses: list[int] = []
    latencies: list[float] = []

    async def worker() -> None:
        try:
            async with semaphore:
                status_code, latency_ms = await request_runner()
        except Exception:  # noqa: BLE001
            status_code = 599
            latency_ms = max(scenario.p99_target_ms * 2, 1.0)
        statuses.append(status_code)
        latencies.append(latency_ms)

    await asyncio.gather(*(worker() for _ in range(total_requests)))

    successful_requests = sum(1 for value in statuses if 200 <= value < 300)
    failed_requests = total_requests - successful_requests
    error_rate_percent = (
        round((failed_requests / total_requests) * 100, 3)
        if total_requests > 0
        else 0.0
    )

    p95_latency_ms = _percentile(latencies, 95)
    p99_latency_ms = _percentile(latencies, 99)
    avg_latency_ms = (
        round(sum(latencies) / len(latencies), 3)
        if latencies
        else None
    )

    checks = _build_checks(
        scenario=scenario,
        p95_latency_ms=p95_latency_ms,
        p99_latency_ms=p99_latency_ms,
        error_rate_percent=error_rate_percent,
        failed_requests=failed_requests,
    )
    passed = all(bool(item["met"]) for item in checks)

    return ScenarioResult(
        name=scenario.name,
        total_requests=total_requests,
        concurrent_users=scenario.concurrent_users,
        inflight_limit=inflight_limit,
        requests_per_user=scenario.requests_per_user,
        successful_requests=successful_requests,
        failed_requests=failed_requests,
        error_rate_percent=error_rate_percent,
        p95_latency_ms=p95_latency_ms,
        p99_latency_ms=p99_latency_ms,
        avg_latency_ms=avg_latency_ms,
        checks=checks,
        passed=passed,
    )


async def _run_scenario(
    client: httpx.AsyncClient,
    *,
    endpoint: str,
    headers: dict[str, str],
    scenario: ScenarioConfig,
    max_inflight_requests: int,
) -> ScenarioResult:
    async def request_runner() -> tuple[int, float]:
        return await _execute_request(
            client,
            endpoint=endpoint,
            headers=headers,
        )

    return await _run_generic_scenario(
        scenario=scenario,
        max_inflight_requests=max_inflight_requests,
        request_runner=request_runner,
    )


def _resolve_scope_for_token(token: str) -> ScopeContext:
    db = SessionLocal()
    try:
        return get_scope_from_token(db=db, token=token)
    finally:
        db.close()


def _run_pipeline_once(scope: ScopeContext, query_text: str) -> int:
    db = SessionLocal()
    try:
        result = pipeline_service.process_query(db=db, scope=scope, query_text=query_text)
        return 200 if not result.was_blocked else 403
    finally:
        db.close()


async def _run_query_path_scenarios(
    *,
    query_login_token: str,
    query_text: str,
    query_warmup_requests: int,
    query_normal_concurrency: int,
    query_normal_requests_per_user: int,
    query_peak_concurrency: int,
    query_peak_requests_per_user: int,
    max_inflight_requests: int,
) -> QueryPathResult:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        timeout=30.0,
    ) as client:
        headers = await _authenticate(client, login_token=query_login_token)

    auth_header = headers.get("Authorization", "")
    token = auth_header.split(" ", 1)[1] if " " in auth_header else ""
    if not token:
        raise RuntimeError("Failed to resolve JWT token for query-path load scenarios")

    scope = _resolve_scope_for_token(token)

    warmup_requests = max(0, int(query_warmup_requests))
    for _ in range(warmup_requests):
        status_code = await asyncio.to_thread(_run_pipeline_once, scope, query_text)
        if status_code != 200:
            raise RuntimeError(
                "Query-path warm-up request failed; verify token scope and query text"
            )

    scenarios = [
        ScenarioConfig(
            name="query_path_normal_load",
            concurrent_users=max(1, int(query_normal_concurrency)),
            requests_per_user=max(1, int(query_normal_requests_per_user)),
            p95_target_ms=1000.0,
            p99_target_ms=2000.0,
            max_error_rate_percent=0.1,
        ),
        ScenarioConfig(
            name="query_path_peak_load",
            concurrent_users=max(1, int(query_peak_concurrency)),
            requests_per_user=max(1, int(query_peak_requests_per_user)),
            p95_target_ms=1500.0,
            p99_target_ms=2500.0,
            max_error_rate_percent=0.1,
        ),
    ]

    async def request_runner() -> tuple[int, float]:
        started = perf_counter()
        status_code = await asyncio.to_thread(_run_pipeline_once, scope, query_text)
        latency_ms = (perf_counter() - started) * 1000
        return status_code, latency_ms

    scenario_results: list[ScenarioResult] = []
    for scenario in scenarios:
        scenario_results.append(
            await _run_generic_scenario(
                scenario=scenario,
                max_inflight_requests=max_inflight_requests,
                request_runner=request_runner,
            )
        )

    overall_pass = all(item.passed for item in scenario_results)
    return QueryPathResult(
        enabled=True,
        login_token=query_login_token,
        query_text=query_text,
        scenarios=[asdict(item) for item in scenario_results],
        overall_status="pass" if overall_pass else "fail",
    )


async def _run_recovery_check(
    client: httpx.AsyncClient,
    *,
    endpoint: str,
    headers: dict[str, str],
    probe_scenario: ScenarioConfig,
    max_inflight_requests: int,
    timeout_seconds: float,
    check_interval_seconds: float,
) -> RecoveryCheckResult:
    normalized_timeout = max(float(timeout_seconds), 1.0)
    normalized_interval = max(float(check_interval_seconds), 0.1)
    started = perf_counter()
    attempts = 0
    last_probe: ScenarioResult | None = None

    while True:
        attempts += 1
        last_probe = await _run_scenario(
            client,
            endpoint=endpoint,
            headers=headers,
            scenario=probe_scenario,
            max_inflight_requests=max_inflight_requests,
        )
        elapsed = perf_counter() - started
        if last_probe.passed:
            return RecoveryCheckResult(
                timeout_seconds=round(normalized_timeout, 3),
                check_interval_seconds=round(normalized_interval, 3),
                attempts=attempts,
                recovered_in_seconds=round(elapsed, 3),
                passed=True,
                probe_scenario=asdict(probe_scenario),
                last_probe=asdict(last_probe),
            )

        if elapsed >= normalized_timeout:
            return RecoveryCheckResult(
                timeout_seconds=round(normalized_timeout, 3),
                check_interval_seconds=round(normalized_interval, 3),
                attempts=attempts,
                recovered_in_seconds=None,
                passed=False,
                probe_scenario=asdict(probe_scenario),
                last_probe=asdict(last_probe),
            )

        await asyncio.sleep(normalized_interval)


def _bootstrap_runtime_dataset(profile: str) -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        seed_ipeds_claims(db, profile=profile)
        db.commit()
    finally:
        db.close()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Phase 9 API performance/load gate checks."
    )
    parser.add_argument(
        "--dataset-profile",
        "--seed-profile",
        dest="dataset_profile",
        default="test",
        help="Synthetic dataset profile used before running load checks (default: test)",
    )
    parser.add_argument(
        "--endpoint",
        default=DEFAULT_ENDPOINT,
        help="Authenticated endpoint to load test",
    )
    parser.add_argument(
        "--login-token",
        default=DEFAULT_LOGIN_TOKEN,
        help="Mock Google login token for auth bootstrap",
    )
    parser.add_argument(
        "--timeout-seconds",
        default=30.0,
        type=float,
        help="HTTP request timeout in seconds",
    )
    parser.add_argument(
        "--normal-concurrency",
        default=100,
        type=int,
        help="Concurrent users for normal-load scenario",
    )
    parser.add_argument(
        "--normal-requests-per-user",
        default=2,
        type=int,
        help="Requests per user for normal-load scenario",
    )
    parser.add_argument(
        "--peak-concurrency",
        default=200,
        type=int,
        help="Concurrent users for peak-load scenario",
    )
    parser.add_argument(
        "--peak-requests-per-user",
        default=2,
        type=int,
        help="Requests per user for peak-load scenario",
    )
    parser.add_argument(
        "--burst-concurrency",
        default=500,
        type=int,
        help="Concurrent users for burst-spike scenario",
    )
    parser.add_argument(
        "--burst-requests-per-user",
        default=1,
        type=int,
        help="Requests per user for burst-spike scenario",
    )
    parser.add_argument(
        "--burst-p95-target-ms",
        default=5000.0,
        type=float,
        help="P95 latency threshold for burst-spike scenario",
    )
    parser.add_argument(
        "--burst-p99-target-ms",
        default=8000.0,
        type=float,
        help="P99 latency threshold for burst-spike scenario",
    )
    parser.add_argument(
        "--recovery-concurrency",
        default=100,
        type=int,
        help="Concurrent users used while probing post-burst recovery",
    )
    parser.add_argument(
        "--recovery-requests-per-user",
        default=1,
        type=int,
        help="Requests per user used while probing post-burst recovery",
    )
    parser.add_argument(
        "--recovery-p95-target-ms",
        default=1000.0,
        type=float,
        help="Recovery target for P95 latency",
    )
    parser.add_argument(
        "--recovery-p99-target-ms",
        default=2000.0,
        type=float,
        help="Recovery target for P99 latency",
    )
    parser.add_argument(
        "--recovery-max-error-rate-percent",
        default=0.1,
        type=float,
        help="Recovery target for error rate percent",
    )
    parser.add_argument(
        "--recovery-timeout-seconds",
        default=300.0,
        type=float,
        help="Maximum seconds allowed to recover to normal thresholds after burst",
    )
    parser.add_argument(
        "--recovery-check-interval-seconds",
        default=10.0,
        type=float,
        help="Interval between post-burst recovery probes",
    )
    parser.add_argument(
        "--max-inflight-requests",
        default=10,
        type=int,
        help=(
            "Maximum in-flight requests at a time. "
            "Use a conservative value for SQLite-based CI environments."
        ),
    )
    parser.add_argument(
        "--skip-query-path",
        action="store_true",
        help="Skip interactive query-path scenarios.",
    )
    parser.add_argument(
        "--query-login-token",
        default=DEFAULT_QUERY_LOGIN_TOKEN,
        help="Mock Google login token for interactive query-path scenarios.",
    )
    parser.add_argument(
        "--query-text",
        default=DEFAULT_QUERY_TEXT,
        help="Query text used by interactive query-path load scenarios.",
    )
    parser.add_argument(
        "--query-warmup-requests",
        default=10,
        type=int,
        help="Number of warm-up requests before query-path scenario timing starts.",
    )
    parser.add_argument(
        "--query-normal-concurrency",
        default=100,
        type=int,
        help="Concurrent users for query-path normal-load scenario.",
    )
    parser.add_argument(
        "--query-normal-requests-per-user",
        default=1,
        type=int,
        help="Requests per user for query-path normal-load scenario.",
    )
    parser.add_argument(
        "--query-peak-concurrency",
        default=200,
        type=int,
        help="Concurrent users for query-path peak-load scenario.",
    )
    parser.add_argument(
        "--query-peak-requests-per-user",
        default=1,
        type=int,
        help="Requests per user for query-path peak-load scenario.",
    )
    parser.add_argument(
        "--skip-regression-check",
        action="store_true",
        help="Skip baseline regression checks.",
    )
    parser.add_argument(
        "--regression-baseline-file",
        default="scripts/performance_regression_baseline.json",
        help="Path to baseline metrics used by regression checks.",
    )
    parser.add_argument(
        "--regression-max-p95-percent",
        default=30.0,
        type=float,
        help="Maximum allowed P95 latency regression percent versus baseline.",
    )
    parser.add_argument(
        "--regression-max-p99-percent",
        default=30.0,
        type=float,
        help="Maximum allowed P99 latency regression percent versus baseline.",
    )
    parser.add_argument(
        "--regression-max-error-rate-delta-percent",
        default=0.1,
        type=float,
        help="Maximum allowed error-rate increase in percent points versus baseline.",
    )
    parser.add_argument(
        "--write-regression-baseline-file",
        default="",
        help="When provided, write current metrics to this baseline file path.",
    )
    return parser.parse_args()


async def _run_gate(args: argparse.Namespace) -> int:
    _bootstrap_runtime_dataset(profile=str(args.dataset_profile))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        timeout=args.timeout_seconds,
    ) as client:
        headers = await _authenticate(client, login_token=args.login_token)

        scenarios = [
            ScenarioConfig(
                name="normal_load",
                concurrent_users=max(1, int(args.normal_concurrency)),
                requests_per_user=max(1, int(args.normal_requests_per_user)),
                p95_target_ms=1000.0,
                p99_target_ms=2000.0,
                max_error_rate_percent=0.1,
            ),
            ScenarioConfig(
                name="peak_load",
                concurrent_users=max(1, int(args.peak_concurrency)),
                requests_per_user=max(1, int(args.peak_requests_per_user)),
                p95_target_ms=1500.0,
                p99_target_ms=2500.0,
                max_error_rate_percent=0.1,
            ),
            ScenarioConfig(
                name="burst_spike",
                concurrent_users=max(1, int(args.burst_concurrency)),
                requests_per_user=max(1, int(args.burst_requests_per_user)),
                p95_target_ms=max(1.0, float(args.burst_p95_target_ms)),
                p99_target_ms=max(1.0, float(args.burst_p99_target_ms)),
                max_error_rate_percent=0.1,
            ),
        ]

        scenario_results: list[ScenarioResult] = []
        for scenario in scenarios:
            result = await _run_scenario(
                client,
                endpoint=args.endpoint,
                headers=headers,
                scenario=scenario,
                max_inflight_requests=max(1, int(args.max_inflight_requests)),
            )
            scenario_results.append(result)

        recovery_probe = ScenarioConfig(
            name="post_burst_recovery_probe",
            concurrent_users=max(1, int(args.recovery_concurrency)),
            requests_per_user=max(1, int(args.recovery_requests_per_user)),
            p95_target_ms=max(1.0, float(args.recovery_p95_target_ms)),
            p99_target_ms=max(1.0, float(args.recovery_p99_target_ms)),
            max_error_rate_percent=max(0.0, float(args.recovery_max_error_rate_percent)),
        )
        recovery_result = await _run_recovery_check(
            client,
            endpoint=args.endpoint,
            headers=headers,
            probe_scenario=recovery_probe,
            max_inflight_requests=max(1, int(args.max_inflight_requests)),
            timeout_seconds=float(args.recovery_timeout_seconds),
            check_interval_seconds=float(args.recovery_check_interval_seconds),
        )

    query_path_result = QueryPathResult(
        enabled=False,
        login_token=args.query_login_token,
        query_text=args.query_text,
        scenarios=[],
        overall_status="skipped",
    )
    if not bool(args.skip_query_path):
        query_path_result = await _run_query_path_scenarios(
            query_login_token=str(args.query_login_token),
            query_text=str(args.query_text),
            query_warmup_requests=int(args.query_warmup_requests),
            query_normal_concurrency=int(args.query_normal_concurrency),
            query_normal_requests_per_user=int(args.query_normal_requests_per_user),
            query_peak_concurrency=int(args.query_peak_concurrency),
            query_peak_requests_per_user=int(args.query_peak_requests_per_user),
            max_inflight_requests=max(1, int(args.max_inflight_requests)),
        )

    current_metrics = _collect_current_metrics(
        scenario_results=scenario_results,
        recovery_result=recovery_result,
        query_path_result=query_path_result,
    )
    written_baseline_file = ""
    if str(args.write_regression_baseline_file).strip():
        written_baseline_file = _write_regression_baseline(
            destination_file=str(args.write_regression_baseline_file),
            metrics=current_metrics,
        )

    regression_result = RegressionCheckResult(
        enabled=False,
        baseline_file=str(args.regression_baseline_file),
        max_p95_regression_percent=float(args.regression_max_p95_percent),
        max_p99_regression_percent=float(args.regression_max_p99_percent),
        max_error_rate_delta_percent=float(args.regression_max_error_rate_delta_percent),
        missing_scenario_baselines=[],
        checks=[],
        overall_status="skipped",
    )
    if not bool(args.skip_regression_check):
        baseline_metrics = _load_regression_baseline(str(args.regression_baseline_file))
        regression_result = _run_regression_check(
            baseline_file=str(args.regression_baseline_file),
            baseline_metrics=baseline_metrics,
            current_metrics=current_metrics,
            max_p95_regression_percent=max(0.0, float(args.regression_max_p95_percent)),
            max_p99_regression_percent=max(0.0, float(args.regression_max_p99_percent)),
            max_error_rate_delta_percent=max(
                0.0,
                float(args.regression_max_error_rate_delta_percent),
            ),
        )

    passed = (
        all(item.passed for item in scenario_results)
        and recovery_result.passed
        and query_path_result.overall_status in {"pass", "skipped"}
        and regression_result.overall_status in {"pass", "skipped"}
    )
    report = {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "endpoint": args.endpoint,
        "dataset_profile": args.dataset_profile,
        "overall_status": "pass" if passed else "fail",
        "scenarios": [asdict(item) for item in scenario_results],
        "recovery": asdict(recovery_result),
        "query_path": asdict(query_path_result),
        "regression": asdict(regression_result),
        "written_regression_baseline_file": written_baseline_file,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if passed else 1


def main() -> int:
    args = _parse_args()
    return asyncio.run(_run_gate(args))


if __name__ == "__main__":
    raise SystemExit(main())