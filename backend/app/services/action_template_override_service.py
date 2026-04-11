from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.db.models import ActionTemplateOverride
from app.services.action_registry import ACTION_TEMPLATE_REGISTRY, ActionTemplateSchema


class ActionTemplateOverrideService:
    _ALLOWED_UPDATE_FIELDS = {
        "is_enabled",
        "trigger",
        "approval_required",
        "approver_role",
        "sla_hours",
        "execution_steps",
    }

    def list_templates(self, *, db: Session, tenant_id: str) -> list[dict[str, object]]:
        rows = db.scalars(
            select(ActionTemplateOverride).where(ActionTemplateOverride.tenant_id == tenant_id)
        ).all()
        by_action_id = {row.action_id: row for row in rows}

        items: list[dict[str, object]] = []
        for action_id in sorted(ACTION_TEMPLATE_REGISTRY.keys()):
            row = by_action_id.get(action_id)
            effective = self._merge_template(
                base=ACTION_TEMPLATE_REGISTRY[action_id],
                row=row,
            )
            items.append(
                {
                    **effective.to_dict(),
                    "enabled": True if row is None else bool(row.is_enabled),
                    "override": self._serialize_override(row),
                }
            )
        return items

    def get_effective_template(
        self,
        *,
        db: Session,
        tenant_id: str,
        action_id: str,
        enforce_enabled: bool = True,
    ) -> ActionTemplateSchema:
        normalized_action_id = self._normalize_action_id(action_id)
        row = db.scalar(
            select(ActionTemplateOverride).where(
                ActionTemplateOverride.tenant_id == tenant_id,
                ActionTemplateOverride.action_id == normalized_action_id,
            )
        )
        if enforce_enabled and row is not None and not row.is_enabled:
            raise ValidationError(
                message=f"Action template {normalized_action_id} is disabled for this tenant",
                code="ACTION_TEMPLATE_DISABLED",
            )

        return self._merge_template(
            base=ACTION_TEMPLATE_REGISTRY[normalized_action_id],
            row=row,
        )

    def upsert_override(
        self,
        *,
        db: Session,
        tenant_id: str,
        action_id: str,
        updated_by: str,
        updates: dict[str, object],
    ) -> dict[str, object]:
        if not updates:
            raise ValidationError(
                message="At least one override field must be provided",
                code="ACTION_TEMPLATE_OVERRIDE_EMPTY",
            )

        unknown_fields = sorted(
            key for key in updates.keys() if key not in self._ALLOWED_UPDATE_FIELDS
        )
        if unknown_fields:
            raise ValidationError(
                message=f"Unsupported override fields: {', '.join(unknown_fields)}",
                code="ACTION_TEMPLATE_OVERRIDE_INVALID_FIELD",
            )

        normalized_action_id = self._normalize_action_id(action_id)
        row = db.scalar(
            select(ActionTemplateOverride).where(
                ActionTemplateOverride.tenant_id == tenant_id,
                ActionTemplateOverride.action_id == normalized_action_id,
            )
        )
        if row is None:
            row = ActionTemplateOverride(
                tenant_id=tenant_id,
                action_id=normalized_action_id,
                updated_by=updated_by,
            )

        if "is_enabled" in updates:
            value = updates["is_enabled"]
            if not isinstance(value, bool):
                raise ValidationError(
                    message="is_enabled must be boolean",
                    code="ACTION_TEMPLATE_OVERRIDE_INVALID",
                )
            row.is_enabled = value

        if "trigger" in updates:
            row.trigger_override = self._normalize_trigger(updates["trigger"])

        if "approval_required" in updates:
            row.approval_required_override = self._normalize_optional_bool(
                updates["approval_required"],
                field_name="approval_required",
            )

        if "approver_role" in updates:
            row.approver_role_override = self._normalize_optional_text(
                updates["approver_role"],
                field_name="approver_role",
            )

        if "sla_hours" in updates:
            row.sla_hours_override = self._normalize_optional_sla_hours(updates["sla_hours"])

        if "execution_steps" in updates:
            row.execution_steps_override = self._normalize_optional_steps(
                updates["execution_steps"],
            )

        row.updated_by = updated_by
        db.add(row)
        db.commit()
        db.refresh(row)

        effective = self.get_effective_template(
            db=db,
            tenant_id=tenant_id,
            action_id=normalized_action_id,
            enforce_enabled=False,
        )
        return {
            "action_id": normalized_action_id,
            "enabled": row.is_enabled,
            "override": self._serialize_override(row),
            "effective_template": effective.to_dict(),
        }

    def delete_override(
        self,
        *,
        db: Session,
        tenant_id: str,
        action_id: str,
    ) -> dict[str, object]:
        normalized_action_id = self._normalize_action_id(action_id)
        row = db.scalar(
            select(ActionTemplateOverride).where(
                ActionTemplateOverride.tenant_id == tenant_id,
                ActionTemplateOverride.action_id == normalized_action_id,
            )
        )
        if row is None:
            raise ValidationError(
                message=f"No override found for action template {normalized_action_id}",
                code="ACTION_TEMPLATE_OVERRIDE_NOT_FOUND",
            )

        db.delete(row)
        db.commit()

        return {
            "action_id": normalized_action_id,
            "enabled": True,
            "override": None,
            "effective_template": ACTION_TEMPLATE_REGISTRY[normalized_action_id].to_dict(),
        }

    def _normalize_action_id(self, action_id: str) -> str:
        normalized = (action_id or "").strip().upper()
        if not normalized or normalized not in ACTION_TEMPLATE_REGISTRY:
            raise ValidationError(
                message=f"Unknown action_id: {action_id}",
                code="ACTION_TEMPLATE_NOT_FOUND",
            )
        return normalized

    @staticmethod
    def _normalize_trigger(value: object) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip().lower()
        if not normalized:
            raise ValidationError(
                message="trigger must be a non-empty string when provided",
                code="ACTION_TEMPLATE_OVERRIDE_INVALID",
            )
        return normalized

    @staticmethod
    def _normalize_optional_bool(value: object, *, field_name: str) -> bool | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        raise ValidationError(
            message=f"{field_name} must be boolean or null",
            code="ACTION_TEMPLATE_OVERRIDE_INVALID",
        )

    @staticmethod
    def _normalize_optional_text(value: object, *, field_name: str) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip().lower()
        if not normalized:
            return None
        return normalized

    @staticmethod
    def _normalize_optional_sla_hours(value: object) -> int | None:
        if value is None:
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                message="sla_hours must be an integer between 1 and 168",
                code="ACTION_TEMPLATE_OVERRIDE_INVALID",
            ) from exc

        if parsed < 1 or parsed > 168:
            raise ValidationError(
                message="sla_hours must be between 1 and 168",
                code="ACTION_TEMPLATE_OVERRIDE_INVALID",
            )
        return parsed

    @staticmethod
    def _normalize_optional_steps(value: object) -> list[str] | None:
        if value is None:
            return None
        if not isinstance(value, list):
            raise ValidationError(
                message="execution_steps must be an array of non-empty strings",
                code="ACTION_TEMPLATE_OVERRIDE_INVALID",
            )

        normalized: list[str] = []
        for item in value:
            step = str(item).strip().lower()
            if not step:
                continue
            if step not in normalized:
                normalized.append(step)

        if not normalized:
            raise ValidationError(
                message="execution_steps must include at least one non-empty step",
                code="ACTION_TEMPLATE_OVERRIDE_INVALID",
            )
        return normalized

    @staticmethod
    def _merge_template(
        *,
        base: ActionTemplateSchema,
        row: ActionTemplateOverride | None,
    ) -> ActionTemplateSchema:
        trigger = base.trigger
        approval_requirements = dict(base.approval_requirements)
        execution_steps = list(base.execution_steps)

        if row is not None:
            if row.trigger_override:
                trigger = row.trigger_override

            if row.approval_required_override is not None:
                approval_requirements["required"] = bool(row.approval_required_override)

            if row.approver_role_override is not None:
                if row.approver_role_override:
                    approval_requirements["approver_role"] = row.approver_role_override
                else:
                    approval_requirements.pop("approver_role", None)

            if row.sla_hours_override is not None:
                approval_requirements["sla_hours"] = int(row.sla_hours_override)

            if row.execution_steps_override:
                execution_steps = list(row.execution_steps_override)

        return ActionTemplateSchema(
            action_id=base.action_id,
            trigger=trigger,
            required_data_scope=list(base.required_data_scope),
            required_permissions=list(base.required_permissions),
            approval_requirements=approval_requirements,
            input_schema=dict(base.input_schema),
            execution_steps=execution_steps,
            output_schema=dict(base.output_schema),
            risk_classification=base.risk_classification,
            audit_implications=list(base.audit_implications),
            allowed_personas=list(base.allowed_personas),
            prohibited_actions=list(base.prohibited_actions),
            reversible=base.reversible,
        )

    @staticmethod
    def _serialize_override(row: ActionTemplateOverride | None) -> dict[str, object] | None:
        if row is None:
            return None
        return {
            "id": row.id,
            "tenant_id": row.tenant_id,
            "action_id": row.action_id,
            "is_enabled": row.is_enabled,
            "trigger": row.trigger_override,
            "approval_required": row.approval_required_override,
            "approver_role": row.approver_role_override,
            "sla_hours": row.sla_hours_override,
            "execution_steps": list(row.execution_steps_override or []),
            "updated_by": row.updated_by,
            "created_at": row.created_at.isoformat(),
            "updated_at": row.updated_at.isoformat(),
        }


action_template_override_service = ActionTemplateOverrideService()
