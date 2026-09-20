"""Tests for realtime provider/model resolution and bundled pricing coverage."""

from agency_swarm.integrations.realtime_config import (
    OPENAI_DEFAULT_REALTIME_MODEL,
    XAI_DEFAULT_REALTIME_MODEL,
    build_model_settings,
)
from agency_swarm.utils.usage_tracking import calculate_openai_cost, get_model_pricing, load_pricing_data


def _settings_for(model: str | None, provider: str = "openai") -> dict[str, object]:
    return dict(
        build_model_settings(
            model=model,
            voice=None,
            input_audio_format=None,
            output_audio_format=None,
            turn_detection=None,
            input_audio_noise_reduction=None,
            provider=provider,
        )
    )


def test_build_model_settings_defaults_openai_model_to_gpt_realtime_2() -> None:
    assert OPENAI_DEFAULT_REALTIME_MODEL == "gpt-realtime-2"
    assert _settings_for(None)["model_name"] == "gpt-realtime-2"


def test_build_model_settings_keeps_explicit_openai_model() -> None:
    assert _settings_for("gpt-realtime-1.5")["model_name"] == "gpt-realtime-1.5"


def test_build_model_settings_defaults_xai_model() -> None:
    assert _settings_for(None, provider="xai")["model_name"] == XAI_DEFAULT_REALTIME_MODEL


def test_default_openai_realtime_model_has_bundled_pricing() -> None:
    """The realtime default must price exactly, not through the gpt-realtime suffix fallback."""
    pricing_data = load_pricing_data()

    assert OPENAI_DEFAULT_REALTIME_MODEL in pricing_data
    pricing = get_model_pricing(OPENAI_DEFAULT_REALTIME_MODEL, pricing_data)
    assert pricing is not None
    assert pricing["input_cost_per_token"] == 4e-06
    assert pricing["output_cost_per_token"] == 2.4e-05
    assert calculate_openai_cost(OPENAI_DEFAULT_REALTIME_MODEL, 1000, 1000, pricing_data=pricing_data) > 0.0
