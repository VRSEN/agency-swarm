"""
Tools for SharePoint Metadata Agent.
"""

import json
from typing import Any

import requests
from agency_swarm import function_tool
from msal import ConfidentialClientApplication

from ...config import Config
from ...utils import SharePointError, get_logger, retry

logger = get_logger(__name__)


class SharePointGraphClient:
    """Microsoft Graph API client for SharePoint operations."""

    def __init__(self, config: Config):
        self.config = config
        self.access_token: str | None = None
        self.app = ConfidentialClientApplication(
            client_id=config.azure.client_id,
            client_credential=config.azure.client_secret,
            authority=f"https://login.microsoftonline.com/{config.azure.tenant_id}",
        )

    @retry(max_attempts=3, delay=2.0)
    def _get_access_token(self) -> str:
        """Get access token for Microsoft Graph API."""
        if self.access_token:
            return self.access_token

        result = self.app.acquire_token_for_client(scopes=self.config.azure.scopes)

        if "access_token" in result:
            self.access_token = result["access_token"]
            logger.info("Successfully acquired access token for Microsoft Graph API")
            return self.access_token
        else:
            error_msg = result.get("error_description", "Unknown error acquiring token")
            raise SharePointError(f"Failed to acquire access token: {error_msg}")

    @retry(max_attempts=3, delay=2.0)
    def make_request(self, method: str, endpoint: str, **kwargs) -> dict[str, Any]:
        """Make authenticated request to Microsoft Graph API."""
        token = self._get_access_token()

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", **kwargs.pop("headers", {})}

        url = f"https://graph.microsoft.com/{self.config.azure.api_version}/{endpoint}"

        response = requests.request(
            method=method, url=url, headers=headers, timeout=self.config.azure.timeout, **kwargs
        )

        if response.status_code == 401:
            # Token might be expired, clear it and retry once
            self.access_token = None
            token = self._get_access_token()
            headers["Authorization"] = f"Bearer {token}"

            response = requests.request(
                method=method, url=url, headers=headers, timeout=self.config.azure.timeout, **kwargs
            )

        if not response.ok:
            raise SharePointError(
                f"Graph API request failed: {response.status_code} {response.reason}",
                status_code=response.status_code,
                details={"url": url, "response": response.text},
            )

        return response.json()


@function_tool
def sharepoint_connector(site_url: str, library_name: str, config_json: str = "{}") -> str:
    """
    Connect to SharePoint and validate access to the specified library.

    Args:
        site_url: SharePoint site URL
        library_name: Name of the document library

    Returns:
        Connection status and library information
    """
    try:
        # This would be injected by the agent
        config = Config.from_env()  # In real implementation, this would come from agent context
        client = SharePointGraphClient(config)

        # Extract site path from URL
        site_path = site_url.replace("https://", "").split("/", 1)[1] if "/" in site_url else ""

        # Get site information
        site_endpoint = f"sites/{config.sharepoint.site_url.replace('https://', '').replace('/', ':')}:/{site_path}"
        site_info = client.make_request("GET", site_endpoint)

        # Get library information
        library_endpoint = f"sites/{site_info['id']}/lists"
        libraries = client.make_request("GET", library_endpoint)

        target_library = None
        for library in libraries.get("value", []):
            if library.get("displayName") == library_name:
                target_library = library
                break

        if not target_library:
            raise SharePointError(f"Library '{library_name}' not found in site")

        result = {
            "status": "connected",
            "site_id": site_info["id"],
            "site_name": site_info["displayName"],
            "library_id": target_library["id"],
            "library_name": target_library["displayName"],
            "library_type": target_library.get("list", {}).get("template", "Unknown"),
        }

        logger.info(f"Successfully connected to SharePoint library: {library_name}")
        return json.dumps(result, indent=2)

    except Exception as e:
        logger.error(f"Failed to connect to SharePoint: {e}")
        raise SharePointError(f"SharePoint connection failed: {str(e)}") from e


