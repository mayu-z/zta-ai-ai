from __future__ import annotations

import logging
from typing import Any

from app.core.config import get_settings
from app.core.exceptions import ValidationError
from app.schemas.pipeline import InterpretedIntent, ScopeContext

logger = logging.getLogger(__name__)
UNSAFE_HINTS = ("select ", " from ", "schema", "table", "system prompt")


class SLMSimulator:
    """
    Strict untrusted rendering layer (sandboxed, stateless).

    All template generation is delegated to a hosted SLM. The SLM receives only
    sanitized intent metadata (no raw data values) and produces slot-based
    templates. The returned output is treated as untrusted and must pass output
    guards before use.

    Per ZTA-AI spec:
    - No pre-built or hardcoded templates
    - SLM generates all response templates dynamically
    - SLM has no access to databases, no memory, no tool calling
    - SLM runs in isolated environment (API-only access)
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self._client: Any | None = None
        self._validate_slm_config()

    def _validate_slm_config(self) -> None:
        """Validate SLM is properly configured at startup."""
        if not self.settings.slm_api_key:
            logger.warning(
                "SLM_API_KEY not configured - SLM template generation will fail"
            )

    def render_template(self, intent: InterpretedIntent, scope: ScopeContext) -> str:
        """
        Generate a response template using the hosted SLM.

        Always delegates to SLM - no hardcoded templates or fallbacks.
        This ensures dynamic, context-aware template generation as per spec.
        """
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
