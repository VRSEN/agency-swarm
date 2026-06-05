"""Run context helpers and deprecated agency-context compatibility.

The deprecated Agency.user_context sync-back path is isolated here so the next
breaking release can remove it without changing the run-scoped context flow.
"""

from typing import TYPE_CHECKING, Any

from agency_swarm.context import MasterContext

if TYPE_CHECKING:
    from agency_swarm.agent.core import AgencyContext


def resolve_latest_shared_instructions(agency_context: "AgencyContext | None") -> str | None:
    """Return the freshest shared instructions and keep the context in sync."""
    if not agency_context:
        return None

    agency_instance = getattr(agency_context, "agency_instance", None)
    if agency_instance and hasattr(agency_instance, "shared_instructions"):
        latest = getattr(agency_instance, "shared_instructions", None)
        normalized = latest if isinstance(latest, str) else None
        normalized = normalized or None
        agency_context.shared_instructions = normalized
        return normalized

    existing = agency_context.shared_instructions
    if isinstance(existing, str):
        normalized = existing or None
        agency_context.shared_instructions = normalized
        return normalized

    agency_context.shared_instructions = None
    return None


def get_agency_user_context_store(agency_instance: object) -> dict[str, Any] | None:
    """Return the mutable context store used for legacy agency-level state."""
    shared_run_user_context = getattr(agency_instance, "_shared_run_user_context", None)
    if isinstance(shared_run_user_context, dict):
        return shared_run_user_context

    initial_user_context = getattr(agency_instance, "_initial_user_context", None)
    if isinstance(initial_user_context, dict):
        return initial_user_context

    legacy_user_context = getattr(agency_instance, "user_context", None)
    if isinstance(legacy_user_context, dict):
        return legacy_user_context

    return None


def sync_context_back_to_agency(
    context_override: dict[str, Any] | None,
    agency_context: "AgencyContext | None",
    master_context_for_run: MasterContext,
) -> None:
    """Preserve legacy Agency.user_context sync-back for override runs."""
    if not context_override or not agency_context or not agency_context.agency_instance:
        return

    base_user_context = get_agency_user_context_store(agency_context.agency_instance)
    if base_user_context is None:
        return

    for key, value in master_context_for_run.user_context.items():
        if key not in context_override:
            base_user_context[key] = value
