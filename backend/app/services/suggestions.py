from __future__ import annotations

PERSONA_ZTA_SUGGESTIONS = {
    "executive": [
        "Give me campus aggregate KPI summary.",
        "Show average enrollment across sampled institutions.",
        "Summarize finance and admissions trends this semester.",
        "Show a high-level department performance overview.",
    ],
    "student": [
        "What is my overall attendance this semester?",
        "How many courses am I currently enrolled in?",
        "Show my academic summary for this semester.",
        "Show recent campus notices relevant to students.",
    ],
    "faculty": [
        "How many courses am I handling right now?",
        "What is the average attendance across my courses?",
        "Show department-level academic performance summary.",
        "Show the latest notices for faculty.",
    ],
    "dept_head": [
        "Show department performance summary.",
        "How many students are in my department?",
        "Show exam backlog and pass rate for my department.",
        "Show department notices and action items.",
    ],
    "admin_staff": [
        "Show admissions operations summary for my office.",
        "How many applicant records are currently in scope?",
        "Show operations trend summary for my function.",
        "Show notices relevant to operations staff.",
    ],
    "it_head": [
        "Open Tenant Admin Dashboard to review connector health.",
        "Open Tenant Admin Dashboard to inspect the role map.",
        "Open Tenant Admin Dashboard to review recent policy proofs.",
        "Open Tenant Admin Dashboard and rebuild the control graph.",
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
