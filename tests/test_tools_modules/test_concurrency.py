"""Unit tests for tool concurrency state management."""

from agency_swarm.tools.concurrency import ToolConcurrencyManager


def test_acquire_and_release_lock_tracks_owner() -> None:
    manager = ToolConcurrencyManager()

    manager.acquire_lock("exclusive_tool")
    busy, owner = manager.is_lock_active()
    assert busy is True
    assert owner == "exclusive_tool"

    manager.release_lock()
    busy, owner = manager.is_lock_active()
    assert busy is False
    assert owner is None


def test_lock_accepts_none_owner() -> None:
    manager = ToolConcurrencyManager()

    manager.acquire_lock(None)
    busy, owner = manager.is_lock_active()
    assert busy is True
    assert owner is None


def test_active_count_tracks_increments_and_prevents_underflow() -> None:
    manager = ToolConcurrencyManager()

    manager.increment_active_count()
    manager.increment_active_count()
    assert manager.get_active_count() == 2

    manager.decrement_active_count()
    manager.decrement_active_count()
    manager.decrement_active_count()
    assert manager.get_active_count() == 0


def test_lock_state_does_not_change_active_count() -> None:
    manager = ToolConcurrencyManager()
    manager.increment_active_count()
    manager.increment_active_count()

    manager.acquire_lock("tool")
    assert manager.get_active_count() == 2

    manager.release_lock()
    assert manager.get_active_count() == 2
