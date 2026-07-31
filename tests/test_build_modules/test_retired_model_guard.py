"""Keep the test suite off retired models that are expensive or no longer worth exercising."""

from pathlib import Path

TESTS_ROOT = Path(__file__).parents[1]

# Retired model id -> the model new tests should use instead.
RETIRED_MODELS = {"gpt-5.4-mini": "gpt-5.6-luna"}

# Files where a retired id is load-bearing: the exact string is what the test proves.
ALLOWLIST = {
    "integration/fastapi/_openclaw_test_support.py": "shared OpenClaw provider_model fixture asserted by importers",
    "integration/fastapi/test_openclaw_current_app_defaults.py": "OpenClaw model resolution and precedence",
    "integration/fastapi/test_openclaw_layout.py": "snapshot of the written OpenClaw config",
    "integration/fastapi/test_openclaw_model_auth.py": "OpenClaw alias and provider-model resolution",
    "integration/fastapi/test_openclaw_proxy_requests.py": "asserts the forwarded upstream payload model",
    "integration/fastapi/test_openclaw_proxy_streaming.py": "asserts the proxied upstream request model",
    "integration/litellm_integration/test_litellm_models.py": "LiteLLM provider-prefix routing",
    "integration/litellm_integration/test_litellm_openai_responses_history_switch.py": (
        "pairs a prefixed and a bare id to prove cross-provider history replay"
    ),
    "integration/litellm_integration/test_litellm_visualization.py": "LiteLLM provider-prefix routing",
    "test_agent_modules/test_agent_capabilities.py": "capability detection keyed to the model id",
    "test_agent_modules/test_agent_initialization.py": "provider-prefix handling and reasoning detection",
    "test_agent_modules/test_conversation_starters_cache.py": "provider-routing fingerprint contrast",
    "test_agent_modules/test_openclaw_agent.py": "OpenClaw model mapping and usage-name resolution",
    "test_fastapi_utils_modules/test_codex_input_role_boundary.py": "provider-prefix stripping and role boundaries",
    "test_messages_modules/test_message_formatter_history_protocol.py": "provider-routing matrix",
    "test_utils_modules/test_model_utils.py": "reasoning-model detection table",
    "test_utils_modules/test_usage_tracking.py": "gpt-5.4-family pricing fixture",
}

_GUARD_FILE = Path(__file__).relative_to(TESTS_ROOT).as_posix()


def _offending_lines() -> list[str]:
    """Report every non-allowlisted test line that hard-codes a retired model id."""
    offenders: list[str] = []
    for path in sorted(TESTS_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        relative = path.relative_to(TESTS_ROOT).as_posix()
        if relative == _GUARD_FILE or relative in ALLOWLIST:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for retired, replacement in RETIRED_MODELS.items():
                if retired in line:
                    offenders.append(f"tests/{relative}:{number} hard-codes '{retired}' -> use '{replacement}'")
    return offenders


def test_tests_do_not_hardcode_retired_models() -> None:
    """Fail with actionable guidance when a test pins a retired model id."""
    offenders = _offending_lines()
    assert not offenders, (
        "Retired model ids found in the test suite:\n"
        + "\n".join(offenders)
        + "\n\nUse gpt-5.6-luna instead. It is the framework default (FRAMEWORK_DEFAULT_MODEL), has a "
        "1,050,000-token context window and reasoning support, and is cheaper per token, so this is not "
        "a capability downgrade.\nIf the exact id is load-bearing - provider-prefix routing "
        "(litellm/openrouter/anthropic), OpenClaw model resolution, or a pricing or capability-detection "
        f"fixture - add the file to ALLOWLIST in tests/{_GUARD_FILE} with a one-line reason."
    )


def test_retired_model_allowlist_has_no_stale_entries() -> None:
    """Keep the allowlist honest so cleaned-up files stop granting an exemption."""
    stale: list[str] = []
    for relative in sorted(ALLOWLIST):
        path = TESTS_ROOT / relative
        assert path.is_file(), f"tests/{relative} is allowlisted but missing; drop it from ALLOWLIST"
        text = path.read_text(encoding="utf-8")
        if not any(retired in text for retired in RETIRED_MODELS):
            stale.append(relative)
    assert not stale, (
        "Allowlisted files no longer contain a retired model id; remove them from ALLOWLIST:\n"
        + "\n".join(f"tests/{entry}" for entry in stale)
    )
