from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from typing import Any


class StepExecutionError(RuntimeError):
    def __init__(self, message: str, error_class: str, retryable: bool) -> None:
        super().__init__(message)
        self.error_class = error_class
        self.retryable = retryable


@dataclass
class StepResult:
    step_id: str
    status: str
    latency_ms: int
    output: dict[str, Any]


class StepExecutor:
    def __init__(self, approved_endpoints: list[str] | None = None) -> None:
        self.approved_endpoints = set(approved_endpoints or [])

    def execute_step(self, step: dict[str, Any], context: dict[str, Any]) -> StepResult:
        start = monotonic()
        step_type = step.get("step_type")
        step_id = step.get("step_id", step_type or "unknown")

        try:
            output = self._dispatch(step_type=step_type, step=step, context=context)
            return StepResult(
                step_id=step_id,
                status=output.get("status", "success"),
                latency_ms=int((monotonic() - start) * 1000),
                output=output,
            )
        except StepExecutionError:
            raise
        except Exception as exc:
            raise StepExecutionError(
                message=str(exc),
                error_class="unhandled_error",
                retryable=False,
            ) from exc

    def _dispatch(self, step_type: str | None, step: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        if step_type == "fetch_data":
            return {"status": "success", "tokenized_rows": []}

        if step_type == "validate":
            return {"status": "success", "validated": True}

        if step_type == "generate_link":
            return {"status": "success", "link_token": "[SLOT_LINK_1]"}

        if step_type == "render_template":
            template = step.get("config", {}).get("template", "")
            variables = context.get("variables", {})
            for key, value in variables.items():
                template = template.replace(f"{{{{{key}}}}}", str(value))
            return {"status": "success", "rendered": template}

        if step_type == "submit_api":
            endpoint = step.get("config", {}).get("endpoint")
            if endpoint not in self.approved_endpoints:
                raise StepExecutionError(
                    message="submit_api endpoint is not in tenant allowlist",
                    error_class="policy_violation",
                    retryable=False,
                )
            if not context.get("confirmed", False):
                return {"status": "waiting_confirmation"}
            return {"status": "success", "submitted": True}

        if step_type == "send_notification":
            return {"status": "success", "channels": step.get("config", {}).get("channels", [])}

        if step_type == "chain_agent":
            return {
                "status": "success",
                "next_agent_id": step.get("config", {}).get("target_agent_id"),
            }

        if step_type == "request_confirmation":
            return {"status": "waiting_confirmation"}

        if step_type == "alert_security":
            return {"status": "success", "alerted": True}

        raise StepExecutionError(
            message=f"Unsupported step_type: {step_type}",
            error_class="unsupported_step_type",
            retryable=False,
        )
