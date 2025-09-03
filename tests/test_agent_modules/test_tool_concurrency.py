"""Unit tests for tool concurrency management."""

import pytest

from agency_swarm.tools.concurrency import LockState, ToolConcurrencyManager


class TestLockState:
    """Test LockState NamedTuple."""

    def test_lock_state_creation(self):
        """Test creating LockState instances."""
        state = LockState(busy=True, owner="test_tool")
        assert state.busy is True
        assert state.owner == "test_tool"

    def test_lock_state_immutability(self):
        """Test that LockState is immutable."""
        state = LockState(busy=False, owner=None)
        with pytest.raises(AttributeError):
            state.busy = True  # Should raise error as NamedTuple is immutable

    def test_lock_state_equality(self):
        """Test LockState equality comparison."""
        state1 = LockState(busy=True, owner="tool1")
        state2 = LockState(busy=True, owner="tool1")
        state3 = LockState(busy=False, owner="tool1")

        assert state1 == state2
        assert state1 != state3


class TestToolConcurrencyManager:
    """Test ToolConcurrencyManager class."""

    def test_manager_initialization(self):
        """Test manager initializes with correct default state."""
        manager = ToolConcurrencyManager()

        busy, owner = manager.is_lock_active()
        assert busy is False
        assert owner is None
        assert manager.get_active_count() == 0

    def test_lock_acquisition_and_release(self):
        """Test lock acquisition and release cycle."""
        manager = ToolConcurrencyManager()

        # Initially no lock
        busy, owner = manager.is_lock_active()
        assert busy is False
        assert owner is None

        # Acquire lock
        manager.acquire_lock("test_tool")
        busy, owner = manager.is_lock_active()
        assert busy is True
        assert owner == "test_tool"

        # Release lock
        manager.release_lock()
        busy, owner = manager.is_lock_active()
        assert busy is False
        assert owner is None

    def test_lock_reacquisition(self):
        """Test that lock can be reacquired by different tools."""
        manager = ToolConcurrencyManager()

        # First tool acquires lock
        manager.acquire_lock("tool1")
        busy, owner = manager.is_lock_active()
        assert busy is True
        assert owner == "tool1"

        # Release and acquire by different tool
        manager.release_lock()
        manager.acquire_lock("tool2")
        busy, owner = manager.is_lock_active()
        assert busy is True
        assert owner == "tool2"

    def test_active_count_operations(self):
        """Test active count increment and decrement."""
        manager = ToolConcurrencyManager()

        # Initially zero
        assert manager.get_active_count() == 0

        # Increment multiple times
        manager.increment_active_count()
        assert manager.get_active_count() == 1

        manager.increment_active_count()
        assert manager.get_active_count() == 2

        manager.decrement_active_count()
        assert manager.get_active_count() == 1

        manager.decrement_active_count()
        assert manager.get_active_count() == 0

    def test_active_count_underflow_protection(self):
        """Test that active count doesn't go below zero."""
        manager = ToolConcurrencyManager()

        # Try to decrement when count is zero
        manager.decrement_active_count()
        assert manager.get_active_count() == 0

        # Multiple decrements shouldn't cause negative count
        manager.decrement_active_count()
        manager.decrement_active_count()
        assert manager.get_active_count() == 0

    def test_lock_with_none_owner(self):
        """Test lock operations with None as owner."""
        manager = ToolConcurrencyManager()

        manager.acquire_lock(None)
        busy, owner = manager.is_lock_active()
        assert busy is True
        assert owner is None

        manager.release_lock()
        busy, owner = manager.is_lock_active()
        assert busy is False
        assert owner is None

    def test_concurrent_operations_simulation(self):
        """Test simulated concurrent operations."""
        manager = ToolConcurrencyManager()

        # Simulate multiple tools starting
        manager.increment_active_count()  # Tool 1 starts
        manager.increment_active_count()  # Tool 2 starts
        assert manager.get_active_count() == 2

        # One tool acquires one_call lock
        manager.acquire_lock("exclusive_tool")
        busy, owner = manager.is_lock_active()
        assert busy is True
        assert owner == "exclusive_tool"

        # Tool 1 finishes
        manager.decrement_active_count()
        assert manager.get_active_count() == 1

        # Exclusive tool finishes
        manager.release_lock()
        manager.decrement_active_count()
        assert manager.get_active_count() == 0
        busy, owner = manager.is_lock_active()
        assert busy is False
        assert owner is None

    def test_independent_lock_and_count_state(self):
        """Test that lock state and active count are independent."""
        manager = ToolConcurrencyManager()

        # Increment count without acquiring lock
        manager.increment_active_count()
        manager.increment_active_count()
        assert manager.get_active_count() == 2

        busy, owner = manager.is_lock_active()
        assert busy is False
        assert owner is None

        # Acquire lock without changing count
        manager.acquire_lock("test_tool")
        assert manager.get_active_count() == 2  # Count unchanged

        busy, owner = manager.is_lock_active()
        assert busy is True
        assert owner == "test_tool"

        # Release lock without changing count
        manager.release_lock()
        assert manager.get_active_count() == 2  # Count still unchanged

        busy, owner = manager.is_lock_active()
        assert busy is False
        assert owner is None
