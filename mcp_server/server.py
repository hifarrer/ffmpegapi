import json
import logging
import os
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import Any, Callable

import httpx
from mcp.server import Server
from mcp.server.fastmcp.server import StreamableHTTPASGIApp
from mcp.server.lowlevel.server import ReadResourceContents
from mcp.server.streamable_http import TransportSecuritySettings
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import Resource, TextContent, Tool
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from ai_discovery import (
    generate_docs_markdown,
    generate_examples_markdown,
    generate_llms_full_txt,
    generate_openapi_spec,
)
from mcp_server.catalog import input_schema_for_endpoint, path_parameters, tool_catalog


logger = logging.getLogger(__name__)

DEFAULT_API_BASE_URL = "https://ffmpegapi.net"
DEFAULT_TIMEOUT_SECONDS = 1800.0
DEFAULT_ALLOWED_ORIGINS = [
    "https://ffmpegapi.net",
    "https://www.ffmpegapi.net",
    "http://localhost:*",
    "http://127.0.0.1:*",
]
DEFAULT_ALLOWED_HOSTS = [
    "ffmpegapi.net",
    "www.ffmpegapi.net",
    "localhost:*",
    "127.0.0.1:*",
    "testserver",
]

api_key_context: ContextVar[str | None] = ContextVar("ffmpeg_api_key", default=None)

EndpointCatalog = dict[str, dict[str, Any]]
ClientFactory = Callable[[float], httpx.AsyncClient]


def _split_env_list(name: str, default: list[str]) -> list[str]:
    raw = os.environ.get(name)
    if not raw:
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


def _timeout_seconds() -> float:
    raw = os.environ.get("MCP_REQUEST_TIMEOUT_SECONDS")
    if not raw:
        return DEFAULT_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError:
        logger.warning("Invalid MCP_REQUEST_TIMEOUT_SECONDS value; using default")
        return DEFAULT_TIMEOUT_SECONDS
    return value if value > 0 else DEFAULT_TIMEOUT_SECONDS


def _api_base_url() -> str:
    return os.environ.get("FFMPEG_API_BASE_URL", DEFAULT_API_BASE_URL).rstrip("/")


def _redact_api_key(api_key: str | None) -> str:
    if not api_key:
        return "<missing>"
    if len(api_key) <= 8:
        return "[REDACTED]"
    return f"{api_key[:4]}...[REDACTED]...{api_key[-4:]}"


def _default_client_factory(timeout: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout)


def mcp_tool_definitions(catalog: EndpointCatalog | None = None) -> list[Tool]:
    endpoints = catalog or tool_catalog()
    return [
        Tool(
            name=tool_name,
            title=endpoint["name"],
            description=endpoint["description"],
            inputSchema=input_schema_for_endpoint(endpoint),
            outputSchema={
                "type": "object",
                "properties": {
                    "ok": {"type": "boolean"},
                    "status_code": {"type": "integer"},
                    "endpoint": {"type": "string"},
                    "operation_id": {"type": "string"},
                    "response": {"type": "object"},
                },
                "required": ["ok", "status_code", "endpoint", "operation_id", "response"],
                "additionalProperties": True,
            },
        )
        for tool_name, endpoint in endpoints.items()
    ]


def mcp_resources() -> list[Resource]:
    return [
        Resource(
            uri="ffmpegapi://openapi.json",
            name="OpenAPI specification",
            title="OpenAPI specification",
            description="OpenAPI JSON for public FFMPEG API endpoints.",
            mimeType="application/json",
        ),
        Resource(
            uri="ffmpegapi://docs.md",
            name="API documentation",
            title="API documentation",
            description="Markdown API documentation for public FFMPEG API endpoints.",
            mimeType="text/markdown",
        ),
        Resource(
            uri="ffmpegapi://examples.md",
            name="API examples",
            title="API examples",
            description="Markdown request examples for FFMPEG API endpoints.",
            mimeType="text/markdown",
        ),
        Resource(
            uri="ffmpegapi://llms-full.txt",
            name="Full LLM context",
            title="Full LLM context",
            description="Combined API documentation, examples, and LLM-facing context.",
            mimeType="text/plain",
        ),
    ]


def resource_content(uri: str) -> tuple[str, str]:
    if uri == "ffmpegapi://openapi.json":
        return json.dumps(generate_openapi_spec(), indent=2), "application/json"
    if uri == "ffmpegapi://docs.md":
        return generate_docs_markdown(full=True), "text/markdown"
    if uri == "ffmpegapi://examples.md":
        return generate_examples_markdown(), "text/markdown"
    if uri == "ffmpegapi://llms-full.txt":
        return generate_llms_full_txt(), "text/plain"
    raise ValueError(f"Unknown resource URI: {uri}")


