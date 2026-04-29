import logging
from typing import Any

from agents import Agent, RunHooks, RunResult
from agents.lifecycle import AgentHookContext
from agents.run_context import RunContextWrapper
from agents.tool import Tool

from .context import MasterContext
from .utils.thread import ThreadLoadCallback, ThreadSaveCallback

logger = logging.getLogger(__name__)


class CompositeRunHooks(RunHooks):
    """Compose multiple run hooks into one SDK-compatible RunHooks object."""

    def __init__(self, hooks: list[RunHooks]) -> None:
        self._hooks = hooks

    async def on_agent_start(self, context: AgentHookContext[MasterContext], agent: Agent) -> None:
        for hook in self._hooks:
            await hook.on_agent_start(context, agent)

    async def on_agent_end(self, context: AgentHookContext[MasterContext], agent: Agent, output: Any) -> None:
        for hook in self._hooks:
            await hook.on_agent_end(context, agent, output)

    async def on_handoff(
        self,
        context: RunContextWrapper[MasterContext],
        from_agent: Agent,
        to_agent: Agent,
    ) -> None:
        for hook in self._hooks:
            await hook.on_handoff(context, from_agent, to_agent)

    async def on_tool_start(self, context: RunContextWrapper[MasterContext], agent: Agent, tool: Tool) -> None:
        for hook in self._hooks:
            await hook.on_tool_start(context, agent, tool)

    async def on_tool_end(
        self,
        context: RunContextWrapper[MasterContext],
        agent: Agent,
        tool: Tool,
        result: str,
    ) -> None:
        for hook in self._hooks:
            await hook.on_tool_end(context, agent, tool, result)

    async def on_llm_start(
        self,
        context: RunContextWrapper[MasterContext],
        agent: Agent,
        system_prompt: str | None,
        input_items: list[Any],
    ) -> None:
        for hook in self._hooks:
            await hook.on_llm_start(context, agent, system_prompt, input_items)

    async def on_llm_end(
        self,
        context: RunContextWrapper[MasterContext],
        agent: Agent,
        response: Any,
    ) -> None:
        for hook in self._hooks:
            await hook.on_llm_end(context, agent, response)


class PersistenceHooks(RunHooks):
    """Custom `RunHooks` implementation for loading and saving `ThreadManager` state.

    This class integrates with the `agents.Runner` lifecycle to automatically
    save message history at the end of a run using user-provided callback
    functions. Loading relies on the `ThreadManager` initialization, which
    invokes the same callbacks to seed the in-memory store.

    Note:
        The signatures for `load_threads_callback` and `save_threads_callback` now
        work with flat message lists instead of thread dictionaries.

    Attributes:
        _load_threads_callback: The function to load all messages.
                               Expected signature: `ThreadLoadCallback`
        _save_threads_callback: The function to save all messages.
                               Expected signature: `ThreadSaveCallback`
    """

    # Type hints for flat message structure
    _load_threads_callback: ThreadLoadCallback
    _save_threads_callback: ThreadSaveCallback

    def __init__(
        self,
        load_threads_callback: ThreadLoadCallback,
        save_threads_callback: ThreadSaveCallback,
    ):
        """
        Initializes the PersistenceHooks.

        Args:
            load_threads_callback (ThreadLoadCallback):
                The function to call when initializing the run to load all
                messages. It should return a flat list of message dictionaries
                with 'agent', 'callerAgent', 'timestamp' and other OpenAI fields.
            save_threads_callback (ThreadSaveCallback):
                The function to call at the end of a run to save all messages.
                It receives a flat list of message dictionaries.

        Raises:
            TypeError: If either `load_threads_callback` or `save_threads_callback` is not callable.
        """
        if not callable(load_threads_callback) or not callable(save_threads_callback):
            raise TypeError("load_threads_callback and save_threads_callback must be callable.")
        self._load_threads_callback = load_threads_callback
        self._save_threads_callback = save_threads_callback
        logger.info("PersistenceHooks initialized with flat message structure.")

    def on_run_start(self, *, context: MasterContext, **kwargs: object) -> None:
        """Confirm the run started after `ThreadManager` performed initial load.

        The `ThreadManager` executes the configured `load_threads_callback`
        during initialization, so this hook only traces the lifecycle event to
        avoid double-loading.

        Args:
            context (MasterContext): The master context for the run, containing the `ThreadManager`.
            **kwargs: Additional keyword arguments from the run lifecycle.
        """
        logger.debug("PersistenceHooks: on_run_start triggered; message loading handled during ThreadManager init.")

    def on_run_end(self, *, context: MasterContext, result: RunResult, **kwargs: object) -> None:
        """Saves all messages from the `ThreadManager` at the end of a run.

        Calls the `save_threads_callback` provided during initialization, passing
        the complete flat list of messages from the `ThreadManager`.
        Logs errors during saving but does not prevent run completion.

        Args:
            context (MasterContext): The master context for the run, containing the `ThreadManager`.
            result (RunResult): The result object for the completed run.
            **kwargs: Additional keyword arguments from the run lifecycle.
        """
        logger.debug("PersistenceHooks: on_run_end triggered.")
        try:
            # Get flat message list from ThreadManager
            all_messages = context.thread_manager.get_all_messages()

            self._save_threads_callback(all_messages)
            logger.info(f"Saved {len(all_messages)} messages via save_threads_callback.")
        except Exception as e:
            logger.error(f"Error during save_threads_callback execution: {e}", exc_info=True)
            # Log error but don't prevent run completion.

    async def on_agent_start(self, context: AgentHookContext[MasterContext], agent: Agent) -> None:
        """Bridge the current Agents SDK hook to the legacy run-start behavior."""
        self.on_run_start(context=context.context)

    async def on_agent_end(self, context: AgentHookContext[MasterContext], agent: Agent, output: Any) -> None:
        """Bridge the current Agents SDK hook to the legacy run-end behavior."""
        self.on_run_end(context=context.context, result=output)
