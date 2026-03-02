"""Minimal tests for FastAPI request models that include `client_config`.

The end-to-end behavior is covered in integration tests under `tests/integration/fastapi/`.
"""

from agency_swarm.integrations.fastapi_utils.request_models import BaseRequest, ClientConfig


class TestClientConfig:
    """Tests for ClientConfig model."""

    def test_config_field_combinations(self) -> None:
        """Config should accept supported override combinations."""
        cases = [
            (
                {"base_url": "https://custom.api.com", "api_key": "sk-custom-key"},
                {"base_url": "https://custom.api.com", "api_key": "sk-custom-key", "litellm_keys": None},
            ),
            (
                {"base_url": "https://custom.api.com"},
                {"base_url": "https://custom.api.com", "api_key": None, "litellm_keys": None},
            ),
            (
                {"api_key": "sk-custom-key"},
                {"base_url": None, "api_key": "sk-custom-key", "litellm_keys": None},
            ),
            (
                {},
                {"base_url": None, "api_key": None, "litellm_keys": None},
            ),
            (
                {"litellm_keys": {"anthropic": "sk-ant-xxx", "gemini": "AIza..."}},
                {
                    "base_url": None,
                    "api_key": None,
                    "litellm_keys": {"anthropic": "sk-ant-xxx", "gemini": "AIza..."},
                },
            ),
        ]
        for payload, expected in cases:
            config = ClientConfig(**payload)
            assert config.base_url == expected["base_url"]
            assert config.api_key == expected["api_key"]
            assert config.litellm_keys == expected["litellm_keys"]


class TestBaseRequestWithClientConfig:
    """Tests for BaseRequest including client_config."""

    def test_request_client_config_passthrough(self) -> None:
        """BaseRequest should preserve optional ClientConfig payloads."""
        request_without_config = BaseRequest(message="Hello")
        assert request_without_config.client_config is None

        request_with_config = BaseRequest(
            message="Hello",
            client_config=ClientConfig(
                base_url="https://custom.api.com",
                api_key="sk-custom-key",
            ),
        )
        assert request_with_config.client_config is not None
        assert request_with_config.client_config.base_url == "https://custom.api.com"
        assert request_with_config.client_config.api_key == "sk-custom-key"
