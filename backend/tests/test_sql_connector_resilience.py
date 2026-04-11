from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.connectors.sql_connector import SQLConnector
from app.core.exceptions import ValidationError


def test_sql_connector_retries_transient_connect_failures_then_succeeds(
    monkeypatch,
) -> None:
    connector = SQLConnector(
        connection_url="sqlite+pysqlite:///:memory:",
        max_retries=2,
    )
    calls = {"count": 0}

    def flaky_probe() -> None:
        calls["count"] += 1
        if calls["count"] < 3:
            raise SQLAlchemyError("connection timeout")

    monkeypatch.setattr(connector, "_probe_connection", flaky_probe)

    status = connector.connect()

    assert status.status == "connected"
    assert calls["count"] == 3


def test_sql_connector_circuit_breaker_opens_after_repeated_failures(
    monkeypatch,
) -> None:
    connector = SQLConnector(
        connection_url="sqlite+pysqlite:///:memory:",
        max_retries=0,
        circuit_breaker_failure_threshold=2,
        circuit_breaker_reset_seconds=60,
    )

    def always_fail() -> None:
        raise SQLAlchemyError("connection timeout")

    monkeypatch.setattr(connector, "_probe_connection", always_fail)

    with pytest.raises(ValidationError) as first_exc:
        connector.connect()
    assert first_exc.value.code == "SOURCE_CONNECT_FAILED"

    with pytest.raises(ValidationError) as second_exc:
        connector.connect()
    assert second_exc.value.code == "SOURCE_CONNECT_FAILED"

    with pytest.raises(ValidationError) as third_exc:
        connector.connect()
    assert third_exc.value.code == "SOURCE_CIRCUIT_OPEN"


def test_sql_connector_circuit_breaker_allows_retry_after_reset(
    monkeypatch,
) -> None:
    connector = SQLConnector(
        connection_url="sqlite+pysqlite:///:memory:",
        max_retries=0,
        circuit_breaker_failure_threshold=1,
        circuit_breaker_reset_seconds=60,
    )

    def always_fail() -> None:
        raise SQLAlchemyError("connection timeout")

    monkeypatch.setattr(connector, "_probe_connection", always_fail)

    with pytest.raises(ValidationError):
        connector.connect()

    connector._circuit_open_until = datetime.now(tz=UTC) - timedelta(seconds=1)

    monkeypatch.setattr(connector, "_probe_connection", lambda: None)
    status = connector.connect()

    assert status.status == "connected"
    assert connector._consecutive_failures == 0


def test_sql_connector_health_check_reports_open_circuit() -> None:
    connector = SQLConnector(connection_url="sqlite+pysqlite:///:memory:")
    connector._circuit_open_until = datetime.now(tz=UTC) + timedelta(seconds=30)
    connector._consecutive_failures = 7

    health = connector.health_check()

    assert health.status == "degraded"
    assert "Circuit breaker is open" in health.recommendation
