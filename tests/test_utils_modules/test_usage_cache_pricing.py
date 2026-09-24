import json
from pathlib import Path

import pytest

from agency_swarm.utils import usage_tracking
from agency_swarm.utils.usage_tracking import UsageStats, calculate_usage_with_cost


@pytest.mark.parametrize("cache_kind", ["read", "write"])
@pytest.mark.parametrize("input_tokens", [100_000, 150_000])
@pytest.mark.parametrize("cache_price", ["missing", "free", "discounted", "tier_only"])
def test_loaded_cache_prices_match_direct_pricing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cache_kind: str,
    input_tokens: int,
    cache_price: str,
) -> None:
    price_key = "cache_read_input_token_cost" if cache_kind == "read" else "cache_creation_input_token_cost"
    model_prices = {
        "input_cost_per_token": 1e-6,
        "input_cost_per_token_above_100k_tokens": 2e-6,
        "output_cost_per_token": 3e-6,
    }
    if cache_price == "free":
        model_prices[price_key] = 0.0
    elif cache_price == "discounted":
        model_prices[price_key] = 0.5e-6
    elif cache_price == "tier_only":
        model_prices[f"{price_key}_above_100k_tokens"] = 0.75e-6
    pricing_data = {"test/model": model_prices}
    pricing_file = tmp_path / "pricing.json"
    pricing_file.write_text(json.dumps(pricing_data), encoding="utf-8")
    monkeypatch.setattr(usage_tracking, "PRICING_FILE_PATH", pricing_file)
    monkeypatch.setattr(usage_tracking, "_PRICING_DATA_CACHE", None)

    stats = UsageStats(
        request_count=1,
        input_tokens=input_tokens,
        output_tokens=1_000,
        total_tokens=input_tokens + 1_000,
        cached_tokens=40_000 if cache_kind == "read" else 0,
        cache_write_tokens=40_000 if cache_kind == "write" else 0,
    )
    input_rate = 2e-6 if input_tokens > 100_000 else 1e-6
    cache_rate = input_rate
    if cache_price == "free":
        cache_rate = 0.0
    elif cache_price == "discounted":
        cache_rate = 0.5e-6
    elif cache_price == "tier_only" and input_tokens > 100_000:
        cache_rate = 0.75e-6
    expected = (input_tokens - 40_000) * input_rate + 40_000 * cache_rate + 1_000 * 3e-6

    direct = calculate_usage_with_cost(stats, "test/model", pricing_data=pricing_data).total_cost
    loaded = calculate_usage_with_cost(stats, "test/model").total_cost

    assert direct == pytest.approx(expected)
    assert loaded == pytest.approx(expected)
