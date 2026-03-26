from __future__ import annotations

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
            rendered = rendered.replace(f"[{slot_name}]", self._format_value(values.get(claim_key)))

        as_of = datetime.now().strftime("%d-%m-%Y")
        rendered = f"{rendered} As of {as_of}."

        if masked_fields_applied:
            rendered += " Some fields were masked by policy."

        return rendered


detokenizer = Detokenizer()
