from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import inspect
import math
import time
from dataclasses import dataclass, field

from app.connectors.base import CONNECTOR_ERROR_CODES, ConnectorBase
from app.core.exceptions import ValidationError


@dataclass(slots=True)
class CertificationCheck:
    name: str
    passed: bool
    details: str = ""


@dataclass(slots=True)
class CertificationResult:
    connector_id: str
    source_type: str
    certified: bool
    checks: list[CertificationCheck] = field(default_factory=list)


class ConnectorCertificationHarness:
    """Runs contract and runtime/load checks used for connector certification gating."""

    REQUIRED_ERROR_CODES = {
        "SUCCESS",
        "CLIENT_ERROR",
        "AUTHENTICATION_ERROR",
        "AUTHORIZATION_ERROR",
        "NOT_FOUND",
        "RATE_LIMITED",
        "SERVER_ERROR",
        "TIMEOUT",
    }

    REQUIRED_METHODS = (
        "connect",
        "test_connection",
        "discover_schema",
        "execute_query",
        "sync",
        "health_check",
        "get_connection_info",
    )

    EXPECTED_PARAMETERS = {
        "connect": ("timeout_seconds",),
        "test_connection": ("timeout_seconds",),
        "discover_schema": ("force_refresh",),
        "execute_query": ("db", "plan", "timeout_seconds"),
        "sync": (),
        "health_check": (),
        "get_connection_info": (),
    }

    def __init__(
        self,
        *,
        load_iterations: int = 12,
        load_concurrency: int = 4,
        max_p95_connect_ms: int = 2000,
        min_reliability_ratio: float = 0.9,
    ) -> None:
        self.load_iterations = max(1, int(load_iterations))
        self.load_concurrency = max(1, int(load_concurrency))
        self.max_p95_connect_ms = max(1, int(max_p95_connect_ms))
        self.min_reliability_ratio = max(0.0, min(1.0, float(min_reliability_ratio)))

    def run(self, connector: ConnectorBase) -> CertificationResult:
        checks: list[CertificationCheck] = []

        checks.extend(self._check_error_code_contract())
        checks.extend(self._check_required_methods(connector))
        checks.extend(self._check_method_signatures(connector))
        checks.extend(self._check_connection_info_contract(connector))
        checks.extend(self._check_policy_safety_contract(connector))
        checks.extend(self._check_runtime_contract(connector))
        checks.extend(self._check_load_contract(connector))

        connector_id = "unknown"
        source_type = "unknown"
        try:
            info = connector.get_connection_info()
            connector_id = info.connector_id or connector_id
            source_type = info.source_type or source_type
        except Exception:  # noqa: BLE001
            pass

        return CertificationResult(
            connector_id=connector_id,
            source_type=source_type,
            certified=all(check.passed for check in checks),
            checks=checks,
        )

    def _check_error_code_contract(self) -> list[CertificationCheck]:
        missing = sorted(self.REQUIRED_ERROR_CODES - set(CONNECTOR_ERROR_CODES.keys()))
        return [
            CertificationCheck(
                name="contract:error_codes",
                passed=not missing,
                details="complete" if not missing else f"missing={','.join(missing)}",
            )
        ]

    def _check_required_methods(self, connector: ConnectorBase) -> list[CertificationCheck]:
        checks: list[CertificationCheck] = []
        for method_name in self.REQUIRED_METHODS:
            has_method = callable(getattr(connector, method_name, None))
            checks.append(
                CertificationCheck(
                    name=f"method:{method_name}",
                    passed=has_method,
                    details="present" if has_method else "missing",
                )
            )
        return checks

    def _check_method_signatures(self, connector: ConnectorBase) -> list[CertificationCheck]:
        checks: list[CertificationCheck] = []
        for method_name, expected_params in self.EXPECTED_PARAMETERS.items():
            method = getattr(connector, method_name, None)
            if method is None:
                checks.append(
                    CertificationCheck(
                        name=f"signature:{method_name}",
                        passed=False,
                        details="method missing",
                    )
                )
                continue

            params = tuple(inspect.signature(method).parameters.keys())
            passed = params[: len(expected_params)] == expected_params
            checks.append(
                CertificationCheck(
                    name=f"signature:{method_name}",
                    passed=passed,
                    details=f"got={params}",
                )
            )
        return checks

    def _check_connection_info_contract(
        self,
        connector: ConnectorBase,
    ) -> list[CertificationCheck]:
        try:
            info = connector.get_connection_info()
            flags_ok = isinstance(info.supports_sync, bool) and isinstance(
                info.supports_live_queries, bool
            )
            return [
                CertificationCheck(
                    name="contract:connection_info_flags",
                    passed=flags_ok,
                    details=(
                        f"supports_sync={info.supports_sync} "
                        f"supports_live_queries={info.supports_live_queries}"
                    ),
                )
            ]
        except Exception as exc:  # noqa: BLE001
            return [
                CertificationCheck(
                    name="contract:connection_info_flags",
                    passed=False,
                    details=str(exc),
                )
            ]

    def _check_policy_safety_contract(
        self,
        connector: ConnectorBase,
    ) -> list[CertificationCheck]:
        execute_query = getattr(connector, "execute_query", None)
        if execute_query is None:
            return [
                CertificationCheck(
                    name="policy:execute_query_compiled_plan",
                    passed=False,
                    details="method missing",
                )
            ]

        params = tuple(inspect.signature(execute_query).parameters.keys())
        uses_compiled_plan = len(params) >= 2 and params[0] == "db" and params[1] == "plan"
        return [
            CertificationCheck(
                name="policy:execute_query_compiled_plan",
                passed=uses_compiled_plan,
                details=f"got={params}",
            )
        ]

    def _check_runtime_contract(self, connector: ConnectorBase) -> list[CertificationCheck]:
        checks: list[CertificationCheck] = []

        try:
            connection = connector.connect(timeout_seconds=5)
            checks.append(
                CertificationCheck(
                    name="runtime:connect",
                    passed=connection.status in {"connected", "error"},
                    details=f"status={connection.status}",
                )
            )
        except Exception as exc:  # noqa: BLE001
            checks.append(
                CertificationCheck(
                    name="runtime:connect",
                    passed=False,
                    details=str(exc),
                )
            )

        try:
            test_result = connector.test_connection(timeout_seconds=5)
            checks.append(
                CertificationCheck(
                    name="runtime:test_connection",
                    passed=test_result.status in {"healthy", "degraded", "error"},
                    details=f"status={test_result.status}",
                )
            )
        except Exception as exc:  # noqa: BLE001
            checks.append(
                CertificationCheck(
                    name="runtime:test_connection",
                    passed=False,
                    details=str(exc),
                )
            )

        try:
            second_connection = connector.connect(timeout_seconds=5)
            checks.append(
                CertificationCheck(
                    name="runtime:connect_idempotent",
                    passed=second_connection.status in {"connected", "error"},
                    details=f"status={second_connection.status}",
                )
            )
        except Exception as exc:  # noqa: BLE001
            checks.append(
                CertificationCheck(
                    name="runtime:connect_idempotent",
                    passed=False,
                    details=str(exc),
                )
            )

        try:
            schema = connector.discover_schema(force_refresh=False)
            checks.append(
                CertificationCheck(
                    name="runtime:discover_schema",
                    passed=isinstance(schema, list),
                    details=(
                        f"type={type(schema).__name__} "
                        f"size={len(schema) if isinstance(schema, list) else 'n/a'}"
                    ),
                )
            )
        except ValidationError as exc:
            checks.append(
                CertificationCheck(
                    name="runtime:discover_schema",
                    passed=True,
                    details=f"validation_error:{exc.code}",
                )
            )
        except Exception as exc:  # noqa: BLE001
            checks.append(
                CertificationCheck(
                    name="runtime:discover_schema",
                    passed=False,
                    details=str(exc),
                )
            )

        try:
            sync_result = connector.sync()
            checks.append(
                CertificationCheck(
                    name="runtime:sync",
                    passed=sync_result.status in {"complete", "partial", "failed"},
                    details=f"status={sync_result.status}",
                )
            )
        except Exception as exc:  # noqa: BLE001
            checks.append(
                CertificationCheck(
                    name="runtime:sync",
                    passed=False,
                    details=str(exc),
                )
            )

        try:
            health = connector.health_check()
            checks.append(
                CertificationCheck(
                    name="runtime:health_check",
                    passed=health.status in {"healthy", "degraded", "error"},
                    details=f"status={health.status}",
                )
            )
        except Exception as exc:  # noqa: BLE001
            checks.append(
                CertificationCheck(
                    name="runtime:health_check",
                    passed=False,
                    details=str(exc),
                )
            )

        try:
            info = connector.get_connection_info()
            info_ok = bool(info.connector_id and info.source_type)
            checks.append(
                CertificationCheck(
                    name="runtime:get_connection_info",
                    passed=info_ok,
                    details=f"connector_id={info.connector_id} source_type={info.source_type}",
                )
            )
        except Exception as exc:  # noqa: BLE001
            checks.append(
                CertificationCheck(
                    name="runtime:get_connection_info",
                    passed=False,
                    details=str(exc),
                )
            )

        return checks

    def _check_load_contract(self, connector: ConnectorBase) -> list[CertificationCheck]:
        checks: list[CertificationCheck] = []

        checks.append(self._run_concurrency_loop(connector))
        checks.append(self._run_latency_loop(connector))
        checks.append(self._run_reliability_loop(connector))

        return checks

    def _run_concurrency_loop(self, connector: ConnectorBase) -> CertificationCheck:
        completed = 0
        succeeded = 0
        with ThreadPoolExecutor(max_workers=self.load_concurrency) as executor:
            futures = [
                executor.submit(self._call_test_connection, connector)
                for _ in range(self.load_concurrency)
            ]
            for future in as_completed(futures):
                completed += 1
                ok, _, _ = future.result()
                if ok:
                    succeeded += 1

        required_successes = math.ceil(self.load_concurrency * self.min_reliability_ratio)
        passed = succeeded >= required_successes
        return CertificationCheck(
            name="load:concurrency_loop",
            passed=passed,
            details=(
                f"workers={self.load_concurrency} succeeded={succeeded} "
                f"required={required_successes} completed={completed}"
            ),
        )

    def _run_latency_loop(self, connector: ConnectorBase) -> CertificationCheck:
        latencies_ms: list[int] = []
        failures = 0
        for _ in range(self.load_iterations):
            started = time.perf_counter()
            ok, reported_latency_ms, _ = self._call_test_connection(connector)
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            if not ok:
                failures += 1
                continue
            measured = elapsed_ms if reported_latency_ms <= 0 else int(reported_latency_ms)
            latencies_ms.append(measured)

        if not latencies_ms:
            return CertificationCheck(
                name="load:latency_loop",
                passed=False,
                details=f"no_successful_samples failures={failures} total={self.load_iterations}",
            )

        p95_ms = self._percentile(latencies_ms, 95)
        avg_ms = int(sum(latencies_ms) / len(latencies_ms))
        max_ms = max(latencies_ms)
        passed = p95_ms <= self.max_p95_connect_ms
        return CertificationCheck(
            name="load:latency_loop",
            passed=passed,
            details=(
                f"samples={len(latencies_ms)} failures={failures} avg_ms={avg_ms} "
                f"p95_ms={p95_ms} max_ms={max_ms} threshold_ms={self.max_p95_connect_ms}"
            ),
        )

    def _run_reliability_loop(self, connector: ConnectorBase) -> CertificationCheck:
        successes = 0
        last_error: str | None = None
        for _ in range(self.load_iterations):
            ok, _, error = self._call_test_connection(connector)
            if ok:
                successes += 1
            elif error:
                last_error = error

        ratio = successes / self.load_iterations
        passed = ratio >= self.min_reliability_ratio
        details = (
            f"successes={successes} total={self.load_iterations} "
            f"ratio={ratio:.3f} required={self.min_reliability_ratio:.3f}"
        )
        if last_error:
            details = f"{details} last_error={last_error}"

        return CertificationCheck(
            name="load:reliability_loop",
            passed=passed,
            details=details,
        )

    def _call_test_connection(self, connector: ConnectorBase) -> tuple[bool, int, str | None]:
        try:
            result = connector.test_connection(timeout_seconds=5)
            ok = result.status in {"healthy", "degraded"}
            latency_ms = int(result.latency_ms)
            return ok, latency_ms, result.error
        except Exception as exc:  # noqa: BLE001
            return False, 0, str(exc)

    def _percentile(self, values: list[int], percentile: int) -> int:
        if not values:
            return 0
        if len(values) == 1:
            return int(values[0])

        ordered = sorted(values)
        rank = (len(ordered) - 1) * (percentile / 100)
        lower = math.floor(rank)
        upper = math.ceil(rank)
        if lower == upper:
            return int(ordered[lower])

        lower_value = ordered[lower]
        upper_value = ordered[upper]
        interpolated = lower_value + (upper_value - lower_value) * (rank - lower)
        return int(interpolated)


connector_certification_harness = ConnectorCertificationHarness()
