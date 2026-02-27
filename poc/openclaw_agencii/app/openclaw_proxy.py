from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

logger = logging.getLogger(__name__)

_OPENRESPONSES_ALLOWED_KEYS: set[str] = {
    "model",
    "input",
    "instructions",
    "tools",
    "tool_choice",
    "stream",
    "max_output_tokens",
    "max_tool_calls",
    "user",
    "temperature",
    "top_p",
    "metadata",
    "store",
    "previous_response_id",
    "reasoning",
    "truncation",
}

_ALLOWED_TOOL_CHOICE_VALUES = {"auto", "none", "required"}


@dataclass(frozen=True)
class OpenClawProxyConfig:
    """Configuration for forwarding OpenResponses requests to OpenClaw."""

    upstream_base_url: str
    upstream_token: str
    timeout_seconds: float = 120.0


def _to_input_content_part(part: dict[str, Any]) -> dict[str, Any]:
    if "type" in part:
        return dict(part)

    # SDK shorthand for text blocks uses only `text`.
    if "text" in part and isinstance(part["text"], str):
        return {"type": "input_text", "text": part["text"]}

    return dict(part)


def _normalize_message_item(item: dict[str, Any]) -> dict[str, Any]:
    role = item.get("role")
    content = item.get("content")

    normalized: dict[str, Any] = {
        "type": "message",
        "role": role,
        "content": content,
    }

    if isinstance(content, list):
        normalized["content"] = [_to_input_content_part(part) if isinstance(part, dict) else part for part in content]

    return normalized


def _normalize_input_items(input_items: list[Any]) -> list[Any]:
    normalized_items: list[Any] = []

    for item in input_items:
        if not isinstance(item, dict):
            raise ValueError("input list items must be objects")

        if "type" not in item and "role" in item and "content" in item:
            normalized_items.append(_normalize_message_item(item))
            continue

        if item.get("type") == "message" and isinstance(item.get("content"), list):
            item_copy = dict(item)
            item_copy["content"] = [
                _to_input_content_part(part) if isinstance(part, dict) else part for part in item_copy["content"]
            ]
            normalized_items.append(item_copy)
            continue

        normalized_items.append(dict(item))

    return normalized_items


def _normalize_tools(tools: Any) -> list[dict[str, Any]]:
    if not isinstance(tools, list):
        return []

    normalized_tools: list[dict[str, Any]] = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue

        if tool.get("type") != "function":
            continue

        function_payload = tool.get("function")
        function_name: str | None = None
        function_description: str | None = None
        function_parameters: dict[str, Any] | None = None

        if isinstance(function_payload, dict):
            raw_name = function_payload.get("name")
            if isinstance(raw_name, str) and raw_name:
                function_name = raw_name

            raw_description = function_payload.get("description")
            if isinstance(raw_description, str) and raw_description:
                function_description = raw_description

            raw_parameters = function_payload.get("parameters")
            if isinstance(raw_parameters, dict):
                function_parameters = raw_parameters

        if function_name is None:
            raw_name = tool.get("name")
            if isinstance(raw_name, str) and raw_name:
                function_name = raw_name

        if function_name is None:
            continue

        normalized_function: dict[str, Any] = {"name": function_name}
        if function_description is not None:
            normalized_function["description"] = function_description
        if function_parameters is not None:
            normalized_function["parameters"] = function_parameters

        normalized_tools.append({"type": "function", "function": normalized_function})

    return normalized_tools


def _normalize_tool_choice(tool_choice: Any) -> str | dict[str, Any] | None:
    if tool_choice is None:
        return None

    if isinstance(tool_choice, str):
        return tool_choice if tool_choice in _ALLOWED_TOOL_CHOICE_VALUES else None

    if not isinstance(tool_choice, dict):
        return None

    if tool_choice.get("type") != "function":
        return None

    function_name: str | None = None
    function_payload = tool_choice.get("function")
    if isinstance(function_payload, dict):
        raw_name = function_payload.get("name")
        if isinstance(raw_name, str) and raw_name:
            function_name = raw_name

    if function_name is None:
        raw_name = tool_choice.get("name")
        if isinstance(raw_name, str) and raw_name:
            function_name = raw_name

    if function_name is None:
        return None

    return {"type": "function", "function": {"name": function_name}}


