"""Agency Swarm adaptations for the MCP SDK OAuth provider."""

import contextlib
import logging
from collections.abc import AsyncGenerator

import httpx
from mcp.client.auth import OAuthClientProvider
from mcp.client.auth.utils import create_client_registration_request
from mcp.shared.auth import OAuthClientMetadata
from pydantic import PrivateAttr

logger = logging.getLogger(__name__)


class _ConfiguredScopeMetadata(OAuthClientMetadata):
    """Keep an explicitly configured scope when the MCP SDK applies discovery."""

    _scope_is_authoritative: bool = PrivateAttr(default=False)
    _configured_scope: str | None = PrivateAttr(default=None)
    _configured_scope_names: frozenset[str] = PrivateAttr(default_factory=frozenset)
    _warned_advertisements: set[str] = PrivateAttr(default_factory=set)

    def make_scope_authoritative(self, scope: str | None) -> None:
        """Lock this metadata to the configured scope string."""
        self._configured_scope = scope
        self._configured_scope_names = frozenset(scope.split()) if scope else frozenset()
        self._scope_is_authoritative = True

    def __setattr__(self, name: str, value: object) -> None:
        if name == "scope" and self._scope_is_authoritative:
            advertised_scope = value if isinstance(value, str) else None
            if advertised_scope and advertised_scope not in self._warned_advertisements:
                self._warned_advertisements.add(advertised_scope)
                advertised_names = frozenset(advertised_scope.split())
                unsupported = sorted(self._configured_scope_names - advertised_names)
                if unsupported:
                    logger.warning(
                        "Configured OAuth scope(s) %s were not advertised for this OAuth request; "
                        "keeping explicit scope(s) %s instead of discovered scope(s) %s.",
                        unsupported,
                        sorted(self._configured_scope_names),
                        sorted(advertised_names),
                    )
            value = self._configured_scope
        super().__setattr__(name, value)


def preserve_configured_scopes(
    metadata: OAuthClientMetadata,
    configured_scopes: list[str] | None,
) -> OAuthClientMetadata:
    """Make configured scopes authoritative while leaving omitted scopes discoverable."""
    if configured_scopes is None and metadata.scope is None:
        return metadata

    scope = " ".join(configured_scopes) if configured_scopes is not None else metadata.scope
    values = metadata.model_dump(mode="python")
    values["scope"] = scope
    protected_metadata = _ConfiguredScopeMetadata.model_validate(values)
    protected_metadata.make_scope_authoritative(scope)
    return protected_metadata


class ErrorCapturingOAuthClientProvider(OAuthClientProvider):
    """Remember OAuth flow errors that the MCP HTTP writer logs and swallows."""

    _last_flow_error: Exception | None = None

    def pop_last_flow_error(self) -> Exception | None:
        """Return and clear the last OAuth flow error."""
        error = self._last_flow_error
        self._last_flow_error = None
        return error

    def _registration_for_server(self, request: httpx.Request) -> httpx.Request:
        """Register as a public PKCE client when no auth method is set and the server supports it.

        Servers such as Notion otherwise issue client_secret_basic, and the MCP SDK then sends two
        client auth methods in the token request (modelcontextprotocol/python-sdk#3138).
        """
        client_metadata = self.context.client_metadata
        server_metadata = self.context.oauth_metadata
        if (
            request.method != "POST"
            or self.context.client_info is not None
            or client_metadata.token_endpoint_auth_method is not None
            or server_metadata is None
            or "none" not in (server_metadata.token_endpoint_auth_methods_supported or [])
        ):
            return request
        base_url = self.context.get_authorization_base_url(self.context.server_url)
        registration = create_client_registration_request(server_metadata, client_metadata, base_url)
        if request.url != registration.url:
            return request
        logger.debug("Registering OAuth client for %s as a public client", self.context.server_url)
        public_client = client_metadata.model_copy(update={"token_endpoint_auth_method": "none"})
        return create_client_registration_request(server_metadata, public_client, base_url)

    async def async_auth_flow(
        self,
        request: httpx.Request,
    ) -> AsyncGenerator[httpx.Request, httpx.Response]:
        """Proxy the SDK flow while retaining its original exception."""
        self._last_flow_error = None
        flow = super().async_auth_flow(request)
        try:
            next_request = await anext(flow)
            while True:
                response = yield self._registration_for_server(next_request)
                next_request = await flow.asend(response)
        except StopAsyncIteration:
            return
        except Exception as exc:
            self._last_flow_error = exc
            raise
        finally:
            with contextlib.suppress(Exception):
                await flow.aclose()
