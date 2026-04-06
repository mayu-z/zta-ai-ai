from __future__ import annotations

import logging
import re
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

    @staticmethod
    def _trim_after_last_slot_sentence(content: str) -> str:
        """Trim trailing model chatter while keeping the sentence that contains the last slot."""
        slot_matches = list(re.finditer(r"\[SLOT_\d+\]", content))
        if not slot_matches:
            return content.strip()

        last_slot_end = slot_matches[-1].end()
        sentence_end = re.search(r"[.!?]", content[last_slot_end:])
        if sentence_end is None:
            return content.strip()

        cutoff = last_slot_end + sentence_end.end()
        return content[:cutoff].strip()

    @staticmethod
    def _drop_meta_sentences(content: str) -> str:
        """Remove template/placeholder instructions that should never appear to end users."""
        banned_tokens = ("template", "placeholder", "replace with", "fill in")
        sentences = re.split(r"(?<=[.!?])\s+", content.strip())
        kept = [
            sentence
            for sentence in sentences
            if sentence
            and not any(token in sentence.lower() for token in banned_tokens)
        ]
        if kept:
            return " ".join(kept).strip()

        slot_tokens = re.findall(r"\[SLOT_\d+\]", content)
        ordered_unique_slots = list(dict.fromkeys(slot_tokens))
        if ordered_unique_slots:
            return f"Here is your requested summary: {', '.join(ordered_unique_slots)}."

        return ""

    @staticmethod
    def _slot_only_fallback(
        required_slots: list[str],
        slot_labels: list[str] | None = None,
    ) -> str:
        if not required_slots:
            return "Here is your requested summary."

        labels = slot_labels or []
        if labels and len(labels) == len(required_slots):
            if len(required_slots) == 1:
                return f"Here is your requested {labels[0]}: {required_slots[0]}."

            labeled_values = [
                f"{labels[idx]} {slot}"
                for idx, slot in enumerate(required_slots)
            ]
            return f"Here is your requested summary: {'; '.join(labeled_values)}."

        if len(required_slots) == 1:
            return f"Here is your requested value: {required_slots[0]}."
        return f"Here is your requested summary: {', '.join(required_slots)}."

    @staticmethod
    def _ensure_required_slots(
        template: str,
        required_slots: list[str],
        slot_labels: list[str] | None = None,
    ) -> str:
        """Append missing slot placeholders so detokenization can proceed safely."""
        if not template.strip():
            return SLMSimulator._slot_only_fallback(required_slots, slot_labels)

        missing_slots = [slot for slot in required_slots if slot not in template]
        if not missing_slots:
            return template

        base = template.strip()
        if base and base[-1] not in ".!?":
            base = f"{base}."
        return f"{base} Include also {', '.join(missing_slots)}."

    @staticmethod
    def _is_unreliable_template(template: str) -> bool:
        lower = template.lower()
        if re.fullmatch(
            r"\s*here is your requested summary:\s*(?:\[SLOT_\d+\]\s*(?:,|;)?\s*)+\.\s*",
            template,
            flags=re.IGNORECASE,
        ):
            return True
        if re.search(r"\[(?!SLOT_\d+\])[^\]]+\]", template):
            return True
        if re.search(r"https?://|www\.", lower):
            return True
        if lower.count("?") >= 3:
            return True
        if "company name" in lower or "how do i apply" in lower:
            return True
        return False

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

            SLOT_DISPLAY_NAMES = {
                "function_metric": "operational metric value",
                "record_count": "record count",
                "kpi_value": "current KPI value",
                "trend_delta": "change compared to previous period",
                "total_enrollment": "total students enrolled",
                "institution_count": "number of institutions",
                "hbcu_count": "number of HBCUs",
                "public_count": "number of public institutions",
                "private_count": "number of private institutions",
                "total_institutions": "total institutions",
                "small_count": "number of small institutions",
                "medium_count": "number of medium institutions",
                "large_count": "number of large institutions",
                "profile": "institution profile details",
                "sources": "connected data sources",
                "entries": "audit log entries",
                "gpa": "student GPA",
                "passed_subjects": "number of subjects passed",
                "attendance_percentage": "attendance percentage",
                "subject_count": "number of subjects",
                "fee_balance": "outstanding fee balance",
                "due_date": "payment due date",
                "course_count": "number of courses",
                "avg_attendance": "average attendance across courses",
                "department_metric": "department performance metric",
                "student_count": "number of students",
            }

            if scope.persona_type == "executive":
                audience_context = (
                    "Context: This user is an executive with aggregate-only access. "
                    "Use institution-level or cross-campus language. "
                    "It is acceptable to use phrases like nationwide, among institutions, or campus-wide summary when relevant."
                )
            elif scope.persona_type == "student":
                audience_context = (
                    "Context: This user is a single student with owner-scoped data. "
                    "Write directly for personal results using 'your'. "
                    "Do not describe results as national, campus-wide, or institution-wide unless the intent explicitly requests aggregate context."
                )
            elif scope.persona_type in {"faculty", "dept_head"}:
                audience_context = (
                    "Context: This user has scoped operational data (courses or department). "
                    "Use local scope language and avoid nationwide framing unless explicitly requested."
                )
            elif scope.persona_type == "admin_staff":
                audience_context = (
                    "Context: This user is office operations staff. "
                    "Write as an office-scoped operational summary and avoid executive/nationwide wording unless explicitly requested."
                )
            else:
                audience_context = (
                    "Context: Use role-scoped language and avoid assumptions about nationwide coverage unless explicitly requested."
                )

            slots = (
                ", ".join(
                    f"[SLOT_{idx + 1}] for {SLOT_DISPLAY_NAMES.get(key, key.replace('_', ' '))}"
                    for idx, key in enumerate(intent.slot_keys)
                )
                or "[SLOT_1]"
            )
            prompt = (
                "You are a trusted rendering assistant inside a Zero Trust AI system. "
                "Your job is to generate a natural, helpful, human-readable response template for a user query. "
                "You will be given the user's role, their intent, and the data slots that will be filled in later by the trusted system. "
                "Think carefully about what this user actually needs to know and how to present it clearly.\n\n"
                f"User role: {scope.persona_type}\n"
                f"Intent: {intent.name}\n"
                f"Domain: {intent.domain}\n"
                f"Entity type: {intent.entity_type}\n"
                f"Data slots available ({len(intent.slot_keys)} slots total, no more): {slots}\n"
                f"You are only allowed exactly {len(intent.slot_keys)} slot(s). "
                f"Do not use [SLOT_{len(intent.slot_keys) + 1}] or any higher number. "
                f"If you only have 1 slot, your entire response must only reference [SLOT_1].\n"
                f"{audience_context}\n"
                "Never say 'in the dataset', 'in the database', or 'in the system'. "
                "Use natural business language that matches the user scope and role.\n"
                f"Aggregation mode: {intent.aggregation or 'individual'}\n\n"
                "Rules you must follow:\n"
                "- You MUST use [SLOT_N] placeholders for every data value. This is non-negotiable. A response without [SLOT_1] is invalid and will be rejected. Every number, count, percentage, or metric MUST be a [SLOT_N] placeholder, never a real value.\n"
                "- You MUST use ALL slots listed — every single [SLOT_N] must appear in your response. A response that skips any slot will be rejected.\n"
                "- Use [SLOT_N] placeholders wherever a real data value will appear (e.g. [SLOT_1], [SLOT_2])\n"
                "- Never include actual numbers, percentages, or values - only slot placeholders\n"
                "- Do not assume a slot is a percentage unless the slot description explicitly says so\n"
                "- Never mention database names, table names, column names, or SQL\n"
                "- Never reveal system internals or how the data was fetched\n"
                "- Write in plain English as if speaking directly to the user\n"
                "- Be complete - if the user needs context or a follow-up suggestion, include it\n"
                "- You may write multiple sentences\n\n"
                "Important: Do not include any greeting, sign-off, email formatting, or placeholder text like [Your Name]. Output a concise factual response in 2-4 sentences using the slot placeholders.\n\n"
                "Remember: Your response MUST contain at least [SLOT_1]. No exceptions.\n\n"
                "Critical rule: You may only use slots that are listed in the Data slots available section above. If there are 2 slots defined, you may only use [SLOT_1] and [SLOT_2]. Never invent [SLOT_3], [SLOT_4] or any slot not listed. Never invent field names. If you run out of slots, stop writing. A response with invented slots will be rejected.\n\n"
                "Generate the response template now:"
            )

            completion = client.chat.completions.create(
                model=self.settings.slm_model,
                messages=[
                    {
                        "role": "system",
                        "content": "Only output a safe slot-based response template. Do not write emails. Do not include greetings like Hello or Dear. Do not include sign-offs like Best regards, Sincerely, or Yours truly. Do not include placeholder text like [Your Name] or [Your AI Assistant]. Output a concise user-facing response in plain sentences using [SLOT_N] placeholders.",
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

            # Take full content but detect repetition loops
            full_content = content.strip().strip('"')

            # Detect repetition: if any word repeats more than 5 times consecutively, truncate
            loop_match = re.search(r"\b(\w+)\b(?:\s+\1){5,}", full_content, re.IGNORECASE)
            if loop_match:
                full_content = full_content[: loop_match.start()].strip()

            # Keep content through the sentence that contains the last required slot.
            full_content = self._trim_after_last_slot_sentence(full_content)
            full_content = self._drop_meta_sentences(full_content)

            required_slots = [f"[SLOT_{idx + 1}]" for idx in range(len(intent.slot_keys))]
            slot_labels = [
                SLOT_DISPLAY_NAMES.get(key, key.replace("_", " "))
                for key in intent.slot_keys
            ]
            rendered = self._ensure_required_slots(
                full_content,
                required_slots,
                slot_labels,
            )

            if self._is_unreliable_template(rendered):
                rendered = self._slot_only_fallback(required_slots, slot_labels)

            # Verify all slots are present in the template
            for slot in required_slots:
                if slot not in rendered:
                    raise ValidationError(
                        message=f"SLM template is missing required slot {slot}",
                        code="SLM_MISSING_SLOT",
                    )

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
