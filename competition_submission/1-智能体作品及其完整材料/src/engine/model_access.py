from __future__ import annotations

from dataclasses import dataclass

import httpx

from config.settings import settings as environment_settings
from engine.settings import settings as engine_settings


@dataclass(frozen=True)
class EffectiveModelSettings:
    model_provider: str
    model_name: str
    model_api_base_url: str
    model_api_key: str
    model_timeout_seconds: float
    source: str = "environment"


def effective_model_settings() -> EffectiveModelSettings:
    """Read the current saved configuration from Java, with environment fallback."""
    fallback = EffectiveModelSettings(
        model_provider=environment_settings.model_provider,
        model_name=environment_settings.model_name,
        model_api_base_url=environment_settings.model_api_base_url,
        model_api_key=environment_settings.model_api_key,
        model_timeout_seconds=environment_settings.model_timeout_seconds,
    )
    if not engine_settings.service_token:
        return fallback
    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(
                f"{engine_settings.app_callback_base_url.rstrip('/')}/internal/v1/model-access-config",
                headers={"X-Service-Token": engine_settings.service_token},
            )
            response.raise_for_status()
            payload = response.json()
        return EffectiveModelSettings(
            model_provider=str(payload["provider"]),
            model_name=str(payload["modelName"]),
            model_api_base_url=str(payload["apiBaseUrl"]),
            model_api_key=str(payload.get("apiKey") or ""),
            model_timeout_seconds=float(payload["timeoutSeconds"]),
            source=str(payload.get("source") or "stored"),
        )
    except (httpx.HTTPError, KeyError, TypeError, ValueError):
        return fallback
