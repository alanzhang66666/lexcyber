from dataclasses import dataclass

from config.settings import Settings


@dataclass(frozen=True)
class ModelRoute:
    provider: str
    model_name: str


class ModelRouter:
    """Selects model routes without coupling Graph nodes to provider SDKs."""

    def __init__(self, config: Settings):
        self.primary = ModelRoute(config.model_provider, config.model_name)
        self.backup = ModelRoute("stub", "stub-fallback-v1")

    def routes(self, task_type: str) -> list[ModelRoute]:
        _ = task_type
        return [self.primary, self.backup] if self.primary.provider != "stub" else [self.primary]