@function_tool
def metadata_schema_loader(library_id: str, cache_duration_hours: int = 24) -> str:
    """
    Load metadata schema from SharePoint document library.

    Args:
        library_id: SharePoint library ID
        cache_duration_hours: How long to cache the schema (default: 24 hours)

    Returns:
        JSON string containing the library's metadata schema
    """
    try:
        config = Config.from_env()
        client = SharePointGraphClient(config)

        # Get library columns/fields
        columns_endpoint = f"sites/{config.sharepoint.site_id or 'root'}/lists/{library_id}/columns"
        columns_response = client.make_request("GET", columns_endpoint)

        # Get content types
        content_types_endpoint = f"sites/{config.sharepoint.site_id or 'root'}/lists/{library_id}/contentTypes"
        content_types_response = client.make_request("GET", content_types_endpoint)

        # Process columns into schema format
        schema = {
            "library_id": library_id,
            "fields": [],
            "content_types": [],
            "loaded_at": "2024-01-01T00:00:00Z",  # Would use actual timestamp
        }

        for column in columns_response.get("value", []):
            field_info = {
                "name": column.get("name"),
                "display_name": column.get("displayName"),
                "type": column.get("columnGroup"),
                "required": column.get("required", False),
                "hidden": column.get("hidden", False),
                "read_only": column.get("readOnly", False),
                "description": column.get("description", ""),
                "default_value": column.get("defaultValue"),
            }

            # Add type-specific properties
            if "text" in column:
                field_info["max_length"] = column["text"].get("maxLength")
            elif "choice" in column:
                field_info["choices"] = column["choice"].get("choices", [])
                field_info["allow_fill_in"] = column["choice"].get("allowFillInChoice", False)
            elif "dateTime" in column:
                field_info["format"] = column["dateTime"].get("format")
            elif "number" in column:
                field_info["min_value"] = column["number"].get("minimum")
                field_info["max_value"] = column["number"].get("maximum")
                field_info["decimal_places"] = column["number"].get("decimalPlaces")

            schema["fields"].append(field_info)

        # Process content types
        for content_type in content_types_response.get("value", []):
            ct_info = {
                "id": content_type.get("id"),
                "name": content_type.get("name"),
                "description": content_type.get("description", ""),
                "hidden": content_type.get("hidden", False),
                "read_only": content_type.get("readOnly", False),
                "parent_id": content_type.get("parentId"),
            }
            schema["content_types"].append(ct_info)

        logger.info(f"Successfully loaded schema for library {library_id} with {len(schema['fields'])} fields")
        return json.dumps(schema, indent=2)

    except Exception as e:
        logger.error(f"Failed to load metadata schema: {e}")
        raise SharePointError(f"Schema loading failed: {str(e)}") from e


@function_tool
def schema_validator(schema_json: str, metadata_dict: str) -> str:
    """
    Validate metadata against SharePoint schema.

    Args:
        schema_json: JSON string containing the SharePoint schema
        metadata_dict: JSON string containing metadata to validate

    Returns:
        Validation result with any errors or warnings
    """
    try:
        schema = json.loads(schema_json)
        metadata = json.loads(metadata_dict)

        validation_result = {"valid": True, "errors": [], "warnings": [], "field_validations": {}}

        # Create field lookup
        fields_by_name = {field["name"]: field for field in schema.get("fields", [])}

        # Validate each metadata field
        for field_name, field_value in metadata.items():
            field_validation = {"valid": True, "errors": [], "warnings": []}

            if field_name not in fields_by_name:
                field_validation["warnings"].append(f"Field '{field_name}' not found in schema")
                validation_result["warnings"].append(f"Unknown field: {field_name}")
            else:
                field_schema = fields_by_name[field_name]

                # Check required fields
                if field_schema.get("required", False) and not field_value:
                    field_validation["errors"].append("Required field is empty")
                    field_validation["valid"] = False

                # Check read-only fields
                if field_schema.get("read_only", False):
                    field_validation["warnings"].append("Field is read-only")

                # Type-specific validation
                field_type = field_schema.get("type", "").lower()

                if "text" in field_type and isinstance(field_value, str):
                    max_length = field_schema.get("max_length")
                    if max_length and len(field_value) > max_length:
                        field_validation["errors"].append(f"Text exceeds maximum length of {max_length}")
                        field_validation["valid"] = False

                elif "choice" in field_type:
                    choices = field_schema.get("choices", [])
                    if choices and field_value not in choices:
                        allow_fill_in = field_schema.get("allow_fill_in", False)
                        if not allow_fill_in:
                            field_validation["errors"].append(f"Value must be one of: {', '.join(choices)}")
                            field_validation["valid"] = False
                        else:
                            field_validation["warnings"].append("Using custom value for choice field")

                elif "number" in field_type and isinstance(field_value, (int, float)):
                    min_val = field_schema.get("min_value")
                    max_val = field_schema.get("max_value")

                    if min_val is not None and field_value < min_val:
                        field_validation["errors"].append(f"Value below minimum of {min_val}")
                        field_validation["valid"] = False

                    if max_val is not None and field_value > max_val:
                        field_validation["errors"].append(f"Value above maximum of {max_val}")
                        field_validation["valid"] = False

            validation_result["field_validations"][field_name] = field_validation

            if not field_validation["valid"]:
                validation_result["valid"] = False
                validation_result["errors"].extend(field_validation["errors"])

        # Check for missing required fields
        for field in schema.get("fields", []):
            if field.get("required", False) and field["name"] not in metadata:
                validation_result["valid"] = False
                validation_result["errors"].append(f"Required field missing: {field['name']}")

        logger.info(f"Schema validation completed. Valid: {validation_result['valid']}")
        return json.dumps(validation_result, indent=2)

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in schema validation: {e}")
        return json.dumps(
            {"valid": False, "errors": [f"Invalid JSON format: {str(e)}"], "warnings": [], "field_validations": {}}
        )
    except Exception as e:
        logger.error(f"Schema validation failed: {e}")
        raise SharePointError(f"Schema validation failed: {str(e)}") from e
