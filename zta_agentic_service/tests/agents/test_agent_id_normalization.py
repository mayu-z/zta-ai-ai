from app.agents.registry_loader import AgentRegistryLoader
from app.services.registry_service import RegistryService


def test_registry_loader_agent_key_candidates_include_legacy_and_normalized() -> None:
    candidates = AgentRegistryLoader._agent_key_candidates("LEAVE_BALANCE_AGENT")

    assert candidates == ["LEAVE_BALANCE_AGENT", "leave_balance_v1"]


def test_registry_service_agent_key_candidates_include_legacy_and_normalized() -> None:
    candidates = RegistryService._agent_key_candidates("LEAVE_BALANCE_AGENT")

    assert candidates == ["LEAVE_BALANCE_AGENT", "leave_balance_v1"]


def test_agent_key_candidates_preserve_canonical_v1() -> None:
    loader_candidates = AgentRegistryLoader._agent_key_candidates("leave_balance_v1")
    service_candidates = RegistryService._agent_key_candidates("leave_balance_v1")

    assert loader_candidates == ["leave_balance_v1"]
    assert service_candidates == ["leave_balance_v1"]
