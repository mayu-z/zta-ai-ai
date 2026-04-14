from __future__ import annotations

import ast
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any


FILE_TO_ACTION_ID: dict[str, str] = {
    "bulk_notification.py": "bulk_notification_v1",
    "email_draft.py": "email_draft_v1",
    "email_send.py": "email_send_v1",
    "fee_reminder.py": "fee_reminder_v1",
    "leave_approval.py": "leave_approval_v1",
    "leave_balance.py": "leave_balance_check_v1",
    "meeting_scheduler.py": "meeting_scheduler_v1",
    "payroll_query.py": "payroll_query_v1",
    "refund.py": "refund_request_v1",
    "result_notification.py": "result_notification_v1",
    "upi_payment.py": "upi_payment_link_v1",
}


class MigrationGenerator:
    KNOWN_OPERATION_PATTERNS = {
        "_compiler.execute_write": "action",
        "_scope.fetch_scoped": "fetch",
        "_approval.evaluate": "approval",
    }

    def generate(self, py_file_path: Path, action_registry_seed_data: dict[str, Any] | None = None) -> dict[str, Any]:
        action_registry_seed_data = action_registry_seed_data or {}
        source = py_file_path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        action_id = FILE_TO_ACTION_ID.get(py_file_path.name, py_file_path.stem)
        trigger_type = str(action_registry_seed_data.get(action_id, {}).get("trigger_type") or "user_query")
        allowed_personas = list(action_registry_seed_data.get(action_id, {}).get("allowed_personas") or [])
        required_scope = list(action_registry_seed_data.get(action_id, {}).get("required_data_scope") or [])

        detected_steps = self._extract_steps(tree)
        if not detected_steps:
            detected_steps = [
                {"node_id": "validate_action", "type": "action", "config": {"action_id": action_id}},
                {"node_id": "fetch_scope", "type": "fetch", "config": {"action_id": action_id}, "output_key": "claim_set"},
            ]

        edges = [{"from": "START", "to": detected_steps[0]["node_id"]}]
        for idx in range(0, len(detected_steps) - 1):
            edges.append({"from": detected_steps[idx]["node_id"], "to": detected_steps[idx + 1]["node_id"]})
        edges.append({"from": detected_steps[-1]["node_id"], "to": "END_SUCCESS"})

        return {
            "agent_id": action_id,
            "display_name": action_id.replace("_", " ").title(),
            "version": "1.0.0",
            "description": f"Migrated from {py_file_path.name}",
            "trigger": {"type": trigger_type, "config": {}},
            "intent": {"action_id": action_id},
            "policy": {
                "allowed_personas": allowed_personas,
                "required_data_scope": required_scope,
            },
            "steps": detected_steps,
            "edges": edges,
            "config": {},
            "audit": {"log_fields": [], "hash_fields": [], "retention_days": 365},
            "metadata": {
                "created_at": datetime.now(tz=UTC).date().isoformat(),
                "created_by": "migration_generator",
                "tenant_overridable_fields": [],
                "migrated_from": py_file_path.name,
            },
        }

    def generate_all(
        self,
        agents_dir: Path,
        output_dir: Path,
        registry_seed: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        output_dir.mkdir(parents=True, exist_ok=True)
        results: list[dict[str, Any]] = []

        for py_file in sorted(agents_dir.glob("*.py")):
            if py_file.name in {"base_agent.py", "__init__.py", "sensitive_monitor.py"}:
                continue

            try:
                definition = self.generate(py_file, registry_seed)
                output_path = output_dir / f"{definition['agent_id']}.json"
                output_path.write_text(json.dumps(definition, indent=2), encoding="utf-8")
                results.append(
                    {
                        "file": py_file.name,
                        "status": "SUCCESS",
                        "output": str(output_path),
                        "detected_steps": [step["type"] for step in definition.get("steps", [])],
                    }
                )
            except Exception as exc:  # noqa: BLE001
                results.append(
                    {
                        "file": py_file.name,
                        "status": "FAILED",
                        "error": str(exc),
                    }
                )

        return results

    def _extract_steps(self, tree: ast.AST) -> list[dict[str, Any]]:
        steps: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        execute_fn = None
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "execute":
                execute_fn = node
                break

        if execute_fn is None:
            return steps

        for statement in ast.walk(execute_fn):
            if not isinstance(statement, ast.Await):
                continue

            call_repr = ast.unparse(statement.value)
            node_type = None
            for pattern, candidate in self.KNOWN_OPERATION_PATTERNS.items():
                if pattern in call_repr:
                    node_type = candidate
                    break
            if node_type is None:
                continue

            base_node_id = f"{node_type}_step"
            node_id = base_node_id
            counter = 1
            while node_id in seen_ids:
                counter += 1
                node_id = f"{base_node_id}_{counter}"

            seen_ids.add(node_id)
            step_payload: dict[str, Any] = {"node_id": node_id, "type": node_type, "config": {}}
            if node_type == "fetch":
                step_payload["output_key"] = "claim_set"
            steps.append(step_payload)

        return steps
