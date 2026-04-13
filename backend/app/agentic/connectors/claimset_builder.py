from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
from typing import Any
from uuid import UUID

from app.agentic.core.policy_engine import PolicyDecision
from app.agentic.models.agent_context import ClaimSet

from .base import RawResult


@dataclass(frozen=True)
class FieldSchema:
    raw_name: str
    alias: str
    classification: str = "GENERAL"


@dataclass(frozen=True)
class EntitySchema:
    entity: str
    fields: dict[str, FieldSchema]

    def get_alias(self, raw_field: str) -> str:
        schema = self.fields.get(raw_field)
        if schema is None:
            return raw_field
        return schema.alias

    def get_classification(self, raw_field: str) -> str:
        schema = self.fields.get(raw_field)
        if schema is None:
            return "GENERAL"
        return schema.classification


class SchemaRegistry:
    """Tenant-scoped in-memory registry for field alias/classification metadata."""

    def __init__(self) -> None:
        self._schemas: dict[str, dict[str, EntitySchema]] = {}

    def register(self, *, tenant_id: UUID, entity: str, fields: dict[str, FieldSchema]) -> None:
        tenant_key = str(tenant_id)
        self._schemas.setdefault(tenant_key, {})[entity] = EntitySchema(entity=entity, fields=fields)

    def get(self, *, entity: str, tenant_id: UUID) -> EntitySchema:
        tenant_schemas = self._schemas.get(str(tenant_id), {})
        schema = tenant_schemas.get(entity)
        if schema is None:
            return EntitySchema(entity=entity, fields={})
        return schema


class MaskingEngine:
    """Simple deterministic masking strategy per classification family."""

    def apply(self, value: Any, classification: str) -> Any:
        if value is None:
            return None
        tag = str(classification).upper()
        if tag in {"PHI", "BIOMETRIC", "SENSITIVE"}:
            return "[REDACTED]"
        if tag == "PERSONAL":
            value_s = str(value)
            if len(value_s) <= 4:
                return "*" * len(value_s)
            return ("*" * (len(value_s) - 4)) + value_s[-4:]
        return value


class ClaimSetBuilder:
    def __init__(self, schema_registry: SchemaRegistry, masking_engine: MaskingEngine):
        self._schema = schema_registry
        self._masking = masking_engine

    def build(
        self,
        raw_result: RawResult,
        entity: str,
        tenant_id: UUID,
        policy_decision: PolicyDecision,
    ) -> ClaimSet:
        schema = self._schema.get(entity=entity, tenant_id=tenant_id)
        claims: dict[str, Any] = {}
        classifications: dict[str, str] = {}

        for row in raw_result.rows:
            for raw_field, value in row.items():
                alias = schema.get_alias(raw_field)
                classification = schema.get_classification(raw_field)

                if alias in policy_decision.masked_fields:
                    value = self._masking.apply(value, classification)

                if self._must_tokenise(alias=alias, classification=classification):
                    value = self._tokenise(value, tenant_id)

                if alias in claims and isinstance(claims[alias], list):
                    claims[alias].append(value)
                elif alias in claims:
                    claims[alias] = [claims[alias], value]
                else:
                    claims[alias] = value
                classifications[alias] = classification

        return ClaimSet(
            claims=claims,
            field_classifications=classifications,
            source_alias=raw_result.source_schema,
            fetched_at=datetime.now(tz=UTC).replace(tzinfo=None),
            row_count=raw_result.row_count,
        )

    def _tokenise(self, value: Any, tenant_id: UUID) -> str:
        raw = f"{tenant_id}:{value}"
        return "TKN-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12].upper()

    def _must_tokenise(self, *, alias: str, classification: str) -> bool:
        class_tag = classification.upper()
        if class_tag in {"IDENTIFIER", "SYSTEM_ID"}:
            return True
        return alias.lower().endswith("_id")
