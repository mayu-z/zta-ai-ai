from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.agentic.connectors.base import ConnectorError
from app.agentic.connectors.smtp import SMTPConnector
from app.agentic.models.execution_plan import ScopeFilter, WriteExecutionPlan


class FakeSMTP:
    def __init__(self):
        self.messages = []

    async def send_message(self, message):
        self.messages.append(message)


@pytest.mark.asyncio
async def test_smtp_recipient_guard_blocks_external_domains(monkeypatch) -> None:
    connector = SMTPConnector(
        tenant_id=uuid4(),
        config={"tenant_allowed_domains": ["university.edu"]},
    )
    connector._connected = True
    connector._smtp = FakeSMTP()

    async def resolve_from(alias: str, tenant_id: str) -> str:
        del alias, tenant_id
        return "faculty@university.edu"

    async def allowed_domains(tenant_id: str) -> list[str]:
        del tenant_id
        return ["university.edu"]

    monkeypatch.setattr(connector, "_resolve_from_address", resolve_from)
    monkeypatch.setattr(connector, "_allowed_domains", allowed_domains)
    monkeypatch.setattr(connector, "_log_delivery_attempt", lambda **kwargs: None)

    plan = WriteExecutionPlan(
        plan_id="smtp-1",
        entity="email",
        operation="send_email",
        payload={
            "from_alias": "FAC-1",
            "to": ["student@university.edu", "outside@gmail.com"],
            "cc": [],
            "subject": "Test",
            "body": "Body",
            "tenant_id": str(connector.tenant_id),
        },
        scope=ScopeFilter(tenant_id=str(connector.tenant_id), user_alias="FAC-1", department_id="CS"),
    )

    with pytest.raises(ConnectorError):
        await connector.write(plan)
    assert connector._smtp.messages == []


@pytest.mark.asyncio
async def test_smtp_from_address_is_resolved_and_enforced(monkeypatch) -> None:
    connector = SMTPConnector(
        tenant_id=uuid4(),
        config={"tenant_allowed_domains": ["university.edu"]},
    )
    connector._connected = True
    connector._smtp = FakeSMTP()

    async def resolve_from(alias: str, tenant_id: str) -> str:
        del alias, tenant_id
        return "faculty@university.edu"

    async def allowed_domains(tenant_id: str) -> list[str]:
        del tenant_id
        return ["university.edu"]

    monkeypatch.setattr(connector, "_resolve_from_address", resolve_from)
    monkeypatch.setattr(connector, "_allowed_domains", allowed_domains)
    monkeypatch.setattr(connector, "_log_delivery_attempt", lambda **kwargs: None)

    plan = WriteExecutionPlan(
        plan_id="smtp-2",
        entity="email",
        operation="send_email",
        payload={
            "from_alias": "FAC-1",
            "to": ["student@university.edu"],
            "cc": [],
            "subject": "Leave",
            "body": "Applied",
            "tenant_id": str(connector.tenant_id),
            "from": "spoofed@evil.com",
        },
        scope=ScopeFilter(tenant_id=str(connector.tenant_id), user_alias="FAC-1", department_id="CS"),
    )

    await connector.write(plan)
    assert len(connector._smtp.messages) == 1
    assert connector._smtp.messages[0]["From"] == "faculty@university.edu"
