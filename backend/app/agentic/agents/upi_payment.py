from __future__ import annotations

from datetime import UTC, datetime
import hashlib

from app.agentic.agents.base_agent import BaseAgent
from app.agentic.core.compiler_interface import ExecutionPlan
from app.agentic.models.action_config import ActionConfig
from app.agentic.models.agent_context import AgentResult, AgentStatus, ClaimSet, RequestContext


class UPIPaymentAgent(BaseAgent):
    async def execute(
        self,
        action: ActionConfig,
        claim_set: ClaimSet,
        execution_plan: ExecutionPlan,
        ctx: RequestContext,
    ) -> AgentResult:
        amount = claim_set.claims.get("outstanding_balance")
        if amount in (None, 0, 0.0):
            return AgentResult(status=AgentStatus.FAILED, message="No outstanding fee balance available for payment.")

        amount_paise = int(float(amount) * 100)
        fee_period = str(execution_plan.metadata.get("fee_period") or "fees")
        ts_ms = int(datetime.now(tz=UTC).timestamp() * 1000)
        alias_hash = hashlib.sha256(ctx.user_alias.encode("utf-8")).hexdigest()[:8].upper()
        order_id = f"ZTA-{str(ctx.tenant_id)[:8].upper()}-{alias_hash}-{fee_period}-{ts_ms}"

        try:
            write_result = await self._compiler.execute_write(
                action=action,
                payload={
                    "amount_paise": amount_paise,
                    "order_id": order_id,
                    "description": "Fee payment",
                    "customer_alias": ctx.user_alias,
                    "expiry_seconds": 1800,
                },
                ctx=ctx,
            )
        except Exception as exc:  # noqa: BLE001
            return AgentResult(status=AgentStatus.FAILED, message=f"Payment link generation failed: {exc}")

        details = write_result.details or {}
        payment_url = details.get("payment_url")
        return AgentResult(
            status=AgentStatus.SUCCESS,
            message="Payment link generated successfully.",
            data={
                "order_id": write_result.generated_id or order_id,
                "payment_url": payment_url,
                "expires_at": details.get("expires_at"),
            },
        )
