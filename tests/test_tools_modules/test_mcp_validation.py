"""Test that demonstrates validation metadata loss when converting MCP tools to BaseTools."""

from unittest.mock import AsyncMock, patch

import pytest
from agents import FunctionTool

from agency_swarm.tools.tool_factory import ToolFactory


class _DummyServer:
    def __init__(self, name: str = "validation_test_server") -> None:
        self.name = name
        self.session = None

    async def connect(self) -> None:
        self.session = object()

    async def cleanup(self) -> None:
        self.session = None


@pytest.mark.asyncio
@patch("agents.mcp.util.MCPUtil.get_function_tools", new_callable=AsyncMock)
@patch("agency_swarm.tools.mcp_manager.default_mcp_manager")
async def test_mcp_validation_metadata_loss(mock_manager, mock_get_function_tools: AsyncMock) -> None:
    """
    Test that demonstrates how JSON schema validation constraints are lost during MCP conversion.

    The original MCP tool has rich validation:
    - enum: status must be one of ["active", "inactive", "pending"]
    - pattern: email must match a regex
    - minLength/maxLength: username length constraints
    - minimum/maximum: age must be between 18 and 100
    - minItems/maxItems: tags array length constraints

    After conversion to BaseTool, these constraints are dropped, and the resulting
    Pydantic model only preserves basic types and descriptions.
    """

    # Create a FunctionTool with rich validation metadata
    rich_schema = {
        "type": "object",
        "properties": {
            "username": {
                "type": "string",
                "description": "User's username",
                "minLength": 3,
                "maxLength": 20,
                "pattern": "^[a-zA-Z0-9_]+$",
            },
            "email": {
                "type": "string",
                "description": "User's email address",
                "format": "email",
                "pattern": r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
            },
            "age": {
                "type": "integer",
                "description": "User's age",
                "minimum": 18,
                "maximum": 100,
            },
            "status": {
                "type": "string",
                "description": "Account status",
                "enum": ["active", "inactive", "pending"],
            },
            "tags": {
                "type": "array",
                "description": "User tags",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 5,
            },
            "score": {
                "type": "number",
                "description": "User score",
                "minimum": 0.0,
                "maximum": 100.0,
            },
        },
        "required": ["username", "email", "status"],
    }

    async def mock_invoke(ctx, input_json: str):
        return f"Processed: {input_json}"

    function_tool = FunctionTool(
        name="create_user_profile",
        description="Creates a user profile with validation",
        params_json_schema=rich_schema,
        on_invoke_tool=mock_invoke,
        strict_json_schema=False,
    )
    mock_get_function_tools.return_value = [function_tool]

    server = _DummyServer()
    mock_manager.register.return_value = server
    mock_manager.ensure_connected = AsyncMock()
    mock_manager.get.return_value = server

    # Convert to BaseTool
    tools = ToolFactory.from_mcp([server], as_base_tool=True)
    assert len(tools) == 1
    tool_class = tools[0]

    # Get the JSON schema from the converted BaseTool
    converted_schema = tool_class.model_json_schema()

    # Verify that validation metadata is preserved
    username_prop = converted_schema["properties"]["username"]
    assert "minLength" in username_prop, "minLength constraint must be preserved"
    assert username_prop["minLength"] == 3
    assert "maxLength" in username_prop, "maxLength constraint must be preserved"
    assert username_prop["maxLength"] == 20
    assert "pattern" in username_prop, "pattern constraint must be preserved"

    email_prop = converted_schema["properties"]["email"]
    assert "format" in email_prop or "pattern" in email_prop, "email validation must be preserved"

    age_prop = converted_schema["properties"]["age"]
    assert "minimum" in age_prop, "minimum constraint must be preserved"
    assert age_prop["minimum"] == 18
    assert "maximum" in age_prop, "maximum constraint must be preserved"
    assert age_prop["maximum"] == 100

    status_prop = converted_schema["properties"]["status"]
    assert "enum" in status_prop, "enum constraint must be preserved"
    assert set(status_prop["enum"]) == {"active", "inactive", "pending"}

    tags_prop = converted_schema["properties"]["tags"]
    assert "minItems" in tags_prop, "minItems constraint must be preserved"
    assert tags_prop["minItems"] == 1
    assert "maxItems" in tags_prop, "maxItems constraint must be preserved"
    assert tags_prop["maxItems"] == 5

    score_prop = converted_schema["properties"]["score"]
    assert "minimum" in score_prop, "minimum constraint must be preserved"
    assert score_prop["minimum"] == 0.0
    assert "maximum" in score_prop, "maximum constraint must be preserved"
    assert score_prop["maximum"] == 100.0

    # Now verify that invalid data is actually rejected by Pydantic validation
    from pydantic import ValidationError

    # Invalid username: too short (< 3 chars)
    with pytest.raises(ValidationError, match="minLength|min_length|at least 3"):
        tool_class(
            username="ab",  # Should fail minLength=3
            email="user@example.com",
            status="active",
        )

    # Invalid status: not in enum
    with pytest.raises(ValidationError, match="enum|invalid_status"):
        tool_class(
            username="valid_user",
            email="user@example.com",
            status="invalid_status",  # Should fail enum constraint
        )

    # Invalid age: below minimum
    with pytest.raises(ValidationError, match="minimum|greater than or equal"):
        tool_class(
            username="valid_user",
            email="user@example.com",
            status="active",
            age=10,  # Should fail minimum=18
        )

    # Invalid score: above maximum
    with pytest.raises(ValidationError, match="maximum|less than or equal"):
        tool_class(
            username="valid_user",
            email="user@example.com",
            status="active",
            score=150.0,  # Should fail maximum=100.0
        )


