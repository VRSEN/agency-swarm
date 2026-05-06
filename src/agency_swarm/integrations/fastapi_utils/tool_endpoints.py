import asyncio
import json
from typing import Any, cast

from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from agency_swarm.tools import BaseTool

from .tool_request_models import build_request_model


def make_tool_endpoint(tool, verify_token, context=None):
    async def generic_handler(request: Request, token: str = Depends(verify_token)):
        try:
            data = await request.json()
            if hasattr(tool, "on_invoke_tool"):
                input_json = json.dumps(data)
                result = await tool.on_invoke_tool(context, input_json)
            elif isinstance(tool, type):
                tool_instance = tool(**data)
                result = tool_instance.run()
                if asyncio.iscoroutine(result):
                    result = await result
            else:
                result = tool(**data)
                if asyncio.iscoroutine(result):
                    result = await result
            return {"response": result}
        except Exception as e:
            return JSONResponse(status_code=500, content={"Error": str(e)})

    if isinstance(tool, type) and issubclass(tool, BaseTool):
        RequestModel: type[BaseModel] = tool

        async def handler(request_data: Any, token: str = Depends(verify_token)):
            try:
                data = cast(BaseModel, request_data).model_dump(mode="python", exclude_unset=True)
                tool_instance = tool(**data)
                result = tool_instance.run()
                if asyncio.iscoroutine(result):
                    result = await result
                return {"response": result}
            except Exception as e:
                return JSONResponse(status_code=500, content={"Error": str(e)})

        handler.__annotations__["request_data"] = RequestModel
        return handler

    tool_name = _tool_name(tool)
    parameters: dict[str, Any] | None = None
    strict_schema = False
    if hasattr(tool, "openai_schema"):
        schema = tool.openai_schema
        parameters = schema.get("parameters", {})
        strict_schema = bool(schema.get("strict"))
    elif hasattr(tool, "params_json_schema"):
        parameters = tool.params_json_schema
        strict_schema = bool(getattr(tool, "strict_json_schema", False))
    else:  # pragma: no cover - defensive airflow
        return generic_handler

    RequestModel = build_request_model(parameters or {}, tool_name, strict=strict_schema)
    if RequestModel is None:
        return generic_handler

    async def handler(request_data: Any, token: str = Depends(verify_token)):
        try:
            request_model = cast(BaseModel, request_data)
            data = request_model.model_dump(mode="python", exclude_unset=True)
            if hasattr(tool, "on_invoke_tool"):
                input_json = request_model.model_dump_json(exclude_unset=True)
                result = await tool.on_invoke_tool(context, input_json)
            else:
                result = tool(**data)
                if asyncio.iscoroutine(result):
                    result = await result
            return {"response": result}
        except Exception as e:
            return JSONResponse(status_code=500, content={"Error": str(e)})

    handler.__annotations__["request_data"] = RequestModel
    return handler


def _tool_name(tool: Any) -> str:
    name = getattr(tool, "name", None)
    if isinstance(name, str):
        return name
    function_name = getattr(tool, "__name__", None)
    if isinstance(function_name, str):
        return function_name
    return tool.__class__.__name__
