from sqlalchemy import Select


class TenantScopeError(ValueError):
    pass


def require_tenant_id(tenant_id: str | None) -> str:
    if not tenant_id:
        raise TenantScopeError("tenant_id is required for tenant-scoped operations")
    return tenant_id


def apply_tenant_scope(stmt: Select, model: type, tenant_id: str) -> Select:
    require_tenant_id(tenant_id)
    if not hasattr(model, "tenant_id"):
        raise TenantScopeError(f"Model {model.__name__} is missing tenant_id")
    return stmt.where(getattr(model, "tenant_id") == tenant_id)
