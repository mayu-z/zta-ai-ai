from dataclasses import dataclass, field


@dataclass
class ExecutionContextSnapshot:
    execution_id: str
    tenant_id: str
    user_id: str
    persona: str
    definition_version_id: str
    config_version_id: str
    trace_id: str
    chain_depth: int = 0
    chain_path: list[str] = field(default_factory=list)
    current_step_index: int = 0
    retry_counters: dict[str, int] = field(default_factory=dict)
    token_map_ref: str | None = None


class ContextManager:
    def __init__(self) -> None:
        self._cache: dict[str, ExecutionContextSnapshot] = {}

    def save_snapshot(self, snapshot: ExecutionContextSnapshot) -> None:
        self._cache[snapshot.execution_id] = snapshot

    def load_snapshot(self, execution_id: str) -> ExecutionContextSnapshot:
        snapshot = self._cache.get(execution_id)
        if snapshot is None:
            raise KeyError(f"Missing execution context for {execution_id}")
        return snapshot

    def update_step_pointer(self, execution_id: str, step_index: int) -> None:
        snapshot = self.load_snapshot(execution_id)
        snapshot.current_step_index = step_index
        self.save_snapshot(snapshot)

    def increment_retry(self, execution_id: str, step_id: str) -> int:
        snapshot = self.load_snapshot(execution_id)
        current = snapshot.retry_counters.get(step_id, 0) + 1
        snapshot.retry_counters[step_id] = current
        self.save_snapshot(snapshot)
        return current
