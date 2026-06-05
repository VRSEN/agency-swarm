import warnings
from typing import Any, Protocol


class _HasInitialUserContext(Protocol):
    _initial_user_context: dict[str, Any]


def warn_agency_user_context_init_deprecated() -> None:
    warnings.warn(
        "`Agency(user_context=...)` is deprecated and will be removed in a future release. "
        "Pass per-run context with `get_response(..., context_override=...)`, "
        "`get_response_stream(..., context_override=...)`, or construct `MasterContext` directly.",
        DeprecationWarning,
        stacklevel=3,
    )


def _get_user_context(self: _HasInitialUserContext) -> dict[str, Any]:
    warnings.warn(
        "`Agency.user_context` is deprecated and will be removed in a future release. "
        "Read run context from `RunResult.context_wrapper.context.user_context` and pass it back with "
        "`context_override` when you need caller-owned state.",
        DeprecationWarning,
        stacklevel=2,
    )
    return self._initial_user_context


def _set_user_context(self: _HasInitialUserContext, value: dict[str, Any]) -> None:
    warnings.warn(
        "`Agency.user_context` is deprecated and will be removed in a future release. "
        "Keep state outside the agency and pass it per run with `context_override`.",
        DeprecationWarning,
        stacklevel=2,
    )
    self._initial_user_context = dict(value or {})


deprecated_user_context = property(_get_user_context, _set_user_context)
