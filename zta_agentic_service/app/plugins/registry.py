from app.plugins.base import PluginInterface


class PluginRegistry:
    def __init__(self) -> None:
        self._plugins: dict[str, PluginInterface] = {}

    def register(self, plugin: PluginInterface) -> None:
        self._plugins[f"{plugin.plugin_id}:{plugin.version}"] = plugin

    def get(self, plugin_id: str, version: str) -> PluginInterface:
        key = f"{plugin_id}:{version}"
        plugin = self._plugins.get(key)
        if plugin is None:
            raise KeyError(f"Plugin not registered: {key}")
        return plugin

    def list_plugins(self) -> list[str]:
        return sorted(self._plugins.keys())
