from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from sqlalchemy.orm import Session

from app.schemas.pipeline import CompiledQueryPlan


class ConnectorBase(ABC):
    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def discover_schema(self) -> list[dict[str, Any]]: ...

    @abstractmethod
    def execute_query(self, db: Session, plan: CompiledQueryPlan) -> dict[str, Any]: ...

    @abstractmethod
    def sync(self) -> None: ...
