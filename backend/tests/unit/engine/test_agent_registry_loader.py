from __future__ import annotations

import json
from uuid import uuid4

import pytest

from app.agentic.registry.agent_registry import AgentDefinitionLoader


def _base_definition(agent_id: str) -> dict:
    return {
        "agent_id": agent_id,
        "display_name": "Fee Reminder",
        "version": "1.0.0",
        "description": "base description",
        "trigger": {"type": "user_query", "config": {}},
        "intent": {"action_id": agent_id},
        "policy": {"allowed_personas": ["student"], "required_data_scope": ["fees.own"]},
        "steps": [{"node_id": "validate", "type": "action", "config": {"action_id": agent_id}}],
        "config": {"rate_limit_max_per_day": 3},
        "metadata": {
            "created_at": "2026-04-15",
            "created_by": "engineering",
            "tenant_overridable_fields": [
                "config.rate_limit_max_per_day",
                "policy.allowed_personas",
            ],
        },
    }


@pytest.mark.asyncio
async def test_loader_applies_tenant_override_allowlist_only(tmp_path, monkeypatch) -> None:
    tenant_id = uuid4()
    agent_id = "fee_reminder_v1"
    (tmp_path / f"{agent_id}.json").write_text(json.dumps(_base_definition(agent_id)), encoding="utf-8")

    loader = AgentDefinitionLoader(definitions_dir=tmp_path, cache_ttl_seconds=60)
    monkeypatch.setattr(
        loader,
        "_load_tenant_override_sync",
        lambda requested_agent_id, requested_tenant_id: {
            "config": {"rate_limit_max_per_day": 9},
            "policy": {"allowed_personas": ["admin"]},
            "description": "tampered",
            "metadata": {"created_by": "attacker"},
            "extra": {"bad": True},
        },
    )

    loaded = await loader.load(agent_id, tenant_id)
    assert loaded is not None
    assert loaded.config["rate_limit_max_per_day"] == 9
    assert loaded.policy.allowed_personas == ["admin"]
    assert loaded.description == "base description"
    assert loaded.metadata.created_by == "engineering"


@pytest.mark.asyncio
async def test_loader_returns_none_for_missing_definition(tmp_path) -> None:
    loader = AgentDefinitionLoader(definitions_dir=tmp_path)
    loaded = await loader.load("missing_agent", uuid4())
    assert loaded is None
