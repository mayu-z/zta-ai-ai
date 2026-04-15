from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.agents.base_handler import AgentContext, AgentResult, BaseAgentHandler


class UpiPaymentHandler(BaseAgentHandler):
    """Generates payment links only; never performs auto-debit operations."""

    def __init__(self, payment_gateway_client: Any | None = None) -> None:
        self.payment_gateway_client = payment_gateway_client

    @property
    def is_side_effect(self) -> bool:
        return True

    async def execute(self, ctx: AgentContext) -> AgentResult:
        claim_set = ctx.claim_set
        config = ctx.instance.config or {}

        if not ctx.confirmed:
            return AgentResult(
                status="pending_confirmation",
                requires_confirmation=True,
                confirmation_prompt=(
                    f"Generate a UPI payment link for Rs. {claim_set.get('outstanding_amount')} "
                    f"(Fee due: {claim_set.get('due_date')})?\n"
                    "This creates a payment request only. You must complete payment in your UPI app."
                ),
                output={},
            )

        gateway_config = config.get("payment_gateway", {})
        link_result = await self._create_payment_link(
            gateway_type=gateway_config.get("type", "stub"),
            gateway_config=gateway_config,
            amount=claim_set.get("outstanding_amount", 0),
            reference_id=claim_set.get("fee_record_alias", "fee-ref-stub"),
            description=f"Fee Payment - {claim_set.get('fee_period', 'current')}",
            upi_id_hint=gateway_config.get("merchant_upi_id"),
        )

        if not link_result.get("success"):
            return AgentResult(
                status="failed",
                output={},
                error=f"Payment gateway error: {link_result.get('error_code', 'unknown')}",
            )

        return AgentResult(
            status="success",
            output={
                "payment_link": link_result.get("url"),
                "link_expiry": link_result.get("expires_at"),
                "amount": claim_set.get("outstanding_amount"),
                "reference": link_result.get("reference_id"),
                "message": (
                    "Your UPI payment link is ready. Open it in your UPI app to complete payment."
                ),
            },
        )

    async def rollback(self, ctx: AgentContext, partial_result: AgentResult) -> None:
        reference = partial_result.output.get("reference")
        gateway_config = (ctx.instance.config or {}).get("payment_gateway", {})
        if reference and self.payment_gateway_client and hasattr(
            self.payment_gateway_client, "void_payment_link"
        ):
            await self.payment_gateway_client.void_payment_link(reference, gateway_config)

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        gateway = config.get("payment_gateway")
        if not gateway:
            errors.append("payment_gateway config block is required")
            return errors
        if "type" not in gateway:
            errors.append("payment_gateway.type is required")
        if "api_key" not in gateway:
            errors.append("payment_gateway.api_key is required")
        return errors

    async def _create_payment_link(self, **kwargs: Any) -> dict[str, Any]:
        if self.payment_gateway_client and hasattr(self.payment_gateway_client, "create_payment_link"):
            result = await self.payment_gateway_client.create_payment_link(**kwargs)
            if isinstance(result, dict):
                return result
            return {
                "success": bool(getattr(result, "success", False)),
                "url": getattr(result, "url", None),
                "expires_at": getattr(result, "expires_at", None),
                "reference_id": getattr(result, "reference_id", None),
                "error_code": getattr(result, "error_code", None),
            }

        expires_at = (datetime.now(UTC) + timedelta(minutes=30)).isoformat()
        return {
            "success": True,
            "url": f"upi://pay?am={kwargs.get('amount', 0)}&ref={kwargs.get('reference_id')}",
            "expires_at": expires_at,
            "reference_id": kwargs.get("reference_id", "fee-ref-stub"),
            "error_code": None,
        }
