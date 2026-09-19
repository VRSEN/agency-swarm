"""Tests for the deprecated ``Agency.user_context`` compatibility path.

The attribute keeps working until the next major release: it warns on
construction, set, and access, while internally routing through the same store
``context_override`` merges into for each run.
"""

import warnings

import pytest
from agents import ModelSettings, RunContextWrapper, function_tool

from agency_swarm import Agency, Agent, MasterContext
from tests.deterministic_model import DeterministicModel


@function_tool
async def store_data(ctx: RunContextWrapper[MasterContext], key: str, value: str) -> str:
    """Store data in the shared context."""
    ctx.context.set(key, value)
    return f"Stored {key}={value}"


@function_tool
async def get_data(ctx: RunContextWrapper[MasterContext], key: str) -> str:
    """Get data from the shared context."""
    value = ctx.context.get(key)
    return f"Value for {key}: {value}"


def _context_agent(name: str = "ContextAgent") -> Agent:
    return Agent(
        name=name,
        instructions="You store and retrieve data using the provided tools.",
        tools=[store_data, get_data],
        model=DeterministicModel(),
        model_settings=ModelSettings(tool_choice="required"),
        tool_use_behavior="stop_on_first_tool",
    )


def test_agency_init_without_user_context_does_not_warn() -> None:
    """A clean agency emits no deprecation warnings."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        agency = Agency(_context_agent())

    assert not [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert agency._initial_user_context == {}


def test_agency_init_user_context_param_warns() -> None:
    """``Agency(user_context=...)`` warns once and still seeds the store."""
    with pytest.warns(DeprecationWarning, match="Agency\\(user_context=...\\)"):
        agency = Agency(_context_agent(), user_context={"initial": "seed"})

    assert agency._initial_user_context == {"initial": "seed"}


def test_agency_user_context_get_and_set_warn() -> None:
    """Direct attribute access warns on both read and write."""
    agency = Agency(_context_agent())

    with pytest.warns(DeprecationWarning, match="`Agency.user_context` is deprecated"):
        agency.user_context = {"key": "value"}
    assert agency._initial_user_context == {"key": "value"}

    with pytest.warns(DeprecationWarning, match="`Agency.user_context` is deprecated"):
        assert agency.user_context == {"key": "value"}


@pytest.mark.asyncio
async def test_deprecated_seed_reaches_run_context_and_still_syncs_back() -> None:
    """The deprecated seed feeds ``MasterContext.user_context`` and run writes
    keep landing in the agency store until removal."""
    with pytest.warns(DeprecationWarning, match="Agency\\(user_context=...\\)"):
        agency = Agency(_context_agent(), user_context={"initial": "seed"})

    result = await agency.get_response("Store stored_key with value stored_value")

    run_context = result.context_wrapper.context.user_context
    assert run_context["initial"] == "seed"
    assert run_context["stored_key"] == "stored_value"
    # Legacy sync-back: without context_override the run dict is the agency store.
    assert agency._initial_user_context["stored_key"] == "stored_value"

    with pytest.warns(DeprecationWarning, match="`Agency.user_context` is deprecated"):
        assert agency.user_context["stored_key"] == "stored_value"


@pytest.mark.asyncio
async def test_context_override_layers_over_deprecated_seed() -> None:
    """``context_override`` merges over the deprecated seed; legacy sync-back
    keeps non-override keys flowing into the agency store."""
    with pytest.warns(DeprecationWarning, match="Agency\\(user_context=...\\)"):
        agency = Agency(_context_agent(), user_context={"initial": "seed"})

    result = await agency.get_response(
        "Store new_key with value new_value",
        context_override={"override_key": "override_value", "initial": "shadowed"},
    )

    run_context = result.context_wrapper.context.user_context
    assert run_context["override_key"] == "override_value"
    assert run_context["initial"] == "shadowed"
    assert run_context["new_key"] == "new_value"

    # Override keys never sync back; keys the run added still do (legacy compat).
    assert "override_key" not in agency._initial_user_context
    assert agency._initial_user_context["initial"] == "seed"
    assert agency._initial_user_context["new_key"] == "new_value"


@pytest.mark.asyncio
async def test_runs_do_not_emit_deprecation_warnings_without_deprecated_use() -> None:
    """Internal run paths read the store without tripping the deprecated accessor."""
    agency = Agency(_context_agent())

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        await agency.get_response("Store key with value val")

    assert not [w for w in caught if issubclass(w.category, DeprecationWarning)]


@pytest.mark.asyncio
async def test_fastapi_rebuild_does_not_warn_after_run_accumulated_context() -> None:
    """A clean agency that only accumulated context at runtime must rebuild for
    FastAPI without tripping ``Agency(user_context=...)`` — the user never
    passed the deprecated argument."""
    from agency_swarm.agency.helpers import build_fastapi_agencies

    agency = Agency(_context_agent())
    await agency.get_response("Store key with value val")
    assert agency._initial_user_context  # run-synced keys landed in the store

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        rebuilt = next(iter(build_fastapi_agencies(agency).values()))()

    assert not [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert rebuilt._initial_user_context == agency._initial_user_context
    assert rebuilt._initial_user_context is not agency._initial_user_context
