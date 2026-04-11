from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import SystemAdminContext, get_current_system_admin
from app.core.exceptions import ValidationError
from app.db.models import Claim, PlanTier, Tenant, TenantStatus, User
from app.db.session import get_db
from app.schemas.system_admin import (
    SystemAdminTenantCreateRequest,
    SystemAdminTenantDetail,
    SystemAdminTenantSummary,
    SystemAdminTenantUpdateRequest,
)
from app.services.tenant_onboarding_service import tenant_onboarding_service

router = APIRouter(prefix="/system-admin", tags=["system-admin"])


@router.get("/tenants", response_model=list[SystemAdminTenantSummary])
def list_tenants(
    status: str | None = Query(default=None),
    admin: SystemAdminContext = Depends(get_current_system_admin),
    db: Session = Depends(get_db),
):
    _ = admin

    stmt = select(Tenant).order_by(Tenant.created_at.desc())
    if status:
        normalized = status.strip().lower()
        try:
            tenant_status = TenantStatus(normalized)
        except ValueError as exc:
            raise ValidationError(
                message="status must be one of active, paused, suspended",
                code="TENANT_STATUS_INVALID",
            ) from exc
        stmt = stmt.where(Tenant.status == tenant_status)

    tenants = db.scalars(stmt).all()
    if not tenants:
        return []

    tenant_ids = [tenant.id for tenant in tenants]

    user_counts = {
        tenant_id: int(count)
        for tenant_id, count in db.execute(
            select(User.tenant_id, func.count(User.id))
            .where(User.tenant_id.in_(tenant_ids))
            .group_by(User.tenant_id)
        ).all()
    }
    claim_counts = {
        tenant_id: int(count)
        for tenant_id, count in db.execute(
            select(Claim.tenant_id, func.count(Claim.id))
            .where(Claim.tenant_id.in_(tenant_ids))
            .group_by(Claim.tenant_id)
        ).all()
    }

    return [
        SystemAdminTenantSummary(
            tenant_id=tenant.id,
            tenant_name=tenant.name,
            email_domain=tenant.domain,
            subdomain=tenant.subdomain,
            status=tenant.status.value,
            plan_tier=tenant.plan_tier.value,
            users_count=user_counts.get(tenant.id, 0),
            claims_count=claim_counts.get(tenant.id, 0),
            created_at=tenant.created_at,
        )
        for tenant in tenants
    ]


@router.get("/tenants/{tenant_id}", response_model=SystemAdminTenantSummary)
def get_tenant(
    tenant_id: str,
    admin: SystemAdminContext = Depends(get_current_system_admin),
    db: Session = Depends(get_db),
):
    _ = admin

    tenant = db.scalar(select(Tenant).where(Tenant.id == tenant_id))
    if tenant is None:
        raise ValidationError(message="Tenant not found", code="TENANT_NOT_FOUND")

    users_count = int(
        db.scalar(select(func.count(User.id)).where(User.tenant_id == tenant.id)) or 0
    )
    claims_count = int(
        db.scalar(select(func.count(Claim.id)).where(Claim.tenant_id == tenant.id)) or 0
    )

    return SystemAdminTenantSummary(
        tenant_id=tenant.id,
        tenant_name=tenant.name,
        email_domain=tenant.domain,
        subdomain=tenant.subdomain,
        status=tenant.status.value,
        plan_tier=tenant.plan_tier.value,
        users_count=users_count,
        claims_count=claims_count,
        created_at=tenant.created_at,
    )


@router.post("/tenants", response_model=SystemAdminTenantDetail)
def create_tenant(
    payload: SystemAdminTenantCreateRequest,
    admin: SystemAdminContext = Depends(get_current_system_admin),
    db: Session = Depends(get_db),
):
    created = tenant_onboarding_service.create_tenant(
        db=db,
        payload=payload,
        created_by=admin.email,
    )
    return SystemAdminTenantDetail(**created)


@router.patch("/tenants/{tenant_id}", response_model=SystemAdminTenantSummary)
def update_tenant(
    tenant_id: str,
    payload: SystemAdminTenantUpdateRequest,
    admin: SystemAdminContext = Depends(get_current_system_admin),
    db: Session = Depends(get_db),
):
    _ = admin

    tenant = db.scalar(select(Tenant).where(Tenant.id == tenant_id))
    if tenant is None:
        raise ValidationError(message="Tenant not found", code="TENANT_NOT_FOUND")

    if payload.tenant_name is not None:
        tenant.name = payload.tenant_name.strip()

    if payload.status is not None:
        normalized_status = payload.status.strip().lower()
        try:
            tenant.status = TenantStatus(normalized_status)
        except ValueError as exc:
            raise ValidationError(
                message="status must be one of active, paused, suspended",
                code="TENANT_STATUS_INVALID",
            ) from exc

    if payload.plan_tier is not None:
        normalized_plan = payload.plan_tier.strip().lower()
        try:
            tenant.plan_tier = PlanTier(normalized_plan)
        except ValueError as exc:
            raise ValidationError(
                message="plan_tier must be one of starter, growth, enterprise",
                code="TENANT_PLAN_TIER_INVALID",
            ) from exc

    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    users_count = int(
        db.scalar(select(func.count(User.id)).where(User.tenant_id == tenant.id)) or 0
    )
    claims_count = int(
        db.scalar(select(func.count(Claim.id)).where(Claim.tenant_id == tenant.id)) or 0
    )

    return SystemAdminTenantSummary(
        tenant_id=tenant.id,
        tenant_name=tenant.name,
        email_domain=tenant.domain,
        subdomain=tenant.subdomain,
        status=tenant.status.value,
        plan_tier=tenant.plan_tier.value,
        users_count=users_count,
        claims_count=claims_count,
        created_at=tenant.created_at,
    )
