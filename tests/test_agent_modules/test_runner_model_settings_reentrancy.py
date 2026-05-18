import asyncio
import queue
import threading
from collections.abc import Coroutine
from typing import Any

import pytest
from agents import ModelSettings, RunConfig

from agency_swarm import Agency, Agent
from agency_swarm.agent.initialization import _RUNNER_COMPAT_LOCK_ATTR, use_runner_compatible_model_settings
from agency_swarm.context import MasterContext


@pytest.mark.asyncio
async def test_runner_settings_context_allows_nested_child_task_agent_run() -> None:
    """Nested SDK tool-task agent calls should not deadlock on compatibility settings."""
    agent = Agent(
        name="CompatAgent",
        instructions="Test",
        model="gpt-4.1-mini",
        model_settings=ModelSettings(temperature=0.3, max_tokens=16),
    )
    original_settings = agent.model_settings

    async with use_runner_compatible_model_settings(agent, RunConfig(model="gpt-4.1-mini")):
        assert agent.model_settings.temperature == 0.3

        with pytest.warns(UserWarning, match="does not support temperature"):
            async with use_runner_compatible_model_settings(agent, RunConfig(model="gpt-5.4-mini")):
                assert agent.model_settings.temperature is None
                assert agent.model_settings.max_tokens == 16

        assert agent.model_settings.temperature == 0.3
        assert agent.model_settings.max_tokens == 16

        async def enter_nested_run() -> None:
            with pytest.warns(UserWarning, match="does not support temperature"):
                async with use_runner_compatible_model_settings(agent, RunConfig(model="gpt-5.4-mini")):
                    assert agent.model_settings.temperature is None
                    assert agent.model_settings.max_tokens == 16

        async with asyncio.timeout(1):
            await asyncio.gather(enter_nested_run())

        assert agent.model_settings.temperature == 0.3
        assert agent.model_settings.max_tokens == 16

    assert agent.model_settings is original_settings
    assert agent.model_settings.temperature == 0.3
    assert agent.model_settings.max_tokens == 16


@pytest.mark.asyncio
async def test_runner_settings_context_serializes_sibling_child_task_agent_runs() -> None:
    """Sibling SDK tool-task agent calls should not overlap Agent settings mutations."""
    agent = Agent(
        name="CompatAgent",
        instructions="Test",
        model="gpt-4.1-mini",
        model_settings=ModelSettings(temperature=0.3, max_tokens=16),
    )
    original_settings = agent.model_settings
    first_entered = asyncio.Event()
    release_first = asyncio.Event()
    second_entered = asyncio.Event()

    async with use_runner_compatible_model_settings(agent, RunConfig(model="gpt-4.1-mini")):

        async def enter_first_nested_run() -> None:
            with pytest.warns(UserWarning, match="does not support temperature"):
                async with use_runner_compatible_model_settings(agent, RunConfig(model="gpt-5.4-mini")):
                    assert agent.model_settings.temperature is None
                    assert agent.model_settings.max_tokens == 16
                    first_entered.set()
                    await release_first.wait()
                    assert agent.model_settings.temperature is None

        async def enter_second_nested_run() -> None:
            await first_entered.wait()
            async with use_runner_compatible_model_settings(agent, RunConfig(model="gpt-4.1-mini")):
                second_entered.set()
                assert agent.model_settings.temperature == 0.3
                assert agent.model_settings.max_tokens == 16

        first_task = asyncio.create_task(enter_first_nested_run())
        second_task: asyncio.Task[None] | None = None
        try:
            async with asyncio.timeout(1):
                await first_entered.wait()
            second_task = asyncio.create_task(enter_second_nested_run())
            await asyncio.sleep(0.01)

            assert not second_entered.is_set()
            assert agent.model_settings.temperature is None

            release_first.set()
            async with asyncio.timeout(1):
                await asyncio.gather(first_task, second_task)
        finally:
            release_first.set()
            pending_tasks = [task for task in (first_task, second_task) if task is not None and not task.done()]
            if pending_tasks:
                await asyncio.gather(*pending_tasks, return_exceptions=True)

        assert second_entered.is_set()
        assert agent.model_settings.temperature == 0.3
        assert agent.model_settings.max_tokens == 16

    assert agent.model_settings is original_settings
    assert agent.model_settings.temperature == 0.3
    assert agent.model_settings.max_tokens == 16


def test_runner_settings_context_serializes_across_thread_event_loops() -> None:
    """Concurrent sync callers use separate loops but must share one Agent settings lock."""
    agent = Agent(
        name="CompatAgent",
        instructions="Test",
        model="gpt-4.1-mini",
        model_settings=ModelSettings(temperature=0.3, max_tokens=16),
    )
    original_settings = agent.model_settings
    first_entered = threading.Event()
    release_first = threading.Event()
    second_entered = threading.Event()
    errors: queue.Queue[BaseException] = queue.Queue()

    async def first_run() -> None:
        with pytest.warns(UserWarning, match="does not support temperature"):
            async with use_runner_compatible_model_settings(agent, RunConfig(model="gpt-5.4-mini")):
                assert agent.model_settings.temperature is None
                first_entered.set()
                assert await asyncio.to_thread(release_first.wait, 2)

    async def second_run() -> None:
        assert await asyncio.to_thread(first_entered.wait, 2)
        async with use_runner_compatible_model_settings(agent, RunConfig(model="gpt-4.1-mini")):
            second_entered.set()
            assert agent.model_settings.temperature == 0.3
            assert agent.model_settings.max_tokens == 16

    def run_in_thread(coro: Coroutine[Any, Any, None]) -> None:
        try:
            asyncio.run(coro)
        except BaseException as exc:
            errors.put(exc)

    first_thread = threading.Thread(target=run_in_thread, args=(first_run(),), daemon=True)
    second_thread = threading.Thread(target=run_in_thread, args=(second_run(),), daemon=True)

    first_thread.start()
    assert first_entered.wait(2)
    second_thread.start()
    assert not second_entered.wait(0.1)

    release_first.set()
    first_thread.join(2)
    second_thread.join(2)

    assert not first_thread.is_alive()
    assert not second_thread.is_alive()
    assert second_entered.is_set()
    assert not isinstance(getattr(agent, _RUNNER_COMPAT_LOCK_ATTR), asyncio.Lock)
    assert agent.model_settings is original_settings
    assert agent.model_settings.temperature == 0.3
    assert errors.empty(), list(errors.queue)


