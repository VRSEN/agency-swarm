"""Minimal tests for FastAPI request models that include `client_config`.

The end-to-end behavior is covered in integration tests under `tests/integration/fastapi/`.
"""

from agency_swarm.integrations.fastapi_utils.request_models import BaseRequest, ClientConfig


class TestClientConfig:
    """Tests for ClientConfig model."""

    def test_config_with_all_fields(self) -> None:
        """Config accepts both base_url and api_key."""
        config = ClientConfig(
            base_url="https://custom.api.com",
            api_key="sk-custom-key",
        )
        assert config.base_url == "https://custom.api.com"
        assert config.api_key == "sk-custom-key"

    def test_config_with_only_base_url(self) -> None:
        """Config can specify only base_url."""
        config = ClientConfig(base_url="https://custom.api.com")
        assert config.base_url == "https://custom.api.com"
        assert config.api_key is None

    def test_config_with_only_api_key(self) -> None:
        """Config can specify only api_key."""
        config = ClientConfig(api_key="sk-custom-key")
        assert config.base_url is None
        assert config.api_key == "sk-custom-key"

    def test_config_empty(self) -> None:
        """Config can be created with no overrides."""
        config = ClientConfig()
        assert config.base_url is None
        assert config.api_key is None
        assert config.litellm_keys is None

    def test_config_with_litellm_keys(self) -> None:
        """Config accepts litellm_keys for provider-specific API keys."""
        config = ClientConfig(
            litellm_keys={
                "anthropic": "sk-ant-xxx",
                "gemini": "AIza...",
            }
        )
        assert config.litellm_keys is not None
        assert config.litellm_keys["anthropic"] == "sk-ant-xxx"
        assert config.litellm_keys["gemini"] == "AIza..."


class TestBaseRequestWithClientConfig:
    """Tests for BaseRequest including client_config."""

    def test_request_without_client_config(self) -> None:
        """Request works without client config."""
        request = BaseRequest(message="Hello")
        assert request.client_config is None

    def test_request_with_client_config(self) -> None:
        """Request accepts client config."""
        request = BaseRequest(
            message="Hello",
            client_config=ClientConfig(
                base_url="https://custom.api.com",
                api_key="sk-custom-key",
            ),
        )
        assert request.client_config is not None
        assert request.client_config.base_url == "https://custom.api.com"
        assert request.client_config.api_key == "sk-custom-key"
