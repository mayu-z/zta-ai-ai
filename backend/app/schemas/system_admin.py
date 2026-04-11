from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SystemAdminTenantCreateRequest(BaseModel):
    tenant_name: str = Field(min_length=2, max_length=255)
    email_domain: str = Field(min_length=3, max_length=255)
    subdomain: str | None = Field(default=None, max_length=100)
    plan_tier: str = Field(default="starter")
    seed_mock_users: bool = Field(default=True)
    seed_mock_claims: bool = Field(default=True)


class SystemAdminTenantUpdateRequest(BaseModel):
    tenant_name: str | None = Field(default=None, min_length=2, max_length=255)
    status: str | None = Field(default=None)
    plan_tier: str | None = Field(default=None)


class SystemAdminTenantSummary(BaseModel):
    tenant_id: str
    tenant_name: str
    email_domain: str
    subdomain: str
    status: str
    plan_tier: str
    users_count: int
    claims_count: int
    created_at: datetime


class SystemAdminTenantDetail(SystemAdminTenantSummary):
    graph_node_count: int = 0
    graph_edge_count: int = 0
    seeded_user_emails: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
