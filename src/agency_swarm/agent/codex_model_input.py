from __future__ import annotations

import inspect
from dataclasses import replace
from typing import Any, cast

from agents import TResponseInputItem
from agents.run_config import CallModelData, ModelInputData, RunConfig

from agency_swarm.messages.codex_input import agent_uses_codex_browser_auth, rewrite_system_input_roles_for_codex


def with_codex_model_input_role_rewrite(run_config: RunConfig) -> RunConfig:
    """Return a RunConfig that rewrites Codex-bound system input at the model-call boundary."""
    existing_filter = run_config.call_model_input_filter

    async def codex_input_filter(data: CallModelData[Any]) -> ModelInputData:
        model_data = data.model_data
        if existing_filter is not None:
            maybe_updated = existing_filter(data)
            model_data = await maybe_updated if inspect.isawaitable(maybe_updated) else maybe_updated

        if not isinstance(model_data, ModelInputData):
            return model_data

        if not agent_uses_codex_browser_auth(data.agent, run_config):
            return model_data

        return ModelInputData(
            input=cast(
                list[TResponseInputItem],
                rewrite_system_input_roles_for_codex(cast(list[dict[str, Any]], model_data.input)),
            ),
            instructions=model_data.instructions,
        )

    return replace(run_config, call_model_input_filter=codex_input_filter)
