import re
from copy import deepcopy
from typing import Any

from ai_discovery import ENDPOINTS


PATH_PARAMETER_RE = re.compile(r"{([^}]+)}")


def operation_id_to_tool_name(operation_id: str) -> str:
    """Convert lowerCamelCase OpenAPI operation IDs to MCP-safe snake_case."""
    name = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", operation_id)
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    return name.lower()


def schema_for_param(param: dict[str, Any]) -> dict[str, Any]:
    param_type = param["type"]
    if param_type == "array[string]":
        schema: dict[str, Any] = {"type": "array", "items": {"type": "string", "format": "uri"}}
    elif param_type == "integer":
        schema = {"type": "integer"}
    elif param_type == "number":
        schema = {"type": "number"}
    elif param_type == "boolean":
        schema = {"type": "boolean"}
    else:
        schema = {"type": "string"}

    if "description" in param:
        schema["description"] = param["description"]
    if "default" in param:
        schema["default"] = param["default"]
    return schema


def input_schema_for_endpoint(endpoint: dict[str, Any]) -> dict[str, Any]:
    if endpoint.get("request_schema") and endpoint["method"] != "GET":
        return deepcopy(endpoint["request_schema"])

    required = [p["name"] for p in endpoint["parameters"] if p.get("required")]
    properties = {p["name"]: schema_for_param(p) for p in endpoint["parameters"]}
    return {
        "type": "object",
        "required": required,
        "properties": properties,
        "additionalProperties": False,
    }


def tool_catalog() -> dict[str, dict[str, Any]]:
    catalog = {}
    for endpoint in ENDPOINTS:
        tool_name = operation_id_to_tool_name(endpoint["operation_id"])
        catalog[tool_name] = endpoint
    return catalog


def path_parameters(path: str) -> list[str]:
    return PATH_PARAMETER_RE.findall(path)

