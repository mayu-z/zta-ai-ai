from __future__ import annotations

import re

from app.core.exceptions import UnsafeOutputError
from app.core.security import contains_raw_number

DISALLOWED_OUTPUT_PATTERNS = [
    re.compile(r"\bselect\b", re.IGNORECASE),
    re.compile(r"\bfrom\b", re.IGNORECASE),
    re.compile(r"\bschema\b", re.IGNORECASE),
    re.compile(r"\btable\b", re.IGNORECASE),
    re.compile(r"system prompt", re.IGNORECASE),
]


class OutputGuard:
    def validate(self, template: str, real_identifiers: list[str]) -> None:
        if contains_raw_number(template):
            raise UnsafeOutputError(
                message="Template contains raw numeric values", code="RAW_VALUE_LEAK"
            )

        lower_template = template.lower()
        for identifier in real_identifiers:
            if identifier and identifier in lower_template:
                raise UnsafeOutputError(
                    message="Template leaked real schema identifier",
                    code="SCHEMA_LEAK_DETECTED",
                )

        for pattern in DISALLOWED_OUTPUT_PATTERNS:
            if pattern.search(template):
                raise UnsafeOutputError(
                    message="Template includes unsafe system tokens",
                    code="SYSTEM_TOKEN_LEAK",
                )

        slots = re.findall(r"\[SLOT_\d+\]", template)
        if not slots:
            raise UnsafeOutputError(
                message="Template missing required SLOT placeholders",
                code="SLOT_MISSING",
            )


output_guard = OutputGuard()
