from typing import Protocol


class PluginValidationResult(dict):
    pass


class PluginStepResult(dict):
    pass


class PluginInterface(Protocol):
    plugin_id: str
    version: str

    def validate_config(self, config: dict) -> PluginValidationResult:
        ...

    def execute(self, step_request: dict) -> PluginStepResult:
        ...

    def health_check(self) -> dict:
        ...
