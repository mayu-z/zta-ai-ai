from __future__ import annotations

import json
import re
from datetime import datetime

from app.schemas.pipeline import CompiledQueryPlan


class Detokenizer:
    def _is_sign_aware_claim_key(self, claim_key: str | None) -> bool:
        if not claim_key:
            return False
        claim_key_lower = claim_key.lower()
        return any(
            keyword in claim_key_lower
            for keyword in ("delta", "trend", "change", "growth", "variance")
        )

    def _format_value(self, value: object, claim_key: str | None = None) -> str:
        if value is None:
            return "N/A"
        sign_aware = self._is_sign_aware_claim_key(claim_key)
        if isinstance(value, float):
            formatted = abs(value) if sign_aware and value < 0 else value
            return f"{formatted:.2f}".rstrip("0").rstrip(".")
        if isinstance(value, int):
            formatted_int = abs(value) if sign_aware and value < 0 else value
            return f"{formatted_int:,}"
        if isinstance(value, list):
            if not value:
                return "none"
            # Format list of dicts as readable summary
            if isinstance(value[0], dict):
                lines = []
                for i, item in enumerate(value[:10], 1):
                    query = item.get("query_text") or item.get("id", "unknown")
                    blocked = item.get("was_blocked", False)
                    timestamp = (
                        item.get("created_at", "")[:16]
                        if item.get("created_at")
                        else ""
                    )
                    status = "BLOCKED" if blocked else "allowed"
                    lines.append(f"{i}. [{status}] {query} ({timestamp})")
                result = "\n".join(lines)
                if len(value) > 10:
                    result += f"\n...and {len(value) - 10} more entries"
                return result
            return ", ".join(str(v) for v in value[:10])
        if isinstance(value, dict):
            return json.dumps(value, default=str)
        return str(value)

    def fill_slots(
        self,
        template: str,
        query_plan: CompiledQueryPlan,
        values: dict[str, object],
        masked_fields_applied: list[str] | None = None,
    ) -> str:
        rendered = template
        for slot_name, claim_key in query_plan.slot_map.items():
            value = values.get(claim_key)
            if self._is_sign_aware_claim_key(claim_key) and isinstance(
                value, (int, float)
            ) and value < 0:
                value = abs(value)
            rendered = rendered.replace(
                f"[{slot_name}]", self._format_value(value, claim_key)
            )

        rendered = re.sub(
            r"\b(?:increased|grew|up) by -(\d+\.?\d*)",
            r"decreased by \1",
            rendered,
            flags=re.IGNORECASE,
        )
        rendered = re.sub(
            r"\b(?:decreased|declined|down) by -(\d+\.?\d*)",
            r"decreased by \1",
            rendered,
            flags=re.IGNORECASE,
        )
        rendered = re.sub(
            r"(?i)^(dear|hello|hi)\s+\w.*?\n",
            "",
            rendered,
            flags=re.MULTILINE,
        )
        rendered = re.sub(
            r"(?i)\n?(best regards|sincerely|yours truly|kind regards)[^\n]*$",
            "",
            rendered,
            flags=re.MULTILINE,
        )
        rendered = re.sub(
            r"(?i)\n?\[Your [A-Za-z ]+\][^\n]*$",
            "",
            rendered,
            flags=re.MULTILINE,
        )
        rendered = re.sub(
            r"(?i)\n?(if you need|please let me know|i can assist|feel free)[^\n]*$",
            "",
            rendered,
            flags=re.MULTILINE,
        )
        rendered = " ".join(rendered.split())

        as_of = datetime.now().strftime("%d-%m-%Y")
        rendered = f"{rendered} As of {as_of}."

        if masked_fields_applied:
            rendered += " Some fields were masked by policy."

        return rendered


detokenizer = Detokenizer()
