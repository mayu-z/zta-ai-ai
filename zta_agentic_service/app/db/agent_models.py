"""Logical agentic models mapped to the canonical registry tables.

The existing service already uses `agent_definitions` and `tenant_agent_configs`
as the registry source of truth. This module exposes prompt-aligned names so
agent handlers and executors can use factory/instance terminology directly.
"""

from app.db.models import AgentDefinition, AgentExecutionLog, TenantAgentConfig

AgentTemplate = AgentDefinition
AgentInstance = TenantAgentConfig

__all__ = [
    "AgentTemplate",
    "AgentInstance",
    "AgentExecutionLog",
]
