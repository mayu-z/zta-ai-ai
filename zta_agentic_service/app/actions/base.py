from __future__ import annotations

import hashlib
import hmac
import json
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.db.enums import ActionExecutionStatus
from app.db.models import ActionAuditLog, ActionExecution


@dataclass
class PreviewResult:
    preview_only: bool
    summary: str
    details: dict[str, Any]


@dataclass
class ExecutionResult:
    status: str
    summary: str
    details: dict[str, Any]


@dataclass
class RollbackResult:
    status: str
    summary: str
    details: dict[str, Any]


class BaseAction(ABC):
    name: str = "base_action"

    def __init__(self, db: Session, actor: str = "system") -> None:
        self.db = db
        self.actor = actor

    @abstractmethod
    def dry_run(self, context: dict[str, Any]) -> PreviewResult:
        raise NotImplementedError

    @abstractmethod
    def execute(self, context: dict[str, Any]) -> ExecutionResult:
        raise NotImplementedError

    @abstractmethod
    def rollback(self, execution_id: str) -> RollbackResult:
        raise NotImplementedError

    def create_execution_record(
        self,
        *,
        triggered_by: str,
        payload: dict[str, Any],
        dry_run: bool,
    ) -> ActionExecution:
        row = ActionExecution(
            action_name=self.name,
            triggered_by=triggered_by,
            status=ActionExecutionStatus.PENDING,
            dry_run=dry_run,
            payload=payload,
            result={},
        )
        self.db.add(row)
        self.db.flush()
        return row

    def update_execution(
        self,
        *,
        execution: ActionExecution,
        status: ActionExecutionStatus,
        result_payload: dict[str, Any],
        completed: bool = False,
    ) -> None:
        execution.status = status
        execution.result = result_payload
        if completed:
            execution.completed_at = datetime.now(UTC)
        self.db.add(execution)
        self.db.commit()

    def append_execution_result(self, execution: ActionExecution, patch: dict[str, Any]) -> None:
        merged = dict(execution.result or {})
        merged.update(patch)
        execution.result = merged
        self.db.add(execution)
        self.db.commit()

    def get_execution(self, execution_id: str) -> ActionExecution:
        row = self.db.get(ActionExecution, execution_id)
        if row is None:
            raise KeyError(f"Unknown action execution: {execution_id}")
        return row

    def audit_log(
        self,
        *,
        execution_id: str,
        step: str,
        outcome: str,
        payload_in: dict[str, Any],
        payload_out: dict[str, Any],
        actor: str | None = None,
    ) -> ActionAuditLog:
        body = {
            "input": payload_in,
            "output": payload_out,
        }
        encoded = json.dumps(body, sort_keys=True, default=str, separators=(",", ":"))
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        log = ActionAuditLog(
            execution_id=execution_id,
            step_name=step,
            actor=actor or self.actor,
            outcome=outcome,
            payload_hash=digest,
            timestamp=datetime.now(UTC),
        )
        self.db.add(log)
        self.db.commit()
        return log

    @staticmethod
    def sign_payload(payload: dict[str, Any], secret: str) -> str:
        body = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
        return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()

    @staticmethod
    def to_dict(result: PreviewResult | ExecutionResult | RollbackResult) -> dict[str, Any]:
        return asdict(result)
