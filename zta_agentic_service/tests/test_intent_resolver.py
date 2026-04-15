from app.services.intent_resolver import IntentResolver


class SettingsStub:
    intent_auto_select_threshold = 0.82
    intent_clarification_threshold = 0.65
    intent_margin_threshold = 0.08


def test_intent_resolver_returns_ordered_candidates() -> None:
    resolver = IntentResolver(settings=SettingsStub())

    candidates = [
        {
            "agent_id": "LEAVE_BALANCE_AGENT",
            "name": "Leave Balance",
            "description": "Check leave balance and apply leave",
            "keywords": ["leave", "balance", "apply"],
            "risk_rank": 30,
        },
        {
            "agent_id": "PAYROLL_QUERY_AGENT",
            "name": "Payroll Query",
            "description": "Show salary and payslip details",
            "keywords": ["salary", "payslip", "payroll"],
            "risk_rank": 80,
        },
    ]

    result = resolver.resolve(
        query_text="How many leaves do I have left?",
        tenant_id="tenant-1",
        persona_context={
            "persona": "employee",
            "allowed_personas_by_agent": {
                "LEAVE_BALANCE_AGENT": ["employee"],
                "PAYROLL_QUERY_AGENT": ["employee"],
            },
            "historical_intent_hits": {"LEAVE_BALANCE_AGENT": 2},
        },
        candidates=candidates,
    )

    assert result.candidates
    assert result.candidates[0].agent_id == "LEAVE_BALANCE_AGENT"
    assert result.decision in {"auto_select", "clarification", "fallback"}
