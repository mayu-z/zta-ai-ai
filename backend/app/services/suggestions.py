from __future__ import annotations


SUGGESTIONS = {
    "student": [
        "What is my attendance percentage this semester?",
        "Show my current GPA.",
        "How much fee balance is pending for me?",
        "What is my exam schedule for this week?",
    ],
    "faculty": [
        "Show attendance trend for my courses.",
        "How many students are below 75% attendance in my courses?",
        "Show my leave balance.",
        "Summarize my course performance this semester.",
    ],
    "dept_head": [
        "Summarize department attendance this semester.",
        "Show department exam result trend.",
        "How many students are at risk in my department?",
        "Give me department performance index.",
    ],
    "admin_staff": [
        "Show finance records pending today.",
        "Summarize function backlog for this week.",
        "How many unresolved records are in my function?",
        "Give me my function KPI summary.",
    ],
    "executive": [
        "Give me campus aggregate KPI summary.",
        "Show enrolment and retention trend.",
        "What are the top aggregate performance shifts this quarter?",
        "Provide campus financial aggregate status.",
    ],
    "it_head": [
        "Open admin user management.",
        "Show connector health status.",
        "Review blocked query audit entries.",
        "Run department kill switch simulation.",
    ],
}


class SuggestionService:
    def suggestions_for(self, persona_type: str) -> list[str]:
        return SUGGESTIONS.get(persona_type, SUGGESTIONS["student"])


suggestion_service = SuggestionService()
