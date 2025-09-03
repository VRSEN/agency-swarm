"""
Tool concurrency management for agents.

This module provides the ToolConcurrencyManager class for managing one-call-at-a-time
tool execution constraints within individual agent instances.
"""

from typing import NamedTuple


class LockState(NamedTuple):
    """Represents the state of a concurrency lock."""

    busy: bool
    owner: str | None


class ToolConcurrencyManager:
    """
    Manages tool concurrency for a single agent instance.

    Provides tracking of tool execution state to enforce
    one-call-at-a-time constraints for tools that require sequential execution.
    """

    def __init__(self) -> None:
        self._lock_state = LockState(busy=False, owner=None)
        self._active_count = 0

    def is_lock_active(self) -> tuple[bool, str | None]:
        """
        Check if the one-call lock is currently active.

        Returns:
            Tuple of (is_active, owner_name)
        """
        return self._lock_state.busy, self._lock_state.owner

    def acquire_lock(self, owner: str | None) -> None:
        """
        Acquire the one-call lock for the specified owner.

        Args:
            owner: Name of the tool acquiring the lock
        """
        self._lock_state = LockState(busy=True, owner=owner)

    def release_lock(self) -> None:
        """Release the one-call lock."""
        self._lock_state = LockState(busy=False, owner=None)

    def get_active_count(self) -> int:
        """Get the current number of active tool executions."""
        return self._active_count

    def increment_active_count(self) -> None:
        """Increment the active tool count."""
        self._active_count += 1

    def decrement_active_count(self) -> None:
        """Decrement the active tool count, ensuring it doesn't go below zero."""
        if self._active_count > 0:
            self._active_count -= 1
