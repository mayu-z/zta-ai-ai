from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.zero_learning import (
    build_zero_learning_headers,
    interaction_fingerprint,
    validate_zero_learning_configuration,
)


def test_validate_zero_learning_configuration_rejects_disabled_in_production() -> None:
    settings = SimpleNamespace(
        environment="production",
        slm_zero_learning_enforced=False,
        slm_zero_learning_header_name="X-ZTA-Zero-Learning",
        slm_zero_learning_header_value="true",
    )

    with pytest.raises(RuntimeError):
        validate_zero_learning_configuration(settings)


def test_validate_zero_learning_configuration_allows_disabled_outside_production() -> None:
    settings = SimpleNamespace(
        environment="development",
        slm_zero_learning_enforced=False,
        slm_zero_learning_header_name="",
        slm_zero_learning_header_value="",
    )

    validate_zero_learning_configuration(settings)


def test_build_zero_learning_headers_returns_expected_defaults() -> None:
    settings = SimpleNamespace(
        slm_zero_learning_enforced=True,
        slm_zero_learning_header_name="X-ZTA-Zero-Learning",
        slm_zero_learning_header_value="true",
    )

    headers = build_zero_learning_headers(settings)

    assert headers["X-ZTA-Zero-Learning"] == "true"
    assert headers["X-ZTA-Data-Retention"] == "none"


def test_interaction_fingerprint_does_not_include_raw_prompt_or_template() -> None:
    prompt = "my sensitive prompt"
    rendered = "my sensitive rendered template"

    fingerprint = interaction_fingerprint(prompt=prompt, rendered_template=rendered)

    assert prompt not in fingerprint
    assert rendered not in fingerprint
    assert "prompt_hash=" in fingerprint
    assert "template_hash=" in fingerprint
