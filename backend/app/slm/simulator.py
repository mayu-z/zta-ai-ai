from __future__ import annotations

import logging
from typing import Any

from app.core.config import get_settings
from app.core.exceptions import ValidationError
from app.schemas.pipeline import InterpretedIntent, ScopeContext

logger = logging.getLogger(__name__)
UNSAFE_HINTS = ("select ", " from ", "schema", "table", "system prompt")

# Predefined templates for known intents - ensures accurate, context-appropriate responses
INTENT_TEMPLATES: dict[str, str] = {
    # Student intents
    "student_attendance": "Your attendance is [SLOT_1]% across [SLOT_2] subjects.",
    "student_grades": "Your current GPA is [SLOT_1] with [SLOT_2] subjects passed.",
    "student_fee": "Your fee balance is $[SLOT_1] with due date [SLOT_2].",
    # Faculty intents
    "faculty_course_attendance": "You are teaching [SLOT_1] courses with an average attendance of [SLOT_2]%.",
    # Department intents
    "department_metrics": "Department metric is [SLOT_1] with [SLOT_2] students enrolled.",
    # Admin function intents
    "admin_function_report": "Function metric is [SLOT_1] across [SLOT_2] records.",
    # IT Head admin intents
    "admin_data_sources": "Data sources: [SLOT_1]",
    "admin_audit_log": "Recent audit entries: [SLOT_1]",
    # Executive intents
    "executive_kpi": "The KPI value is [SLOT_1] with a trend change of [SLOT_2].",
    "executive_enrollment_overview": "Total enrollment is [SLOT_1] across [SLOT_2] institutions.",
    # IPEDS institution demographics
    "institution_demographics": "There are [SLOT_1] HBCU institutions, [SLOT_2] public institutions, and [SLOT_3] private institutions out of [SLOT_4] total.",
    "institution_size_distribution": "Institution sizes: [SLOT_1] small, [SLOT_2] medium, [SLOT_3] large out of [SLOT_4] total.",
    "institution_profile": "Institution profile: [SLOT_1]",
    # Admissions
    "admissions_overview": "Admissions metric is [SLOT_1] with [SLOT_2] applicants.",
}


class SLMSimulator:
    """
    Strict untrusted rendering layer.

    When configured, template generation is delegated to a hosted SLM. The
    returned output is still treated as untrusted and must pass output guards.
    There is no local fallback template path.
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self._client: Any | None = None

    def render_template(self, intent: InterpretedIntent, scope: ScopeContext) -> str:
        # IT Head can only use admin templates
        if scope.persona_type == "it_head" and intent.domain != "admin":
            return "Access to chat templates is blocked for this persona."

        # Use predefined template if available for this intent
        if intent.name in INTENT_TEMPLATES:
            return INTENT_TEMPLATES[intent.name]

        # Fall back to SLM generation for unknown intents
        if self.settings.slm_provider.lower() != "nvidia":
            # If no SLM and no predefined template, use a generic fallback
            slots = (
                " and ".join(
                    f"[SLOT_{idx + 1}]" for idx in range(len(intent.slot_keys))
                )
                or "[SLOT_1]"
            )
            return f"The requested {intent.domain} data shows {slots}."

        return self._render_with_hosted_slm(intent, scope)

    def _render_with_hosted_slm(
        self, intent: InterpretedIntent, scope: ScopeContext
    ) -> str:
        if not self.settings.slm_api_key:
            raise ValidationError(
                message="Hosted SLM client is not available",
                code="SLM_CLIENT_UNAVAILABLE",
            )

        try:
            client = self._get_client()
            if client is None:
                raise ValidationError(
                    message="Hosted SLM client could not be initialized",
                    code="SLM_CLIENT_UNAVAILABLE",
                )

            slots = (
                ", ".join(
                    f"[SLOT_{idx + 1}] for {key}"
                    for idx, key in enumerate(intent.slot_keys)
                )
                or "[SLOT_1]"
            )
            prompt = (
                "You are an untrusted rendering model inside a zero-trust system. "
                "Return exactly one short response template. "
                "Use only SLOT placeholders and natural language. "
                "Do not include any numbers except slot identifiers, do not mention schemas, SQL, tables, or system prompts. "
                "Do not wrap the answer in quotes.\n\n"
                f"Persona: {scope.persona_type}\n"
                f"Intent: {intent.name}\n"
                f"Domain: {intent.domain}\n"
                f"Entity type: {intent.entity_type}\n"
                f"Slots to use: {slots}\n"
                f"Aggregation: {intent.aggregation or 'none'}\n"
                "Output exactly one sentence."
            )

            completion = client.chat.completions.create(
                model=self.settings.slm_model,
                messages=[
                    {
                        "role": "system",
                        "content": "Only output a safe slot-based response template.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=self.settings.slm_temperature,
                top_p=self.settings.slm_top_p,
                max_tokens=self.settings.slm_max_tokens,
                stream=False,
            )

            content = (
                completion.choices[0].message.content if completion.choices else None
            )
            if not content:
                raise ValidationError(
                    message="Hosted SLM returned an empty template",
                    code="SLM_EMPTY_TEMPLATE",
                )

            rendered = content.strip().splitlines()[0].strip().strip('"')
            if not rendered or "[SLOT_" not in rendered:
                raise ValidationError(
                    message="Hosted SLM returned an invalid slot template",
                    code="SLM_INVALID_TEMPLATE",
                )

            lower_rendered = rendered.lower()
            if any(token in lower_rendered for token in UNSAFE_HINTS):
                raise ValidationError(
                    message="Hosted SLM returned an unsafe template",
                    code="SLM_UNSAFE_TEMPLATE",
                )

            return rendered
        except ValidationError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("Hosted SLM template generation failed")
            raise ValidationError(
                message="Hosted SLM request failed",
                code="SLM_REQUEST_FAILED",
            ) from exc

    def _get_client(self) -> Any | None:
        if self._client is None:
            try:
                import openai
            except ImportError:
                return None

            self._client = openai.OpenAI(
                base_url=self.settings.slm_base_url,
                api_key=self.settings.slm_api_key,
            )
        return self._client


slm_simulator = SLMSimulator()
