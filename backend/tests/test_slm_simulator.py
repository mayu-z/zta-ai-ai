import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.slm.simulator import SLMSimulator


def test_trim_after_last_slot_sentence_keeps_all_slots() -> None:
    content = (
        "Across institutions, [SLOT_1] students are enrolled. "
        "The year-over-year trend is [SLOT_2]. "
        "This trailing fragment should be dropped"
    )

    trimmed = SLMSimulator._trim_after_last_slot_sentence(content)

    assert "[SLOT_1]" in trimmed
    assert "[SLOT_2]" in trimmed
    assert "trailing fragment" not in trimmed
    assert trimmed.endswith(".")


def test_ensure_required_slots_appends_missing_slots() -> None:
    template = "Total enrollment is [SLOT_1]."

    ensured = SLMSimulator._ensure_required_slots(
        template,
        ["[SLOT_1]", "[SLOT_2]"],
    )

    assert "[SLOT_1]" in ensured
    assert "[SLOT_2]" in ensured
    assert "Include also" in ensured


def test_get_client_uses_mtls_transport_when_enabled(
    monkeypatch,
) -> None:
    simulator = SLMSimulator()
    fake_transport = MagicMock()

    monkeypatch.setattr(simulator.settings, "slm_api_keys", "")
    monkeypatch.setattr(simulator.settings, "slm_api_key", "test-key")
    monkeypatch.setattr(simulator.settings, "service_mtls_enabled", True)
    monkeypatch.setattr(simulator.settings, "service_mtls_client_cert_path", "/tmp/client.crt")
    monkeypatch.setattr(simulator.settings, "service_mtls_client_key_path", "/tmp/client.key")
    monkeypatch.setattr(simulator.settings, "service_mtls_ca_bundle_path", "/tmp/ca.crt")
    monkeypatch.setattr(simulator.settings, "egress_allowed_hosts", "")
    monkeypatch.setattr(
        "app.slm.simulator.build_mtls_httpx_client",
        lambda **_: fake_transport,
    )

    openai_constructor = MagicMock(return_value=object())
    monkeypatch.setitem(
        sys.modules,
        "openai",
        SimpleNamespace(OpenAI=openai_constructor),
    )

    simulator._get_client()

    kwargs = openai_constructor.call_args.kwargs
    assert "http_client" in kwargs
    assert kwargs["http_client"] is fake_transport


def test_call_slm_api_sends_zero_learning_headers_and_audit_fingerprint(
    monkeypatch,
) -> None:
    simulator = SLMSimulator()
    mock_logger = MagicMock()
    fake_create = MagicMock(
        return_value=SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="The current value is [SLOT_1].")
                )
            ]
        )
    )
    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
    )
    intent = SimpleNamespace(
        name="get_metric",
        domain="analytics",
        entity_type="institution",
        slot_keys=["record_count"],
        aggregation="count",
    )
    scope = SimpleNamespace(persona_type="executive")

    monkeypatch.setattr("app.slm.simulator.logger", mock_logger)
    monkeypatch.setattr(simulator.settings, "slm_zero_learning_enforced", True)
    monkeypatch.setattr(simulator.settings, "slm_zero_learning_header_name", "X-ZTA-Zero-Learning")
    monkeypatch.setattr(simulator.settings, "slm_zero_learning_header_value", "true")
    monkeypatch.setattr(simulator.settings, "slm_zero_learning_audit_log_enabled", True)

    rendered = simulator._call_slm_api(fake_client, intent, scope)

    assert rendered == "The current value is [SLOT_1]."
    kwargs = fake_create.call_args.kwargs
    assert kwargs["extra_headers"]["X-ZTA-Zero-Learning"] == "true"
    assert kwargs["extra_headers"]["X-ZTA-Data-Retention"] == "none"
    assert mock_logger.info.called


def test_call_slm_api_skips_zero_learning_headers_when_disabled(
    monkeypatch,
) -> None:
    simulator = SLMSimulator()
    fake_create = MagicMock(
        return_value=SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="The current value is [SLOT_1].")
                )
            ]
        )
    )
    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
    )
    intent = SimpleNamespace(
        name="get_metric",
        domain="analytics",
        entity_type="institution",
        slot_keys=["record_count"],
        aggregation="count",
    )
    scope = SimpleNamespace(persona_type="executive")

    monkeypatch.setattr(simulator.settings, "slm_zero_learning_enforced", False)

    simulator._call_slm_api(fake_client, intent, scope)

    kwargs = fake_create.call_args.kwargs
    assert kwargs["extra_headers"] == {}
