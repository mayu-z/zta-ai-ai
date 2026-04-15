from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agents.base_handler import AgentContext
from app.agents.handlers.fee_reminder import FeeReminderHandler
from app.agents.handlers.payroll_query import PayrollQueryHandler
from app.agents.handlers.upi_payment import UpiPaymentHandler


@pytest.mark.asyncio
async def test_upi_payment_requires_confirmation() -> None:
    handler = UpiPaymentHandler(payment_gateway_client=None)
    ctx = AgentContext(
        action_id="act-1",
        instance=SimpleNamespace(config={"payment_gateway": {"type": "stub", "api_key": "k"}}),
        tenant_id="00000000-0000-0000-0000-000000000001",
        user_id="user-1",
        claim_set={"outstanding_amount": 1200, "due_date": "2026-06-30", "fee_record_alias": "fee-1"},
        trigger_payload={},
        confirmed=False,
    )

    result = await handler.execute(ctx)

    assert result.status == "pending_confirmation"
    assert result.requires_confirmation is True


@pytest.mark.asyncio
async def test_fee_reminder_dedup_skips_send() -> None:
    class DedupStore:
        def check(self, key: str, ttl_hours: int) -> bool:
            _ = (key, ttl_hours)
            return True

    handler = FeeReminderHandler(notification_service=None, dedup_store=DedupStore())
    ctx = AgentContext(
        action_id="act-2",
        instance=SimpleNamespace(config={"channel": "in_app", "message_template": "x", "days_before_due": 3}),
        tenant_id="00000000-0000-0000-0000-000000000001",
        user_id="user-2",
        claim_set={"student_alias": "st-1", "due_date": "2026-07-01", "outstanding_amount": 500},
        trigger_payload={},
        confirmed=False,
    )

    result = await handler.execute(ctx)

    assert result.status == "success"
    assert result.output["skipped"] is True
    assert result.output["reason"] == "dedup_window_active"


@pytest.mark.asyncio
async def test_payroll_query_fails_closed_without_monitor() -> None:
    handler = PayrollQueryHandler(llm_gateway=None, instance_store=None)
    ctx = AgentContext(
        action_id="act-3",
        instance=SimpleNamespace(config={}),
        tenant_id="00000000-0000-0000-0000-000000000001",
        user_id="user-3",
        claim_set={"pay_period": "May 2026", "gross_salary": 100000, "net_salary": 82000},
        trigger_payload={},
        confirmed=False,
    )

    result = await handler.execute(ctx)

    assert result.status == "failed"
    assert "Sensitive Field Access Monitor" in (result.error or "")
