from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db.models import Claim, ControlGraphEdge, ControlGraphNode, Tenant, User
from app.db.session import SessionLocal
from app.main import app


def test_system_admin_mock_login_and_create_tenant_with_mock_data() -> None:
    with TestClient(app) as client:
        login_response = client.post(
            "/auth/system-admin/mock-login",
            json={"admin_token": "mock_admin:sysadmin@zta.local"},
        )
        assert login_response.status_code == 200
        login_payload = login_response.json()
        assert login_payload["user"]["persona"] == "system_admin"
        token = login_payload["jwt"]

        create_response = client.post(
            "/system-admin/tenants",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "tenant_name": "College One",
                "email_domain": "college1.com",
                "seed_mock_users": True,
                "seed_mock_claims": True,
            },
        )
        assert create_response.status_code == 200
        created = create_response.json()
        assert created["email_domain"] == "college1.com"
        assert created["status"] == "active"
        assert created["users_count"] >= 22
        assert created["claims_count"] > 0
        assert created["graph_node_count"] > 0
        assert created["graph_edge_count"] > 0
        assert "tenant.admin@college1.com" in created["seeded_user_emails"]

        tenant_login = client.post(
            "/auth/google",
            json={"google_token": "mock:tenant.admin@college1.com"},
        )
        assert tenant_login.status_code == 200
        tenant_token = tenant_login.json()["jwt"]

        fleet_health = client.get(
            "/admin/system/fleet-health",
            headers={"Authorization": f"Bearer {tenant_token}"},
        )
        assert fleet_health.status_code == 200

        graph_overview = client.get(
            "/admin/graph/overview",
            headers={"Authorization": f"Bearer {tenant_token}"},
        )
        assert graph_overview.status_code == 200
        graph_payload = graph_overview.json()
        assert graph_payload["summary"]["total_nodes"] > 0
        assert graph_payload["summary"]["total_edges"] > 0
        assert isinstance(graph_payload["role_map"], list)
        assert isinstance(graph_payload["data_lineage"], list)

    db = SessionLocal()
    try:
        tenant = db.scalar(select(Tenant).where(Tenant.domain == "college1.com"))
        assert tenant is not None

        users_count = int(
            db.scalar(select(func.count(User.id)).where(User.tenant_id == tenant.id)) or 0
        )
        claims_count = int(
            db.scalar(select(func.count(Claim.id)).where(Claim.tenant_id == tenant.id))
            or 0
        )
        graph_nodes = int(
            db.scalar(
                select(func.count(ControlGraphNode.id)).where(
                    ControlGraphNode.tenant_id == tenant.id
                )
            )
            or 0
        )
        graph_edges = int(
            db.scalar(
                select(func.count(ControlGraphEdge.id)).where(
                    ControlGraphEdge.tenant_id == tenant.id
                )
            )
            or 0
        )
        assert users_count >= 22
        assert claims_count > 0
        assert graph_nodes > 0
        assert graph_edges > 0
    finally:
        db.close()


def test_system_admin_tenant_endpoint_requires_system_admin_token() -> None:
    with TestClient(app) as client:
        response = client.get("/system-admin/tenants")

    assert response.status_code == 401
    payload = response.json()
    assert payload["code"] == "TOKEN_REQUIRED"
