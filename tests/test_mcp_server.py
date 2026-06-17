import json
import unittest

import httpx
from starlette.testclient import TestClient

from mcp_server.catalog import input_schema_for_endpoint, tool_catalog
from mcp_server.server import create_app, dispatch_tool, mcp_tool_definitions


class McpCatalogTests(unittest.TestCase):
    def test_tool_catalog_contains_all_public_media_tools(self):
        tools = mcp_tool_definitions()
        names = {tool.name for tool in tools}

        self.assertEqual(len(tools), 25)
        self.assertIn("compress_video", names)
        self.assertIn("endless_loop", names)
        self.assertIn("neonvideo_merge_videos", names)
        self.assertIn("get_job_status", names)
        self.assertNotIn("cleanup_old_videos", names)
        self.assertNotIn("serve_from_storage", names)

    def test_tool_schemas_do_not_expose_api_key(self):
        for tool in mcp_tool_definitions():
            schema_json = json.dumps(tool.inputSchema).lower()
            self.assertNotIn("api_key", schema_json)
            self.assertNotIn("x-api-key", schema_json)

    def test_tool_output_schemas_are_endpoint_specific(self):
        output_schemas = {tool.name: tool.outputSchema for tool in mcp_tool_definitions()}

        self.assertIn("audio_parts", json.dumps(output_schemas["split_audio"]))
        self.assertIn("image_url", json.dumps(output_schemas["get_first_frame_image"]))
        self.assertIn("captions_json_url", json.dumps(output_schemas["add_tiktok_captions"]))
        self.assertIn("compression_ratio", json.dumps(output_schemas["compress_video"]))
        self.assertIn("loops_required", json.dumps(output_schemas["endless_loop"]))
        self.assertNotEqual(output_schemas["merge_videos"]["properties"]["response"], {"type": "object"})

    def test_neonvideo_schema_matches_endpoint_metadata(self):
        endpoint = tool_catalog()["neonvideo_merge_videos"]
        schema = input_schema_for_endpoint(endpoint)

        self.assertEqual(schema["required"], ["video_urls"])
        self.assertIn("outro_url", schema["properties"])
        self.assertEqual(schema["properties"]["async"]["type"], "boolean")


class McpForwardingTests(unittest.IsolatedAsyncioTestCase):
    async def test_post_tool_forwards_json_and_api_key(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["method"] = request.method
            captured["url"] = str(request.url)
            captured["api_key"] = request.headers.get("x-api-key")
            captured["body"] = json.loads(request.content.decode())
            return httpx.Response(200, json={"success": True, "download_url": "https://cdn.example/out.mp4"})

        def factory(timeout: float) -> httpx.AsyncClient:
            return httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=timeout)

        _, structured = await dispatch_tool(
            "merge_videos",
            {"video_urls": ["https://example.com/a.mp4", "https://example.com/b.mp4"]},
            "secret-key",
            client_factory=factory,
        )

        self.assertEqual(captured["method"], "POST")
        self.assertEqual(captured["url"], "https://ffmpegapi.net/api/merge_videos")
        self.assertEqual(captured["api_key"], "secret-key")
        self.assertEqual(captured["body"]["video_urls"], ["https://example.com/a.mp4", "https://example.com/b.mp4"])
        self.assertTrue(structured["ok"])

    async def test_get_tool_replaces_path_parameters(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["method"] = request.method
            captured["url"] = str(request.url)
            captured["api_key"] = request.headers.get("x-api-key")
            return httpx.Response(200, json={"success": True, "status": "failed"})

        def factory(timeout: float) -> httpx.AsyncClient:
            return httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=timeout)

        _, structured = await dispatch_tool(
            "get_job_status",
            {"job_id": "job_123"},
            "secret-key",
            client_factory=factory,
        )

        self.assertEqual(captured["method"], "GET")
        self.assertEqual(captured["url"], "https://ffmpegapi.net/api/job/job_123/status")
        self.assertEqual(captured["api_key"], "secret-key")
        self.assertEqual(structured["response"]["status"], "failed")


class McpSecurityTests(unittest.TestCase):
    def test_missing_api_key_returns_401(self):
        with TestClient(create_app()) as client:
            response = client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                headers={"host": "localhost:8000", "accept": "application/json, text/event-stream"},
            )

        self.assertEqual(response.status_code, 401)
        self.assertIn("X-API-Key", response.text)

    def test_invalid_origin_returns_403(self):
        with TestClient(create_app()) as client:
            response = client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                headers={
                    "host": "localhost:8000",
                    "origin": "https://evil.example",
                    "x-api-key": "secret-key",
                    "accept": "application/json, text/event-stream",
                },
            )

        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
