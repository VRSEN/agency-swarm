"""Integration tests for IPythonInterpreter tool with agent isolation."""
import pytest
from agents.run_context import RunContextWrapper

from agency_swarm import Agent
from agency_swarm.context import MasterContext
from agency_swarm.tools.built_in import IPythonInterpreter
from agency_swarm.utils.thread import ThreadManager


@pytest.fixture
def shared_context():
    """Create a shared context wrapped for tools to persist state."""
    thread_manager = ThreadManager()
    master_context = MasterContext(
        thread_manager=thread_manager,
        agents={},
        user_context={},
    )
    return RunContextWrapper(context=master_context)


@pytest.fixture
def agent_with_ipython():
    """Create an agent with IPython interpreter tool."""
    return Agent(
        name="TestAgent",
        description="Test agent with IPython interpreter",
        instructions="Execute Python code when requested",
        tools=[IPythonInterpreter],
    )


class TestIPythonInterpreterPersistence:
    """Test that state persists within same agent across multiple executions."""

    @pytest.mark.asyncio
    async def test_variable_persistence(self, agent_with_ipython, shared_context):
        """Test that variables persist across tool executions."""
        tool1 = IPythonInterpreter(code="my_var = 100")
        tool1._caller_agent = agent_with_ipython
        tool1._context = shared_context
        result1 = await tool1.run()
        assert "Error:" not in result1

        tool2 = IPythonInterpreter(code="my_var * 2")
        tool2._caller_agent = agent_with_ipython
        tool2._context = shared_context
        result2 = await tool2.run()

        assert "200" in result2

    @pytest.mark.asyncio
    async def test_import_persistence(self, agent_with_ipython, shared_context):
        """Test that imports persist and can be reused."""
        tool1 = IPythonInterpreter(code="import math")
        tool1._caller_agent = agent_with_ipython
        tool1._context = shared_context
        await tool1.run()

        tool2 = IPythonInterpreter(code="math.sqrt(16)")
        tool2._caller_agent = agent_with_ipython
        tool2._context = shared_context
        result2 = await tool2.run()

        assert "4" in result2

    @pytest.mark.asyncio
    async def test_function_definition_persistence(self, agent_with_ipython, shared_context):
        """Test that function definitions persist across executions."""
        code_def = """
def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)
"""
        tool1 = IPythonInterpreter(code=code_def)
        tool1._caller_agent = agent_with_ipython
        tool1._context = shared_context
        await tool1.run()

        tool2 = IPythonInterpreter(code="fibonacci(10)")
        tool2._caller_agent = agent_with_ipython
        tool2._context = shared_context
        result2 = await tool2.run()

        assert "55" in result2


class TestIPythonInterpreterAgentIsolation:
    """Test that agents have fully isolated execution environments (core feature)."""

    @pytest.mark.asyncio
    async def test_module_mutation_isolation(self):
        """Test that module mutations in one agent don't leak to another."""
        agent_a = Agent(name="AgentA", description="First", instructions="", tools=[IPythonInterpreter])
        agent_b = Agent(name="AgentB", description="Second", instructions="", tools=[IPythonInterpreter])

        # Agent A mutates math module by adding custom attribute
        tool_a = IPythonInterpreter(code="import math; math.CUSTOM_X = 999; math.CUSTOM_X")
        tool_a._caller_agent = agent_a
        result_a = await tool_a.run()
        assert "999" in result_a

        # Agent B checks if mutation is visible - it should NOT be
        tool_b = IPythonInterpreter(code="import math; hasattr(math, 'CUSTOM_X')")
        tool_b._caller_agent = agent_b
        result_b = await tool_b.run()

        assert "False" in result_b

    @pytest.mark.asyncio
    async def test_variable_isolation_between_agents(self):
        """Test that variables are completely isolated between agents."""
        agent_a = Agent(name="AgentA", description="", instructions="", tools=[IPythonInterpreter])
        agent_b = Agent(name="AgentB", description="", instructions="", tools=[IPythonInterpreter])

        # Agent A defines secret variable
        tool_a = IPythonInterpreter(code="secret_value = 12345; len(dir())")
        tool_a._caller_agent = agent_a
        result_a = await tool_a.run()
        assert "Error:" not in result_a

        # Agent B tries to access it - should not exist
        tool_b = IPythonInterpreter(code="'secret_value' in dir()")
        tool_b._caller_agent = agent_b
        result_b = await tool_b.run()

        assert "False" in result_b

    @pytest.mark.asyncio
    async def test_concurrent_execution_isolation(self):
        """Test that concurrent executions on different agents maintain isolation."""
        import asyncio

        agent_a = Agent(name="AgentA", description="", instructions="", tools=[IPythonInterpreter])
        agent_b = Agent(name="AgentB", description="", instructions="", tools=[IPythonInterpreter])

        # Execute code concurrently - each sets different value for same variable name
        tool_a = IPythonInterpreter(code="x = 1; import time; time.sleep(0.05); x")
        tool_a._caller_agent = agent_a

        tool_b = IPythonInterpreter(code="x = 100; import time; time.sleep(0.05); x")
        tool_b._caller_agent = agent_b

        results = await asyncio.gather(tool_a.run(), tool_b.run())

        # Each agent should see only its own value
        assert "1" in results[0]
        assert "100" in results[1]

    @pytest.mark.asyncio
    async def test_sys_path_isolation(self):
        """Test that sys.path modifications don't leak between agents."""
        agent_a = Agent(name="AgentA", description="", instructions="", tools=[IPythonInterpreter])
        agent_b = Agent(name="AgentB", description="", instructions="", tools=[IPythonInterpreter])

        code_a = "import sys; sys.path.insert(0, '/unique/test/path'); '/unique/test/path' in sys.path"
        tool_a = IPythonInterpreter(code=code_a)
        tool_a._caller_agent = agent_a
        result_a = await tool_a.run()
        assert "True" in result_a

        tool_b = IPythonInterpreter(code="import sys; '/unique/test/path' in sys.path")
        tool_b._caller_agent = agent_b
        result_b = await tool_b.run()

        assert "False" in result_b

    @pytest.mark.asyncio
    async def test_global_module_attribute_isolation(self):
        """Test that adding attributes to built-in modules doesn't leak."""
        agent_a = Agent(name="AgentA", description="", instructions="", tools=[IPythonInterpreter])
        agent_b = Agent(name="AgentB", description="", instructions="", tools=[IPythonInterpreter])

        # Agent A adds attribute to sys module
        tool_a = IPythonInterpreter(code="import sys; sys._test_attr = 'agent_a_data'; hasattr(sys, '_test_attr')")
        tool_a._caller_agent = agent_a
        result_a = await tool_a.run()
        assert "True" in result_a

        # Agent B should not see this attribute
        tool_b = IPythonInterpreter(code="import sys; hasattr(sys, '_test_attr')")
        tool_b._caller_agent = agent_b
        result_b = await tool_b.run()

        assert "False" in result_b


