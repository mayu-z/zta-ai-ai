from __future__ import annotations

import json
from datetime import datetime

from app.schemas.pipeline import CompiledQueryPlan


class Detokenizer:
    def _format_value(self, value: object) -> str:
        if value is None:
            return "N/A"
        if isinstance(value, float):
            return f"{value:.2f}".rstrip("0").rstrip(".")
        if isinstance(value, int):
            return f"{value:,}"
        if isinstance(value, list):
            if not value:
                return "none"
            # Format list of dicts as readable summary
            if isinstance(value[0], dict):
                items = []
                for item in value[:5]:  # Limit to 5 items
                    name = (
                        item.get("name")
                        or item.get("query_text")
                        or item.get("id", "item")
                    )
                    status = item.get("status") or item.get("was_blocked")
                    if status is not None:
                        items.append(f"{name} ({status})")
                    else:
                        items.append(str(name))
                result = ", ".join(items)
                if len(value) > 5:
                    result += f" and {len(value) - 5} more"
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
            rendered = rendered.replace(
                f"[{slot_name}]", self._format_value(values.get(claim_key))
            )

        as_of = datetime.now().strftime("%d-%m-%Y")
        rendered = f"{rendered} As of {as_of}."

        if masked_fields_applied:
            rendered += " Some fields were masked by policy."

        return rendered


detokenizer = Detokenizer()
