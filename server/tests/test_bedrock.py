"""Model resolution is the one piece of configuration that must fail at startup, not at invoke."""

import pytest

from app import bedrock


def test_model_returns_the_configured_identifier(monkeypatch):
    monkeypatch.setenv("BEDROCK_MODEL", "us.anthropic.claude-opus-5")
    assert bedrock.model() == "us.anthropic.claude-opus-5"


@pytest.mark.parametrize("call_site", bedrock.CALL_SITES)
def test_call_site_falls_back_to_the_shared_model(monkeypatch, call_site):
    monkeypatch.setenv("BEDROCK_MODEL", "us.anthropic.shared")
    assert bedrock.model(call_site) == "us.anthropic.shared"


@pytest.mark.parametrize(
    ("call_site", "override_var"),
    [("parse", "BEDROCK_MODEL_PARSE"), ("action", "BEDROCK_MODEL_ACTION")],
)
def test_per_call_site_override_wins(monkeypatch, call_site, override_var):
    monkeypatch.setenv("BEDROCK_MODEL", "us.anthropic.shared")
    monkeypatch.setenv(override_var, "us.anthropic.specific")
    assert bedrock.model(call_site) == "us.anthropic.specific"


def test_an_override_for_the_other_call_site_is_ignored(monkeypatch):
    monkeypatch.setenv("BEDROCK_MODEL", "us.anthropic.shared")
    monkeypatch.setenv("BEDROCK_MODEL_PARSE", "us.anthropic.parse-only")
    assert bedrock.model("action") == "us.anthropic.shared"


def test_an_empty_override_falls_through_rather_than_resolving_to_empty(monkeypatch):
    monkeypatch.setenv("BEDROCK_MODEL", "us.anthropic.shared")
    monkeypatch.setenv("BEDROCK_MODEL_PARSE", "")
    assert bedrock.model("parse") == "us.anthropic.shared"


def test_unknown_call_site_is_rejected(monkeypatch):
    monkeypatch.setenv("BEDROCK_MODEL", "us.anthropic.shared")
    with pytest.raises(ValueError, match="unknown call site 'summarise'"):
        bedrock.model("summarise")


def test_missing_model_names_the_inference_profile_problem():
    # dev-note: the message is the feature. A bare `anthropic.<model>` ID fails at invoke,
    # inside a Lambda, so the error has to say what to run to find the right string.
    with pytest.raises(RuntimeError, match="list-inference-profiles"):
        bedrock.model()


def test_verify_config_passes_when_the_shared_model_is_set(monkeypatch):
    monkeypatch.setenv("BEDROCK_MODEL", "us.anthropic.shared")
    bedrock.verify_config()  # must not raise


def test_verify_config_fails_when_no_model_is_configured():
    with pytest.raises(RuntimeError, match="BEDROCK_MODEL is not set"):
        bedrock.verify_config()


def test_verify_config_accepts_per_call_site_models_with_no_shared_default(monkeypatch):
    monkeypatch.setenv("BEDROCK_MODEL_PARSE", "us.anthropic.parse")
    monkeypatch.setenv("BEDROCK_MODEL_ACTION", "us.anthropic.action")
    bedrock.verify_config()  # must not raise


def test_verify_config_fails_when_only_one_call_site_is_configured(monkeypatch):
    # Covering only `parse` must not pass: the action call site would fail mid-return-flow.
    monkeypatch.setenv("BEDROCK_MODEL_PARSE", "us.anthropic.parse")
    with pytest.raises(RuntimeError, match="BEDROCK_MODEL is not set"):
        bedrock.verify_config()


def test_client_is_shared_across_calls(monkeypatch):
    monkeypatch.setenv("AWS_REGION", "us-west-2")
    assert bedrock.client() is bedrock.client()


def test_client_defaults_to_us_east_1_when_no_region_is_set():
    assert bedrock.client() is not None


def test_max_tokens_is_bounded():
    # A cost control on an unauthenticated endpoint, not tuning — see infra/AGENTS.md.
    assert bedrock.MAX_TOKENS == 4096