def _normalize_metadata(metadata: Any) -> dict[str, str] | None:
    if metadata is None:
        return None

    if not isinstance(metadata, dict):
        return None

    normalized: dict[str, str] = {}
    for key, value in metadata.items():
        if not isinstance(key, str):
            continue

        if isinstance(value, str):
            normalized[key] = value
        else:
            normalized[key] = json.dumps(value, ensure_ascii=False)

    return normalized


def normalize_openresponses_payload(raw_payload: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize an OpenAI SDK payload to OpenClaw's strict OpenResponses schema."""
    payload = dict(raw_payload)

    model = payload.get("model")
    if not isinstance(model, str) or not model:
        raise ValueError("model is required and must be a non-empty string")

    if "input" not in payload:
        raise ValueError("input is required")

    input_payload = payload["input"]
    if isinstance(input_payload, list):
        normalized_input: str | list[Any] = _normalize_input_items(input_payload)
    elif isinstance(input_payload, str):
        normalized_input = input_payload
    else:
        raise ValueError("input must be a string or a list")

    normalized: dict[str, Any] = {
        "model": model,
        "input": normalized_input,
    }

    for key in _OPENRESPONSES_ALLOWED_KEYS:
        if key in {"model", "input", "tools", "tool_choice", "metadata"}:
            continue
        if key in payload:
            normalized[key] = payload[key]

    if "tools" in payload:
        normalized_tools = _normalize_tools(payload.get("tools"))
        if normalized_tools:
            normalized["tools"] = normalized_tools

    if "tool_choice" in payload:
        normalized_tool_choice = _normalize_tool_choice(payload.get("tool_choice"))
        if normalized_tool_choice is not None:
            normalized["tool_choice"] = normalized_tool_choice

    if "metadata" in payload:
        normalized_metadata = _normalize_metadata(payload.get("metadata"))
        if normalized_metadata is not None:
            normalized["metadata"] = normalized_metadata

    return normalized


def _forward_response_passthrough(upstream: httpx.Response) -> Response:
    content_type = upstream.headers.get("content-type", "application/json")
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=content_type,
    )


async def _stream_upstream(
    upstream: httpx.Response,
    stream_context: Any,
    client: httpx.AsyncClient,
) -> AsyncIterator[bytes]:
    try:
        async for chunk in upstream.aiter_raw():
            if chunk:
                yield chunk
    finally:
        await stream_context.__aexit__(None, None, None)
        await client.aclose()


def create_openclaw_proxy_router(config: OpenClawProxyConfig) -> APIRouter:
    """Create a router that proxies OpenResponses requests to OpenClaw."""
    router = APIRouter()

    upstream_url = f"{config.upstream_base_url.rstrip('/')}/v1/responses"

    @router.post("/v1/responses")
    async def proxy_responses(request: Request) -> Response:
        try:
            payload = await request.json()
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid JSON body: {exc}") from exc

        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="Request body must be a JSON object")

        try:
            normalized_payload = normalize_openresponses_payload(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        headers = {
            "Authorization": f"Bearer {config.upstream_token}",
            "Content-Type": "application/json",
        }

        stream = bool(normalized_payload.get("stream"))
        if not stream:
            async with httpx.AsyncClient(timeout=config.timeout_seconds) as client:
                upstream = await client.post(upstream_url, headers=headers, json=normalized_payload)
            return _forward_response_passthrough(upstream)

        client = httpx.AsyncClient(timeout=None)
        stream_context = client.stream("POST", upstream_url, headers=headers, json=normalized_payload)
        upstream = await stream_context.__aenter__()

        if upstream.status_code >= 400:
            try:
                body = await upstream.aread()
            finally:
                await stream_context.__aexit__(None, None, None)
                await client.aclose()

            return Response(
                content=body,
                status_code=upstream.status_code,
                media_type=upstream.headers.get("content-type", "application/json"),
            )

        return StreamingResponse(
            _stream_upstream(upstream, stream_context, client),
            status_code=upstream.status_code,
            media_type=upstream.headers.get("content-type", "text/event-stream"),
        )

    @router.get("/health")
    async def openclaw_proxy_health() -> JSONResponse:
        return JSONResponse({"ok": True, "upstream": upstream_url})

    return router
