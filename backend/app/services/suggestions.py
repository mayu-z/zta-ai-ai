from __future__ import annotations

PERSONA_ZTA_SUGGESTIONS = {
    "executive": [
        "Give me campus aggregate KPI summary.",
        "Show average enrollment across sampled institutions.",
        "Try to show raw student records to confirm aggregate-only enforcement.",
        "Ask for a finance-only dataset to confirm the domain gate blocks it.",
    ],
    "admin_staff": [
        "Show open admissions coverage across sampled campuses.",
        "Give me admissions KPI summary for institutions in scope.",
        "Try a campus-wide executive query to confirm admin scope limits.",
        "Try a finance summary to confirm cross-domain access is blocked.",
    ],
    "it_head": [
        "Use the admin panel to list data sources.",
        "Use the admin panel to review audit log entries.",
        "Try a chat query to confirm IT Head chat access is blocked.",
        "Use admin endpoints only and verify business-data chat stays denied.",
    ],
}

DEFAULT_ZTA_SUGGESTIONS = [
    "Ask for data that should be allowed for your role.",
    "Then ask for data outside your role to confirm the policy blocks it.",
    "Verify aggregate roles do not receive row-level records.",
    "Review the audit log to confirm both allowed and blocked actions are recorded.",
]


class SuggestionService:
    def suggestions_for(self, persona_type: str) -> list[str]:
        return PERSONA_ZTA_SUGGESTIONS.get(persona_type, DEFAULT_ZTA_SUGGESTIONS)


suggestion_service = SuggestionService()
