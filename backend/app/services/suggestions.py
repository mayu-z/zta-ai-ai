from __future__ import annotations

PERSONA_ZTA_SUGGESTIONS = {
    "executive": [
        "Give me campus aggregate KPI summary.",
        "Show average enrollment across sampled institutions.",
        "Try to show raw student records to confirm aggregate-only enforcement.",
        "Ask for a finance-only dataset to confirm the domain gate blocks it.",
    ],
    "student": [
        "What is my overall attendance this semester?",
        "How many subjects am I currently enrolled in?",
        "What is my fee balance and due date?",
        "Show me another student's attendance record.",
    ],
    "faculty": [
        "How many courses am I handling right now?",
        "What is the average attendance across my courses?",
        "Show my leave balance and pending requests.",
        "Show student fee balances for the whole campus.",
    ],
    "dept_head": [
        "Show department performance summary.",
        "How many students are in my department?",
        "Show exam backlog and pass rate for my department.",
        "Show payroll records for all departments.",
    ],
    "admin_staff": [
        "Show admissions operations summary for my office.",
        "How many applicant records are currently in scope?",
        "Show admissions intake trend summary.",
        "Give me a finance collections summary.",
    ],
    "it_head": [
        "Use the admin panel to list data sources.",
        "Use the admin panel to review audit log entries.",
        "Try a chat query to confirm IT Head chat access is blocked.",
        "Use admin endpoints only and verify business-data chat stays denied.",
    ],
}

DEFAULT_ZTA_SUGGESTIONS = [
    "Show my role-allowed summary for today.",
    "Give me a quick performance overview for my current scope.",
    "Show one query that should be blocked by policy.",
    "Summarize my latest audit-visible activity.",
]


class SuggestionService:
    def suggestions_for(self, persona_type: str) -> list[str]:
        return PERSONA_ZTA_SUGGESTIONS.get(persona_type, DEFAULT_ZTA_SUGGESTIONS)


suggestion_service = SuggestionService()
