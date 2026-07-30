"""RunHooks that bind the per-user OAuth token contextvar for a run.

This is the first link of the OAuth storage chain: the hooks set the user contextvar
that :class:`agency_swarm.mcp.oauth.FileTokenStorage` reads on every operation to pick
the per-user token bucket.
"""

import logging
from typing import Any

from agents import RunHooks

from .oauth import _user_id_context

logger = logging.getLogger(__name__)


class OAuthStorageHooks(RunHooks):  # type: ignore[type-arg]
    """RunHooks implementation for OAuth token storage.

    Sets the user_id contextvar from MasterContext at the start of each run,
    enabling per-user token isolation in FileTokenStorage.

    Usage:
        from agency_swarm import Agency
        from agency_swarm.mcp.oauth import OAuthStorageHooks

        agency = Agency(
            [agent],
            oauth_token_path="./data",
            user_context={"user_id": "user_123"},
            hooks=[OAuthStorageHooks()],
        )
    """

    def on_run_start(self, *, context: Any, **kwargs: Any) -> None:
        """Set user_id contextvar from MasterContext at run start."""
        user_id = context.user_context.get("user_id") if hasattr(context, "user_context") else None
        _user_id_context.set(user_id)
        logger.debug(f"OAuth user_id context set to: {user_id}")

    def on_run_end(self, *, context: Any, result: Any, **kwargs: Any) -> None:
        """Clear user_id contextvar at run end."""
        _user_id_context.set(None)
        logger.debug("OAuth user_id context cleared")

    async def on_agent_start(self, context: Any, agent: Any) -> None:
        """Bridge the current Agents SDK hook to the legacy run-start behavior."""
        self.on_run_start(context=context.context)

    async def on_agent_end(self, context: Any, agent: Any, output: Any) -> None:
        """Bridge the current Agents SDK hook to the legacy run-end behavior."""
        self.on_run_end(context=context.context, result=output)