@pytest.mark.asyncio
async def test_runner_settings_context_locks_runtime_send_message_recipients() -> None:
    """Root runs should lock reciprocal SendMessage recipients before nested tool calls."""
    agent_a = Agent(
        name="AgentA",
        instructions="Test",
        model="gpt-4.1-mini",
        model_settings=ModelSettings(temperature=0.3, max_tokens=16),
    )
    agent_b = Agent(
        name="AgentB",
        instructions="Test",
        model="gpt-4.1-mini",
        model_settings=ModelSettings(temperature=0.4, max_tokens=32),
    )
    agency = Agency(agent_a, agent_b, communication_flows=[agent_a > agent_b, agent_b > agent_a])
    master_context = MasterContext(
        thread_manager=agency.thread_manager,
        agents=agency.agents,
        agent_runtime_state=agency._agent_runtime_state,
    )
    first_entered = asyncio.Event()
    release_first = asyncio.Event()
    second_entered = asyncio.Event()

    async def first_run() -> None:
        with pytest.warns(UserWarning, match="does not support temperature"):
            async with use_runner_compatible_model_settings(
                agent_a,
                RunConfig(model="gpt-5.4-mini"),
                master_context,
            ):
                assert agent_a.model_settings.temperature is None
                assert agent_b.model_settings.temperature == 0.4
                first_entered.set()
                await release_first.wait()

    async def second_run() -> None:
        await first_entered.wait()
        async with use_runner_compatible_model_settings(
            agent_b,
            RunConfig(model="gpt-4.1-mini"),
            master_context,
        ):
            second_entered.set()
            assert agent_b.model_settings.temperature == 0.4

    first_task = asyncio.create_task(first_run())
    second_task: asyncio.Task[None] | None = None
    try:
        async with asyncio.timeout(1):
            await first_entered.wait()
        second_task = asyncio.create_task(second_run())
        await asyncio.sleep(0)

        assert not second_entered.is_set()

        release_first.set()
        async with asyncio.timeout(1):
            await asyncio.gather(first_task, second_task)
    finally:
        release_first.set()
        pending_tasks = [task for task in (first_task, second_task) if task is not None and not task.done()]
        if pending_tasks:
            await asyncio.gather(*pending_tasks, return_exceptions=True)

    assert second_entered.is_set()
    assert agent_a.model_settings.temperature == 0.3
    assert agent_b.model_settings.temperature == 0.4


@pytest.mark.asyncio
async def test_runner_settings_context_allows_three_level_lock_only_descendant_run() -> None:
    """A middle SendMessage run must not hold a downstream lock-only recipient while waiting for it."""
    ceo = Agent(
        name="CEO",
        instructions="Test",
        model="gpt-4.1-mini",
        model_settings=ModelSettings(temperature=0.3, max_tokens=16),
    )
    manager = Agent(
        name="Manager",
        instructions="Test",
        model="gpt-4.1-mini",
        model_settings=ModelSettings(temperature=0.4, max_tokens=32),
    )
    worker = Agent(
        name="Worker",
        instructions="Test",
        model="gpt-4.1-mini",
        model_settings=ModelSettings(temperature=0.5, max_tokens=64),
    )
    agency = Agency(ceo, communication_flows=[ceo > manager, manager > worker])
    master_context = MasterContext(
        thread_manager=agency.thread_manager,
        agents=agency.agents,
        agent_runtime_state=agency._agent_runtime_state,
    )
    original_ceo_settings = ceo.model_settings
    original_manager_settings = manager.model_settings
    original_worker_settings = worker.model_settings
    manager_entered = asyncio.Event()
    worker_entered = asyncio.Event()

    async def enter_worker_child_run() -> None:
        with pytest.warns(UserWarning, match="does not support temperature"):
            async with use_runner_compatible_model_settings(
                worker,
                RunConfig(model="gpt-5.4-mini"),
                master_context,
            ):
                worker_entered.set()
                assert worker.model_settings.temperature is None
                assert worker.model_settings.max_tokens == 64

    async def enter_manager_child_run() -> None:
        async with use_runner_compatible_model_settings(
            manager,
            RunConfig(model="gpt-4.1-mini"),
            master_context,
        ):
            manager_entered.set()
            worker_task = asyncio.create_task(enter_worker_child_run())
            await asyncio.wait_for(worker_task, timeout=1)
            assert worker_entered.is_set()
            assert worker.model_settings is original_worker_settings
            assert manager.model_settings.temperature == 0.4

    async with use_runner_compatible_model_settings(
        ceo,
        RunConfig(model="gpt-4.1-mini"),
        master_context,
    ):
        manager_task = asyncio.create_task(enter_manager_child_run())
        await asyncio.wait_for(manager_task, timeout=1)

    assert manager_entered.is_set()
    assert worker_entered.is_set()
    assert ceo.model_settings is original_ceo_settings
    assert manager.model_settings is original_manager_settings
    assert worker.model_settings is original_worker_settings
