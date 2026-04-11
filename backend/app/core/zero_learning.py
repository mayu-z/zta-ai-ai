from __future__ import annotations

import hashlib
from typing import Any


def validate_zero_learning_configuration(settings: Any) -> None:
    environment = str(getattr(settings, "environment", "development")).strip().lower()
    if environment != "production":
        return

    if not bool(getattr(settings, "slm_zero_learning_enforced", True)):
        raise RuntimeError("SLM_ZERO_LEARNING_ENFORCED must be true in production")

    header_name = str(
        getattr(settings, "slm_zero_learning_header_name", "X-ZTA-Zero-Learning")
    ).strip()
    if not header_name:
        raise RuntimeError(
            "SLM_ZERO_LEARNING_HEADER_NAME must be configured when zero-learning is enforced"
        )

    header_value = str(
        getattr(settings, "slm_zero_learning_header_value", "true")
    ).strip()
    if not header_value:
        raise RuntimeError(
            "SLM_ZERO_LEARNING_HEADER_VALUE must be configured when zero-learning is enforced"
        )


def build_zero_learning_headers(settings: Any) -> dict[str, str]:
    if not bool(getattr(settings, "slm_zero_learning_enforced", True)):
        return {}

    header_name = str(
        getattr(settings, "slm_zero_learning_header_name", "X-ZTA-Zero-Learning")
    ).strip()
    header_value = str(
        getattr(settings, "slm_zero_learning_header_value", "true")
    ).strip()

    if not header_name or not header_value:
        return {}

    return {
        header_name: header_value,
        "X-ZTA-Data-Retention": "none",
    }


def interaction_fingerprint(*, prompt: str, rendered_template: str) -> str:
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]
    template_hash = hashlib.sha256(rendered_template.encode("utf-8")).hexdigest()[:16]
    return (
        f"prompt_hash={prompt_hash} template_hash={template_hash} "
        f"prompt_chars={len(prompt)} template_chars={len(rendered_template)}"
    )
