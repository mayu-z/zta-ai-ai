from __future__ import annotations

from app.schemas.pipeline import InterpretedIntent, ScopeContext


TEMPLATE_MAP = {
    "student_attendance": "Your attendance this semester is [SLOT_1]% across [SLOT_2] subjects.",
    "student_grades": "Your current GPA is [SLOT_1] with [SLOT_2] passed subjects.",
    "student_fee": "Your outstanding fee balance is [SLOT_1], due by [SLOT_2].",
    "faculty_course_attendance": "You are handling [SLOT_1] courses with average attendance of [SLOT_2]%.",
    "department_metrics": "Your department performance index is [SLOT_1] with [SLOT_2] students in scope.",
    "admin_function_report": "Your function metric is [SLOT_1] across [SLOT_2] records.",
    "executive_kpi": "Campus aggregate KPI is [SLOT_1] with trend delta [SLOT_2].",
    "domain_summary": "Requested summary value is [SLOT_1] and secondary value is [SLOT_2].",
}


class SLMSimulator:
    """
    Strict untrusted rendering layer.

    It receives only abstract intent and emits slot-only templates.
    No data access, no tools, no memory.
    """

    def render_template(self, intent: InterpretedIntent, scope: ScopeContext) -> str:
        if scope.persona_type == "it_head":
            return "Access to chat templates is blocked for this persona."

        return TEMPLATE_MAP.get(intent.name, TEMPLATE_MAP["domain_summary"])


slm_simulator = SLMSimulator()
