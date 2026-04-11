from __future__ import annotations

from types import SimpleNamespace

from app.connectors.certification import ConnectorCertificationHarness
from app.connectors.external_connectors import GoogleSheetsConnector
from app.connectors.mock_claims import mock_claims_connector
from app.connectors.sql_connector import SQLConnector


class _BrokenConnector:
    def connect(self, timeout_seconds: int = 30):
        return SimpleNamespace(status="connected", response_time_ms=1)


def test_connector_certification_harness_passes_mock_connector() -> None:
    harness = ConnectorCertificationHarness(load_iterations=6, load_concurrency=3)

    result = harness.run(mock_claims_connector)

    assert result.certified is True
    assert result.connector_id == "mock_claims"
    assert {
        "load:concurrency_loop",
        "load:latency_loop",
        "load:reliability_loop",
    }.issubset({check.name for check in result.checks})
    assert all(check.passed for check in result.checks)


def test_connector_certification_harness_passes_sql_connector() -> None:
    harness = ConnectorCertificationHarness()
    connector = SQLConnector(connection_url="sqlite+pysqlite:///:memory:")

    result = harness.run(connector)

    assert result.certified is True
    assert result.source_type == "sqlite"


def test_connector_certification_harness_passes_google_sheets_connector() -> None:
    harness = ConnectorCertificationHarness()
    connector = GoogleSheetsConnector(
        service_account_json={"project_id": "demo-project"},
        spreadsheet_id="sheet-abc",
        sheet_rows=[
            {
                "tenant_id": "tenant-1",
                "domain": "ops",
                "entity_type": "records",
                "claim_key": "record_count",
                "value_number": 10,
            }
        ],
    )

    result = harness.run(connector)

    assert result.certified is True
    assert result.source_type == "google_sheets"


def test_connector_certification_harness_flags_missing_contract_methods() -> None:
    harness = ConnectorCertificationHarness()

    result = harness.run(_BrokenConnector())

    assert result.certified is False
    assert any(not check.passed for check in result.checks)


def test_connector_certification_harness_fails_reliability_loop_when_unstable() -> None:
    harness = ConnectorCertificationHarness(load_iterations=8, load_concurrency=4)

    class _UnstableGoogleSheetsConnector(GoogleSheetsConnector):
        def __init__(self) -> None:
            super().__init__(
                service_account_json={"project_id": "demo-project"},
                spreadsheet_id="sheet-unstable",
                sheet_rows=[
                    {
                        "tenant_id": "tenant-1",
                        "domain": "ops",
                        "entity_type": "records",
                        "claim_key": "record_count",
                        "value_number": 1,
                    }
                ],
            )
            self._attempts = 0

        def test_connection(self, timeout_seconds: int = 30):
            self._attempts += 1
            if self._attempts % 2 == 0:
                return super().test_connection(timeout_seconds=timeout_seconds)
            return SimpleNamespace(status="error", latency_ms=0, error="transient")

    connector = _UnstableGoogleSheetsConnector()
    result = harness.run(connector)

    reliability_checks = [check for check in result.checks if check.name == "load:reliability_loop"]
    assert len(reliability_checks) == 1
    assert reliability_checks[0].passed is False
    assert result.certified is False