@pytest.mark.asyncio
@patch("agents.mcp.util.MCPUtil.get_function_tools", new_callable=AsyncMock)
@patch("agency_swarm.tools.mcp_manager.default_mcp_manager")
async def test_mcp_nested_object_validation_loss(mock_manager, mock_get_function_tools: AsyncMock) -> None:
    """Test that validation constraints are also lost in nested objects and $defs."""

    schema_with_defs = {
        "type": "object",
        "properties": {
            "user": {
                "$ref": "#/$defs/UserInfo",
            },
        },
        "required": ["user"],
        "$defs": {
            "UserInfo": {
                "type": "object",
                "properties": {
                    "role": {
                        "type": "string",
                        "description": "User role",
                        "enum": ["admin", "user", "guest"],
                    },
                    "permissions": {
                        "type": "array",
                        "description": "User permissions",
                        "items": {"type": "string"},
                        "minItems": 1,
                        "maxItems": 10,
                    },
                },
                "required": ["role"],
            },
        },
    }

    async def mock_invoke(ctx, input_json: str):
        return f"Processed: {input_json}"

    function_tool = FunctionTool(
        name="configure_user",
        description="Configure user with nested validation",
        params_json_schema=schema_with_defs,
        on_invoke_tool=mock_invoke,
        strict_json_schema=False,
    )
    mock_get_function_tools.return_value = [function_tool]

    server = _DummyServer()
    mock_manager.register.return_value = server
    mock_manager.ensure_connected = AsyncMock()
    mock_manager.get.return_value = server

    # Convert to BaseTool
    tools = ToolFactory.from_mcp([server], as_base_tool=True)
    assert len(tools) == 1
    tool_class = tools[0]

    # Get the JSON schema from the converted BaseTool
    converted_schema = tool_class.model_json_schema()

    # Check that nested validation is preserved
    assert "$defs" in converted_schema, "Nested object definitions must be preserved"
    user_info_def = converted_schema["$defs"].get("ConfigureUser_user") or converted_schema["$defs"].get("UserInfo")
    assert user_info_def is not None, "UserInfo definition must exist"
    assert "properties" in user_info_def

    role_prop = user_info_def["properties"]["role"]
    assert "enum" in role_prop, "enum in nested object must be preserved"
    assert set(role_prop["enum"]) == {"admin", "user", "guest"}

    permissions_prop = user_info_def["properties"]["permissions"]
    assert "minItems" in permissions_prop, "minItems in nested array must be preserved"
    assert permissions_prop["minItems"] == 1
    assert "maxItems" in permissions_prop, "maxItems in nested array must be preserved"
    assert permissions_prop["maxItems"] == 10

    # Verify that invalid nested data is rejected
    from pydantic import ValidationError

    # Invalid role: not in enum
    with pytest.raises(ValidationError, match="role|enum|superadmin"):
        tool_class(
            user={
                "role": "superadmin",  # Should fail enum constraint
            }
        )

    # Invalid permissions: empty array fails minItems
    with pytest.raises(ValidationError, match="permissions|minItems|at least 1"):
        tool_class(
            user={
                "role": "admin",
                "permissions": [],  # Should fail minItems=1
            }
        )


