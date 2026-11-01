"""Keep traces away from OpenAI when ``OPENAI_BASE_URL`` points elsewhere.

The Agents SDK's default trace processor (``BatchTraceProcessor`` with
``BackendSpanExporter``) uploads traces to ``https://api.openai.com/v1/traces/ingest``
with ``OPENAI_API_KEY``, wherever ``OPENAI_BASE_URL`` sends model calls
(openai/openai-agents-python#5291). With a custom ``OPENAI_BASE_URL`` that key
belongs to the other endpoint, so the upload would send prompts and the key to OpenAI.

This module only removes that default processor through the SDK's
``set_trace_processors``. Spans are still created, and processors added later with
``add_trace_processor`` or ``set_trace_processors`` receive them.
"""

import logging
import os

from agents import set_trace_processors
from agents.models.openai_client_utils import is_official_openai_base_url
from agents.tracing import setup as tracing_setup

logger = logging.getLogger(__name__)

# OPENAI_AGENTS_DISABLE_TRACING values that keep SDK tracing on. The SDK lowercases the
# value and turns tracing off only for "1" or "true", so any other value, an empty one
# included, is not an opt-in to the OpenAI upload.
_OPT_IN_VALUES = ("0", "false")


def skip_openai_trace_upload_for_custom_base_url() -> bool:
    """Remove the SDK's OpenAI trace upload when ``OPENAI_BASE_URL`` is not OpenAI.

    Leaves tracing as the SDK configures it when ``OPENAI_AGENTS_DISABLE_TRACING`` is
    ``0`` or ``false``, or when tracing was set up before Agency Swarm was imported.

    Returns:
        True when the default OpenAI trace upload was removed.
    """
    base_url = os.environ.get("OPENAI_BASE_URL")
    if not base_url or is_official_openai_base_url(base_url):
        return False
    if os.environ.get("OPENAI_AGENTS_DISABLE_TRACING", "").lower() in _OPT_IN_VALUES:
        return False
    # The SDK has no public check; get_trace_provider() would create the provider.
    if tracing_setup.GLOBAL_TRACE_PROVIDER is not None:
        return False
    set_trace_processors([])
    logger.info(
        "OPENAI_BASE_URL is not api.openai.com, so traces are not uploaded to OpenAI. "
        "Set OPENAI_AGENTS_DISABLE_TRACING=0 to keep the Agents SDK default."
    )
    return True
