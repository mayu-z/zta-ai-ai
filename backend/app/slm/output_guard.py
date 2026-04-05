from __future__ import annotations

import re

from app.core.exceptions import UnsafeOutputError
from app.core.security import contains_raw_number

DISALLOWED_OUTPUT_PATTERNS = [
    re.compile(r"\bSELECT\s+.{0,50}\s+FROM\b", re.IGNORECASE),
    re.compile(r"\bFROM\s+\w+\s+(WHERE|JOIN|LIMIT|GROUP)\b", re.IGNORECASE),
    re.compile(r"\bDROP\s+TABLE\b", re.IGNORECASE),
    re.compile(r"\bINSERT\s+INTO\b", re.IGNORECASE),
    re.compile(r"\bDELETE\s+FROM\b", re.IGNORECASE),
    re.compile(r"\bUPDATE\s+\w+\s+SET\b", re.IGNORECASE),
    re.compile(r"\bCREATE\s+TABLE\b", re.IGNORECASE),
    re.compile(r"system\s+prompt", re.IGNORECASE),
    re.compile(r"\bschema\s+name\b", re.IGNORECASE),
    re.compile(r"\bcolumn\s+name\b", re.IGNORECASE),
]


class OutputGuard:
    def validate(
        self,
        template: str,
        real_identifiers: list[str],
        expected_slot_count: int = 0,
    ) -> None:
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
        slot_numbers = set(int(re.search(r"\d+", s).group()) for s in slots)
        if expected_slot_count > 0 and max(slot_numbers, default=0) > expected_slot_count:
            raise UnsafeOutputError(
                message=f"Template contains more slots than defined ({max(slot_numbers)} > {expected_slot_count})",
                code="SLOT_COUNT_EXCEEDED",
            )
        if not slots:
            raise UnsafeOutputError(
                message="Template missing required SLOT placeholders",
                code="SLOT_MISSING",
            )


output_guard = OutputGuard()