@pytest.mark.asyncio
@patch("agents.mcp.util.MCPUtil.get_function_tools", new_callable=AsyncMock)
@patch("agency_swarm.tools.mcp_manager.default_mcp_manager")
async def test_mcp_const_and_additional_properties_loss(mock_manager, mock_get_function_tools: AsyncMock) -> None:
    """Test that const and additionalProperties constraints are lost."""

    schema_with_const = {
        "type": "object",
        "properties": {
            "api_version": {
                "type": "string",
                "description": "API version",
                "const": "v1",
            },
            "metadata": {
                "type": "object",
                "description": "Additional metadata",
                "properties": {
                    "source": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        "required": ["api_version"],
    }

    async def mock_invoke(ctx, input_json: str):
        return f"Processed: {input_json}"

    function_tool = FunctionTool(
        name="api_request",
        description="Make API request with const and additionalProperties validation",
        params_json_schema=schema_with_const,
        on_invoke_tool=mock_invoke,
        strict_json_schema=False,
    )
    mock_get_function_tools.return_value = [function_tool]

    server = _DummyServer()
    mock_manager.register.return_value = server
    mock_manager.ensure_connected = AsyncMock()
    mock_manager.get.return_value = server

    # Convert to BaseTool
    tools = ToolFactory.from_mcp([server], as_base_tool=True)
    assert len(tools) == 1
    tool_class = tools[0]

    # Get the JSON schema from the converted BaseTool
    converted_schema = tool_class.model_json_schema()

    # Verify const is preserved
    api_version_prop = converted_schema["properties"]["api_version"]
    assert "const" in api_version_prop, "const constraint must be preserved"
    assert api_version_prop["const"] == "v1"

    # Verify additionalProperties constraint is preserved
    # Check in either the main properties or in $defs
    if "$ref" in converted_schema["properties"]["metadata"]:
        # Nested model case
        ref_name = converted_schema["properties"]["metadata"]["$ref"].split("/")[-1]
        metadata_def = converted_schema["$defs"][ref_name]
        assert "additionalProperties" in metadata_def, "additionalProperties must be preserved in nested model"
        assert metadata_def["additionalProperties"] is False
    else:
        metadata_prop = converted_schema["properties"]["metadata"]
        assert "additionalProperties" in metadata_prop, "additionalProperties must be preserved"
        assert metadata_prop["additionalProperties"] is False

    # Verify that invalid data is rejected
    from pydantic import ValidationError

    # Invalid api_version: must be exactly "v1"
    with pytest.raises(ValidationError, match="const|v2|must be 'v1'"):
        tool_class(
            api_version="v2",  # Should fail const="v1"
        )

    # Invalid metadata: extra fields should be rejected
    with pytest.raises(ValidationError, match="extra|additional|unexpected"):
        tool_class(
            api_version="v1",
            metadata={"source": "test", "unexpected_field": "should_be_rejected"},
        )
