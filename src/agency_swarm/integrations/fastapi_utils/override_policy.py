import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from agents.models._openai_shared import get_default_openai_client
from openai import AsyncOpenAI

from agency_swarm import Agency, Agent
from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

logger = logging.getLogger(__name__)


def _get_openai_client_from_agent(agent: Agent) -> AsyncOpenAI | None:
    """Return the agent's current OpenAI client, if directly accessible."""
    model = agent.model
    for attr in ("openai_client", "client", "_client"):
        maybe = getattr(model, attr, None)
        if isinstance(maybe, AsyncOpenAI):
            return maybe
    return None


def _get_upload_client_agent(agency: Agency, recipient_agent: str | None = None) -> Agent | None:
    """Resolve the agent context used to derive upload/chat-name OpenAI client settings."""
    if recipient_agent:
        selected = agency.agents.get(recipient_agent)
        if selected is not None:
            return selected

    entry_points = getattr(agency, "entry_points", None)
    if isinstance(entry_points, list) and entry_points:
        first_entry = entry_points[0]
        if isinstance(first_entry, Agent):
            return first_entry
        entry_name = getattr(first_entry, "name", None)
        if isinstance(entry_name, str):
            selected = agency.agents.get(entry_name)
            if selected is not None:
                return selected

    if len(agency.agents) == 1:
        return next(iter(agency.agents.values()))

    return None


def get_allowed_dirs_for_metadata(allowed_local_dirs: Sequence[str | Path]) -> list[str]:
    """Return validated allowlist entries without expanding them into resolved server paths."""
    visible_dirs: list[str] = []
    for entry in allowed_local_dirs:
        path = Path(entry).expanduser()
        if not path.exists():
            logger.warning("Allowed directory not found (skipping): %s", entry)
            continue
        if not path.is_dir():
            logger.warning("Allowed path must be a directory (skipping): %s", entry)
            continue
        visible_dirs.append(str(entry))
    return visible_dirs


@dataclass(frozen=True)
class RequestOverridePolicy:
    """Shared policy for request-level client overrides across FastAPI handlers."""

    config: ClientConfig | None

    @property
    def has_client_overrides(self) -> bool:
        return self.config is not None and (
            self.config.base_url is not None
            or self.config.api_key is not None
            or self.config.default_headers is not None
            or self.config.litellm_keys is not None
        )

    @property
    def has_openai_overrides(self) -> bool:
        return self.config is not None and (
            self.config.base_url is not None
            or self.config.api_key is not None
            or self.config.default_headers is not None
        )

    def build_file_upload_client(
        self,
        agency: Agency,
        recipient_agent: str | None = None,
    ) -> AsyncOpenAI | None:
        """Build a request-scoped OpenAI client for uploads/chat-name when needed."""
        if not self.has_openai_overrides:
            return None

        assert self.config is not None

        base_client: AsyncOpenAI | None = None
        selected_agent = _get_upload_client_agent(agency, recipient_agent=recipient_agent)
        if selected_agent is not None:
            base_client = _get_openai_client_from_agent(selected_agent)
            if base_client is None:
                cached_client = getattr(selected_agent, "_openai_client", None)
                if isinstance(cached_client, AsyncOpenAI):
                    base_client = cached_client

        if base_client is None:
            base_client = get_default_openai_client()

        if base_client is None:
            if self.config.api_key is None:
                # No baseline client and no request api_key: fall back to default env behavior.
                return None
            return AsyncOpenAI(
                api_key=self.config.api_key,
                base_url=self.config.base_url,
                default_headers=self.config.default_headers,
            )

        return base_client.copy(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            default_headers=self.config.default_headers,
        )
