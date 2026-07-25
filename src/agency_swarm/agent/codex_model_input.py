from __future__ import annotations

import inspect
from dataclasses import replace
from typing import Any, cast

from agents import TResponseInputItem
from agents.run_config import CallModelData, ModelInputData, RunConfig

from agency_swarm.agent.system_reminder_state import TRANSIENT_REMINDER_MARKER
from agency_swarm.agent.system_reminders import inject_pending_system_reminders
from agency_swarm.context import MasterContext
from agency_swarm.messages.codex_input import agent_uses_codex_browser_auth, rewrite_system_input_roles_for_codex


def with_codex_model_input_role_rewrite(
    run_config: RunConfig,
    *,
    reminders_as_instructions: bool = False,
) -> RunConfig:
    """Return a RunConfig that rewrites Codex-bound system input at the model-call boundary."""
    existing_filter = run_config.call_model_input_filter

    async def codex_input_filter(data: CallModelData[Any]) -> ModelInputData:
        model_data = data.model_data
        uses_codex = agent_uses_codex_browser_auth(data.agent, run_config)
        inject_pending_system_reminders(data.agent, data.context, model_data.input)
        if isinstance(data.context, MasterContext):
            data.context._system_reminder_role = "developer" if uses_codex else "system"

        if existing_filter is not None:
            maybe_updated = existing_filter(data)
            model_data = await maybe_updated if inspect.isawaitable(maybe_updated) else maybe_updated

        if not isinstance(model_data, ModelInputData):
            return model_data

        if uses_codex:
            model_data = ModelInputData(
                input=cast(
                    list[TResponseInputItem],
                    rewrite_system_input_roles_for_codex(cast(list[dict[str, Any]], model_data.input)),
                ),
                instructions=model_data.instructions,
            )

        return _finalize_transient_reminders(model_data, as_instructions=reminders_as_instructions)

    return replace(run_config, call_model_input_filter=codex_input_filter)


def _finalize_transient_reminders(
    model_data: ModelInputData,
    *,
    as_instructions: bool,
) -> ModelInputData:
    input_items: list[TResponseInputItem] = []
    reminder_texts: list[str] = []
    for item in model_data.input:
        if not isinstance(item, dict):
            input_items.append(item)
            continue

        item_with_marker = cast(dict[object, object], item)
        if item_with_marker.get(TRANSIENT_REMINDER_MARKER) is not True:
            input_items.append(item)
            continue

        clean_item = {key: value for key, value in item_with_marker.items() if key is not TRANSIENT_REMINDER_MARKER}
        if as_instructions:
            content = clean_item.get("content")
            if isinstance(content, str):
                reminder_texts.append(content)
        else:
            input_items.append(cast(TResponseInputItem, clean_item))

    instructions = model_data.instructions
    if reminder_texts:
        reminder_block = "\n\n".join(reminder_texts)
        instructions = f"{instructions}\n\n{reminder_block}" if instructions else reminder_block
    return ModelInputData(input=input_items, instructions=instructions)
