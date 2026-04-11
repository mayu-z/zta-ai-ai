from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.db.models import (
    ActionTemplateOverride,
    ControlGraphEdge,
    ControlGraphNode,
    DataSource,
    DomainKeyword,
    DomainSourceBinding,
    IntentDefinition,
    PolicyProofArtifact,
    RolePolicy,
    SchemaField,
    Tenant,
    User,
    UserStatus,
)
from app.services.action_registry import list_action_templates


class ControlPlaneGraphService:
    def _persona_matches_policy(self, *, persona: str, role_key: str) -> bool:
        if role_key == persona:
            return True
        if persona == "admin_staff" and role_key.startswith("admin_staff:"):
            return True
        if persona == "dept_head" and role_key in {"hod", "dept_head"}:
            return True
        if persona == "it_head" and role_key in {"it_head", "it_admin"}:
            return True
        return False

    def rebuild_tenant_graph(self, *, db: Session, tenant_id: str) -> dict[str, int]:
        tenant = db.scalar(select(Tenant).where(Tenant.id == tenant_id))
        if tenant is None:
            raise ValidationError(message="Tenant not found", code="TENANT_NOT_FOUND")

        db.execute(delete(ControlGraphEdge).where(ControlGraphEdge.tenant_id == tenant_id))
        db.execute(delete(ControlGraphNode).where(ControlGraphNode.tenant_id == tenant_id))

        node_index: dict[tuple[str, str], ControlGraphNode] = {}
        edge_index: set[tuple[str, str, str]] = set()

        def add_node(
            *,
            node_type: str,
            node_key: str,
            label: str,
            attributes: dict | None = None,
        ) -> ControlGraphNode:
            key = (node_type, node_key)
            existing = node_index.get(key)
            if existing is not None:
                return existing

            node = ControlGraphNode(
                id=str(uuid4()),
                tenant_id=tenant_id,
                node_type=node_type,
                node_key=node_key,
                label=label,
                attributes=attributes or {},
            )
            db.add(node)
            node_index[key] = node
            return node

        def add_edge(
            *,
            edge_type: str,
            source: ControlGraphNode,
            target: ControlGraphNode,
            attributes: dict | None = None,
        ) -> None:
            edge_key = (edge_type, source.id, target.id)
            if edge_key in edge_index:
                return
            edge_index.add(edge_key)
            # Ensure referenced nodes are persisted before edge insert to avoid
            # transient FK violations during full graph rebuilds.
            db.flush()
            db.add(
                ControlGraphEdge(
                    id=str(uuid4()),
                    tenant_id=tenant_id,
                    edge_type=edge_type,
                    source_node_id=source.id,
                    target_node_id=target.id,
                    attributes=attributes or {},
                )
            )

        plan_tier = tenant.plan_tier.value if hasattr(tenant.plan_tier, "value") else str(tenant.plan_tier)
        status = tenant.status.value if hasattr(tenant.status, "value") else str(tenant.status)
        tenant_node = add_node(
            node_type="tenant",
            node_key=tenant.id,
            label=tenant.name,
            attributes={
                "domain": tenant.domain,
                "subdomain": tenant.subdomain,
                "plan_tier": plan_tier,
                "status": status,
            },
        )

        role_policies = db.scalars(
            select(RolePolicy).where(
                RolePolicy.tenant_id == tenant_id,
                RolePolicy.is_active.is_(True),
            )
        ).all()
        role_nodes: dict[str, ControlGraphNode] = {}
        for policy in role_policies:
            role_node = add_node(
                node_type="role_policy",
                node_key=policy.role_key,
                label=policy.display_name,
                attributes={
                    "row_scope_mode": policy.row_scope_mode,
                    "aggregate_only": policy.aggregate_only,
                    "chat_enabled": policy.chat_enabled,
                    "masked_fields": list(policy.masked_fields or []),
                },
            )
            role_nodes[policy.role_key] = role_node
            add_edge(edge_type="tenant_has_role_policy", source=tenant_node, target=role_node)

            for domain in list(policy.allowed_domains or []):
                domain_node = add_node(
                    node_type="domain",
                    node_key=domain,
                    label=domain.replace("_", " ").title(),
                    attributes={},
                )
                add_edge(edge_type="role_allows_domain", source=role_node, target=domain_node)

            for field_alias in list(policy.masked_fields or []):
                field_node = add_node(
                    node_type="field_alias",
                    node_key=field_alias,
                    label=field_alias,
                    attributes={},
                )
                add_edge(edge_type="role_masks_field", source=role_node, target=field_node)

        users = db.scalars(
            select(User).where(
                User.tenant_id == tenant_id,
                User.status == UserStatus.active,
            )
        ).all()
        for user in users:
            persona = user.persona_type.value if hasattr(user.persona_type, "value") else str(user.persona_type)
            user_node = add_node(
                node_type="user",
                node_key=user.id,
                label=user.email,
                attributes={
                    "name": user.name,
                    "persona": persona,
                    "department": user.department,
                    "admin_function": user.admin_function,
                    "external_id": user.external_id,
                },
            )
            add_edge(edge_type="user_member_of_tenant", source=user_node, target=tenant_node)

            persona_node = add_node(
                node_type="persona",
                node_key=persona,
                label=persona.replace("_", " ").title(),
                attributes={},
            )
            add_edge(edge_type="user_has_persona", source=user_node, target=persona_node)

            for role_key, role_node in role_nodes.items():
                if self._persona_matches_policy(persona=persona, role_key=role_key):
                    add_edge(
                        edge_type="persona_maps_role_policy",
                        source=persona_node,
                        target=role_node,
                    )

        domain_keywords = db.scalars(
            select(DomainKeyword).where(
                DomainKeyword.tenant_id == tenant_id,
                DomainKeyword.is_active.is_(True),
            )
        ).all()
        for keyword_set in domain_keywords:
            domain = keyword_set.domain
            domain_node = add_node(
                node_type="domain",
                node_key=domain,
                label=domain.replace("_", " ").title(),
                attributes={},
            )
            for keyword in list(keyword_set.keywords or []):
                keyword_node = add_node(
                    node_type="domain_keyword",
                    node_key=f"{domain}:{keyword}",
                    label=keyword,
                    attributes={"domain": domain},
                )
                add_edge(
                    edge_type="keyword_maps_domain",
                    source=keyword_node,
                    target=domain_node,
                )

        intent_definitions = db.scalars(
            select(IntentDefinition).where(
                IntentDefinition.tenant_id == tenant_id,
                IntentDefinition.is_active.is_(True),
            )
        ).all()
        for intent in intent_definitions:
            intent_node = add_node(
                node_type="intent",
                node_key=intent.intent_name,
                label=intent.intent_name,
                attributes={
                    "entity_type": intent.entity_type,
                    "slot_keys": list(intent.slot_keys or []),
                    "requires_aggregation": intent.requires_aggregation,
                    "priority": intent.priority,
                },
            )
            domain_node = add_node(
                node_type="domain",
                node_key=intent.domain,
                label=intent.domain.replace("_", " ").title(),
                attributes={},
            )
            add_edge(edge_type="intent_targets_domain", source=intent_node, target=domain_node)

            for persona in list(intent.persona_types or []):
                persona_node = add_node(
                    node_type="persona",
                    node_key=persona,
                    label=persona.replace("_", " ").title(),
                    attributes={},
                )
                add_edge(
                    edge_type="intent_allowed_persona",
                    source=intent_node,
                    target=persona_node,
                )

        data_sources = db.scalars(select(DataSource).where(DataSource.tenant_id == tenant_id)).all()
        source_nodes: dict[str, ControlGraphNode] = {}
        for source in data_sources:
            source_status = source.status.value if hasattr(source.status, "value") else str(source.status)
            source_type = source.source_type.value if hasattr(source.source_type, "value") else str(source.source_type)
            source_node = add_node(
                node_type="data_source",
                node_key=source.id,
                label=source.name,
                attributes={"source_type": source_type, "status": source_status},
            )
            source_nodes[source.id] = source_node
            add_edge(edge_type="tenant_uses_source", source=tenant_node, target=source_node)

        schema_fields = db.scalars(
            select(SchemaField).where(SchemaField.tenant_id == tenant_id)
        ).all()
        for field in schema_fields:
            source_node = source_nodes.get(field.data_source_id)
            if source_node is None:
                continue
            field_node = add_node(
                node_type="schema_field",
                node_key=field.id,
                label=field.alias_token,
                attributes={
                    "real_table": field.real_table,
                    "real_column": field.real_column,
                    "visibility": field.visibility.value
                    if hasattr(field.visibility, "value")
                    else str(field.visibility),
                    "pii_flag": field.pii_flag,
                },
            )
            add_edge(edge_type="source_exposes_field", source=source_node, target=field_node)

            for persona in list(field.masked_for_personas or []):
                persona_node = add_node(
                    node_type="persona",
                    node_key=persona,
                    label=persona.replace("_", " ").title(),
                    attributes={},
                )
                add_edge(
                    edge_type="field_masked_for_persona",
                    source=field_node,
                    target=persona_node,
                )

        bindings = db.scalars(
            select(DomainSourceBinding).where(DomainSourceBinding.tenant_id == tenant_id)
        ).all()
        for binding in bindings:
            domain_node = add_node(
                node_type="domain",
                node_key=binding.domain,
                label=binding.domain.replace("_", " ").title(),
                attributes={},
            )
            target = source_nodes.get(binding.data_source_id or "")
            if target is None:
                source_type = (
                    binding.source_type.value
                    if hasattr(binding.source_type, "value")
                    else str(binding.source_type)
                )
                target = add_node(
                    node_type="source_type",
                    node_key=source_type,
                    label=source_type,
                    attributes={},
                )
            add_edge(
                edge_type="domain_bound_to_source",
                source=domain_node,
                target=target,
                attributes={
                    "binding_id": binding.id,
                    "is_active": binding.is_active,
                },
            )

        overrides = db.scalars(
            select(ActionTemplateOverride).where(ActionTemplateOverride.tenant_id == tenant_id)
        ).all()
        overrides_by_action = {row.action_id: row for row in overrides}

        for template in list_action_templates():
            action_id = str(template.get("action_id", "")).strip()
            if not action_id:
                continue
            override = overrides_by_action.get(action_id)

            template_node = add_node(
                node_type="action_template",
                node_key=action_id,
                label=action_id,
                attributes={
                    "trigger": template.get("trigger"),
                    "risk_classification": template.get("risk_classification"),
                    "approval_requirements": template.get("approval_requirements"),
                    "tenant_override": override is not None,
                    "is_enabled": override.is_enabled if override else True,
                },
            )
            add_edge(
                edge_type="tenant_has_action_template",
                source=tenant_node,
                target=template_node,
            )

            for persona in list(template.get("allowed_personas", [])):
                persona_node = add_node(
                    node_type="persona",
                    node_key=persona,
                    label=persona.replace("_", " ").title(),
                    attributes={},
                )
                add_edge(
                    edge_type="template_allowed_persona",
                    source=template_node,
                    target=persona_node,
                )

            for scope_name in list(template.get("required_data_scope", [])):
                scope_node = add_node(
                    node_type="data_scope",
                    node_key=scope_name,
                    label=scope_name.replace("_", " ").title(),
                    attributes={},
                )
                add_edge(
                    edge_type="template_requires_scope",
                    source=template_node,
                    target=scope_node,
                )

        return {"node_count": len(node_index), "edge_count": len(edge_index)}

    def get_tenant_graph_overview(
        self,
        *,
        db: Session,
        tenant_id: str,
        proofs_limit: int = 20,
    ) -> dict[str, object]:
        node_count = int(
            db.scalar(
                select(func.count(ControlGraphNode.id)).where(
                    ControlGraphNode.tenant_id == tenant_id
                )
            )
            or 0
        )
        if node_count == 0:
            self.rebuild_tenant_graph(db=db, tenant_id=tenant_id)
            db.commit()
            node_count = int(
                db.scalar(
                    select(func.count(ControlGraphNode.id)).where(
                        ControlGraphNode.tenant_id == tenant_id
                    )
                )
                or 0
            )

        edge_count = int(
            db.scalar(
                select(func.count(ControlGraphEdge.id)).where(
                    ControlGraphEdge.tenant_id == tenant_id
                )
            )
            or 0
        )

        nodes_by_type = {
            node_type: int(count)
            for node_type, count in db.execute(
                select(ControlGraphNode.node_type, func.count(ControlGraphNode.id))
                .where(ControlGraphNode.tenant_id == tenant_id)
                .group_by(ControlGraphNode.node_type)
            ).all()
        }
        edges_by_type = {
            edge_type: int(count)
            for edge_type, count in db.execute(
                select(ControlGraphEdge.edge_type, func.count(ControlGraphEdge.id))
                .where(ControlGraphEdge.tenant_id == tenant_id)
                .group_by(ControlGraphEdge.edge_type)
            ).all()
        }

        role_map = [
            {
                "role_key": row.role_key,
                "display_name": row.display_name,
                "allowed_domains": list(row.allowed_domains or []),
                "masked_fields": list(row.masked_fields or []),
                "row_scope_mode": row.row_scope_mode,
                "aggregate_only": row.aggregate_only,
                "chat_enabled": row.chat_enabled,
            }
            for row in db.scalars(
                select(RolePolicy)
                .where(
                    RolePolicy.tenant_id == tenant_id,
                    RolePolicy.is_active.is_(True),
                )
                .order_by(RolePolicy.role_key.asc())
            ).all()
        ]

        sources = {
            row.id: row
            for row in db.scalars(select(DataSource).where(DataSource.tenant_id == tenant_id)).all()
        }
        lineage: list[dict[str, object]] = []
        for binding in db.scalars(
            select(DomainSourceBinding).where(DomainSourceBinding.tenant_id == tenant_id)
        ).all():
            source = sources.get(binding.data_source_id or "")
            source_type = (
                source.source_type.value
                if source is not None and hasattr(source.source_type, "value")
                else binding.source_type.value
                if hasattr(binding.source_type, "value")
                else str(binding.source_type)
            )
            lineage.append(
                {
                    "domain": binding.domain,
                    "source_type": source_type,
                    "data_source_id": binding.data_source_id,
                    "data_source_name": source.name if source else None,
                    "data_source_status": source.status.value if source else None,
                    "is_active": binding.is_active,
                }
            )

        overrides = {
            row.action_id: row
            for row in db.scalars(
                select(ActionTemplateOverride).where(ActionTemplateOverride.tenant_id == tenant_id)
            ).all()
        }
        template_governance = []
        for template in list_action_templates():
            action_id = str(template.get("action_id", "")).strip()
            if not action_id:
                continue
            override = overrides.get(action_id)
            template_governance.append(
                {
                    "action_id": action_id,
                    "risk_classification": template.get("risk_classification"),
                    "approval_requirements": template.get("approval_requirements"),
                    "allowed_personas": list(template.get("allowed_personas", [])),
                    "required_data_scope": list(template.get("required_data_scope", [])),
                    "override": {
                        "is_enabled": override.is_enabled,
                        "approval_required_override": override.approval_required_override,
                        "approver_role_override": override.approver_role_override,
                        "sla_hours_override": override.sla_hours_override,
                    }
                    if override
                    else None,
                }
            )

        proof_rows = db.scalars(
            select(PolicyProofArtifact)
            .where(PolicyProofArtifact.tenant_id == tenant_id)
            .order_by(PolicyProofArtifact.created_at.desc())
            .limit(proofs_limit)
        ).all()
        recent_policy_proofs = [
            {
                "proof_id": row.proof_id,
                "intent_hash": row.intent_hash,
                "domain": row.domain,
                "source_type": row.source_type,
                "masked_fields": list(row.masked_fields or []),
                "created_at": row.created_at,
            }
            for row in proof_rows
        ]

        rebuild_markers = db.scalars(
            select(ControlGraphNode.updated_at)
            .where(ControlGraphNode.tenant_id == tenant_id)
            .order_by(ControlGraphNode.updated_at.desc())
            .limit(1)
        ).all()
        last_rebuild_at = rebuild_markers[0] if rebuild_markers else datetime.now(tz=UTC)

        return {
            "summary": {
                "total_nodes": node_count,
                "total_edges": edge_count,
                "last_graph_rebuild_at": last_rebuild_at,
            },
            "nodes_by_type": nodes_by_type,
            "edges_by_type": edges_by_type,
            "role_map": role_map,
            "data_lineage": sorted(lineage, key=lambda item: str(item["domain"])),
            "template_governance": sorted(
                template_governance,
                key=lambda item: str(item["action_id"]),
            ),
            "recent_policy_proofs": recent_policy_proofs,
        }


control_plane_graph_service = ControlPlaneGraphService()