class TestIPythonInterpreterEdgeCases:
    """Test edge cases, error handling, and special scenarios."""

    @pytest.mark.asyncio
    async def test_error_handling_with_traceback(self, agent_with_ipython, shared_context):
        """Test that errors return proper traceback information."""
        code = """
def buggy_function():
    return 1 / 0

buggy_function()
"""
        tool = IPythonInterpreter(code=code)
        tool._caller_agent = agent_with_ipython
        tool._context = shared_context

        result = await tool.run()

        assert "Error:" in result
        assert "ZeroDivisionError" in result
        assert "buggy_function" in result

    @pytest.mark.asyncio
    async def test_multiline_output_capture(self, agent_with_ipython, shared_context):
        """Test that both print output and return values are captured."""
        code = """
print('Step 1: Starting calculation')
result = 42 * 2
print(f'Step 2: Result is {result}')
result
"""
        tool = IPythonInterpreter(code=code)
        tool._caller_agent = agent_with_ipython
        tool._context = shared_context

        result = await tool.run()

        assert "Step 1" in result
        assert "Step 2" in result
        assert "84" in result

    @pytest.mark.asyncio
    async def test_no_agent_context_ephemeral_kernel(self):
        """Test that tool creates ephemeral kernel when no agent context."""
        tool = IPythonInterpreter(code="import os; os.getpid()")
        # Deliberately don't set _caller_agent or context

        result = await tool.run()

        # Should work and return a process ID
        assert "Error:" not in result
        assert result.strip()  # Non-empty result

    @pytest.mark.asyncio
    async def test_recovery_after_error(self, agent_with_ipython, shared_context):
        """Test that kernel recovers and continues working after an error."""
        # Cause an error
        tool1 = IPythonInterpreter(code="undefined_variable")
        tool1._caller_agent = agent_with_ipython
        tool1._context = shared_context
        result1 = await tool1.run()
        assert "Error:" in result1

        # Should still work after error
        tool2 = IPythonInterpreter(code="x = 100; x * 2")
        tool2._caller_agent = agent_with_ipython
        tool2._context = shared_context
        result2 = await tool2.run()

        assert "200" in result2
        assert "Error:" not in result2

    @pytest.mark.asyncio
    async def test_timeout_on_infinite_loop(self, shared_context):
        """Test that infinite loops are properly timed out."""
        # Create a custom tool class with a short timeout
        class ShortTimeoutInterpreter(IPythonInterpreter):
            class ToolConfig:
                kernel_timeout_seconds = 1.0

        agent = Agent(name="Test", description="", instructions="", tools=[ShortTimeoutInterpreter])

        tool = ShortTimeoutInterpreter(code="while True: pass")
        tool._caller_agent = agent
        tool._context = shared_context

        result = await tool.run()

        assert "Error:" in result
        assert "TimeoutError" in result or "timeout" in result.lower()

    @pytest.mark.asyncio
    async def test_large_output_handling(self, agent_with_ipython, shared_context):
        """Test that large outputs are properly captured."""
        # Generate large output
        code = "data = 'x' * 50000; print(f'Generated {len(data)} chars'); len(data)"
        tool = IPythonInterpreter(code=code)
        tool._caller_agent = agent_with_ipython
        tool._context = shared_context

        result = await tool.run()

        assert "50000" in result
        assert "Generated" in result

    @pytest.mark.asyncio
    async def test_stderr_capture(self, agent_with_ipython, shared_context):
        """Test that stderr output is captured alongside stdout."""
        code = "import sys; sys.stderr.write('Warning message\\n'); sys.stdout.write('Normal output\\n'); 'done'"
        tool = IPythonInterpreter(code=code)
        tool._caller_agent = agent_with_ipython
        tool._context = shared_context

        result = await tool.run()

        # Both stderr and stdout should be captured
        assert "Warning message" in result or "Normal output" in result
        assert "done" in result