def _build_endpoint_url(endpoint: dict[str, Any], arguments: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    path = endpoint["path"]
    remaining = dict(arguments)
    for param_name in path_parameters(path):
        value = remaining.pop(param_name, None)
        if value is None:
            raise ValueError(f"Missing required path parameter: {param_name}")
        path = path.replace("{" + param_name + "}", str(value))
    return f"{_api_base_url()}{path}", remaining


def _summarize_response(tool_name: str, structured: dict[str, Any]) -> str:
    response = structured.get("response")
    if isinstance(response, dict):
        if response.get("success") is False and response.get("error"):
            return f"{tool_name} failed: {response['error']}"
        if response.get("status"):
            return f"{tool_name} returned status {response['status']}"
        if response.get("download_url"):
            return f"{tool_name} completed: {response['download_url']}"
        if response.get("message"):
            return f"{tool_name}: {response['message']}"
    return f"{tool_name} returned HTTP {structured['status_code']}"


async def dispatch_tool(
    tool_name: str,
    arguments: dict[str, Any],
    api_key: str,
    *,
    catalog: EndpointCatalog | None = None,
    client_factory: ClientFactory = _default_client_factory,
) -> tuple[list[TextContent], dict[str, Any]]:
    endpoints = catalog or tool_catalog()
    endpoint = endpoints.get(tool_name)
    if endpoint is None:
        raise ValueError(f"Unknown tool: {tool_name}")
    if not api_key:
        raise PermissionError("X-API-Key is required")

    url, forwarded_arguments = _build_endpoint_url(endpoint, arguments)
    headers = {
        "X-API-Key": api_key,
        "Accept": "application/json",
        "User-Agent": "ffmpegapi-mcp/1.0",
    }

    logger.info(
        "Forwarding MCP tool %s to %s with API key %s",
        tool_name,
        endpoint["path"],
        _redact_api_key(api_key),
    )

    async with client_factory(_timeout_seconds()) as client:
        if endpoint["method"] == "GET":
            response = await client.get(url, params=forwarded_arguments, headers=headers)
        else:
            response = await client.request(endpoint["method"], url, json=forwarded_arguments, headers=headers)

    try:
        response_payload: Any = response.json()
    except ValueError:
        response_payload = {"text": response.text}

    structured = {
        "ok": 200 <= response.status_code < 300,
        "status_code": response.status_code,
        "endpoint": endpoint["path"],
        "operation_id": endpoint["operation_id"],
        "response": response_payload if isinstance(response_payload, dict) else {"value": response_payload},
    }
    content = [TextContent(type="text", text=_summarize_response(tool_name, structured))]
    return content, structured


def create_mcp_server(catalog: EndpointCatalog | None = None) -> Server:
    endpoints = catalog or tool_catalog()
    server = Server("ffmpegapi-mcp")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return mcp_tool_definitions(endpoints)

    @server.call_tool(validate_input=True)
    async def call_tool(tool_name: str, arguments: dict[str, Any]) -> tuple[list[TextContent], dict[str, Any]]:
        api_key = api_key_context.get()
        if not api_key:
            raise PermissionError("X-API-Key is required")
        return await dispatch_tool(tool_name, arguments, api_key, catalog=endpoints)

    @server.list_resources()
    async def list_resources() -> list[Resource]:
        return mcp_resources()

    @server.read_resource()
    async def read_resource(uri: Any) -> list[ReadResourceContents]:
        content, mime_type = resource_content(str(uri))
        return [ReadResourceContents(content=content, mime_type=mime_type)]

    return server


class ApiKeyRequiredASGIApp:
    def __init__(self, inner: Any):
        self.inner = inner

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.inner(scope, receive, send)
            return

        request = Request(scope, receive)
        api_key = request.headers.get("x-api-key")
        if not api_key:
            response = JSONResponse(
                {"success": False, "error": "X-API-Key header is required for MCP requests."},
                status_code=401,
            )
            await response(scope, receive, send)
            return

        token = api_key_context.set(api_key)
        try:
            await self.inner(scope, receive, send)
        finally:
            api_key_context.reset(token)


def create_app(catalog: EndpointCatalog | None = None) -> Starlette:
    server = create_mcp_server(catalog)
    security_settings = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=_split_env_list("MCP_ALLOWED_HOSTS", DEFAULT_ALLOWED_HOSTS),
        allowed_origins=_split_env_list("MCP_ALLOWED_ORIGINS", DEFAULT_ALLOWED_ORIGINS),
    )
    session_manager = StreamableHTTPSessionManager(
        app=server,
        json_response=False,
        stateless=True,
        security_settings=security_settings,
    )
    mcp_app = ApiKeyRequiredASGIApp(StreamableHTTPASGIApp(session_manager))

    @asynccontextmanager
    async def lifespan(_: Starlette):
        async with session_manager.run():
            yield

    return Starlette(
        debug=os.environ.get("MCP_DEBUG", "").lower() in {"1", "true", "yes"},
        routes=[Route("/mcp", endpoint=mcp_app)],
        lifespan=lifespan,
    )


app = create_app()

