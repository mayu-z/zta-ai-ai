from __future__ import annotations

from typing import Any

from app.agents.base_handler import AgentContext, AgentResult, BaseAgentHandler


class EmailDraftSendHandler(BaseAgentHandler):
    """Drafts or sends university-routed email templates with confirmation in send mode."""

    def __init__(self, llm_gateway: Any | None = None, smtp_client: Any | None = None) -> None:
        self.llm_gateway = llm_gateway
        self.smtp_client = smtp_client

    @property
    def is_side_effect(self) -> bool:
        return True

    async def execute(self, ctx: AgentContext) -> AgentResult:
        config = ctx.instance.config or {}
        email_type = ctx.trigger_payload.get("email_type", "general")
        template_config = (config.get("email_templates") or {}).get(email_type)

        if not template_config:
            return AgentResult(
                status="failed",
                output={},
                error=f"Email type '{email_type}' is not configured for this instance.",
            )

        draft = await self._fill_draft(
            template=template_config.get("template", "Subject: {subject}\n\n{body}"),
            slots=ctx.claim_set,
            persona=ctx.trigger_payload.get("persona"),
            fallback_to_alias=template_config.get("to_alias", ctx.claim_set.get("recipient_alias", "unknown")),
        )

        if config.get("draft_only", True):
            return AgentResult(
                status="success",
                output={
                    "mode": "draft",
                    "subject": draft["subject"],
                    "body": draft["body"],
                    "to": draft["to_alias"],
                    "message": "Draft ready. Review and send manually or click Send to send now.",
                },
            )

        if not ctx.confirmed:
            return AgentResult(
                status="pending_confirmation",
                requires_confirmation=True,
                confirmation_prompt=(
                    f"Send this email to {draft['to_display_name']}?\n\n"
                    f"{draft['subject']}\n\n{draft['body'][:200]}..."
                ),
                output={"draft": draft},
            )

        smtp_config = config.get("smtp", {})
        send_result = await self._send_email(
            smtp_config=smtp_config,
            to_alias=draft["to_alias"],
            subject=draft["subject"],
            body=draft["body"],
            from_name=smtp_config.get("from_name", "University Notifications"),
            tenant_id=ctx.tenant_id,
        )

        delivered = bool(send_result.get("delivered", False))
        return AgentResult(
            status="success" if delivered else "failed",
            output={
                "mode": "sent",
                "message_id": send_result.get("message_id"),
                "delivered": delivered,
                "message": "Email sent successfully." if delivered else f"Send failed: {send_result.get('error')}",
            },
            error=None if delivered else send_result.get("error"),
        )

    async def rollback(self, ctx: AgentContext, partial_result: AgentResult) -> None:
        _ = (ctx, partial_result)

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        if "email_templates" not in config or not config.get("email_templates"):
            errors.append("At least one email_template must be configured")
        if not config.get("draft_only", True) and "smtp" not in config:
            errors.append("smtp config required when draft_only=false")
        return errors

    async def _fill_draft(
        self,
        template: str,
        slots: dict[str, Any],
        persona: str | None,
        fallback_to_alias: str,
    ) -> dict[str, Any]:
        if self.llm_gateway and hasattr(self.llm_gateway, "fill_template"):
            result = await self.llm_gateway.fill_template(
                template=template,
                slots=slots,
                persona=persona,
            )
            if isinstance(result, dict):
                return {
                    "subject": result.get("subject", "Notification"),
                    "body": result.get("body", ""),
                    "to_alias": result.get("to_alias", fallback_to_alias),
                    "to_display_name": result.get("to_display_name", "recipient"),
                }

        subject = str(slots.get("subject", "Notification"))
        body = template.format(**{k: v for k, v in slots.items() if isinstance(k, str)})
        return {
            "subject": subject,
            "body": body,
            "to_alias": fallback_to_alias,
            "to_display_name": slots.get("recipient_name", "recipient"),
        }

    async def _send_email(
        self,
        smtp_config: dict[str, Any],
        to_alias: str,
        subject: str,
        body: str,
        from_name: str,
        tenant_id: str,
    ) -> dict[str, Any]:
        if self.smtp_client and hasattr(self.smtp_client, "send"):
            result = await self.smtp_client.send(
                smtp_config=smtp_config,
                to_alias=to_alias,
                subject=subject,
                body=body,
                from_name=from_name,
                tenant_id=tenant_id,
            )
            if isinstance(result, dict):
                return result
            return {
                "delivered": bool(getattr(result, "delivered", False)),
                "message_id": getattr(result, "message_id", None),
                "error": getattr(result, "error", None),
            }

        return {
            "delivered": True,
            "message_id": f"stub-email-{to_alias}",
            "error": None,
        }
