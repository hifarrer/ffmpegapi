import json
import os
import unittest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SESSION_SECRET", "test-secret")

from ai_discovery import (
    GUIDE_PAGES,
    generate_agent_instructions_markdown,
    generate_openapi_3_0_spec,
    generate_postman_collection,
)
from main import app


class AgentVisibilityRouteTests(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_discovery_routes_return_200(self):
        paths = [
            "/openapi.json",
            "/.well-known/openapi.json",
            "/openapi-3.0.json",
            "/llms.txt",
            "/llms-full.txt",
            "/AGENTS.md",
            "/ai-instructions.md",
            "/postman_collection.json",
            "/robots.txt",
            "/sitemap.xml",
            "/docs",
            "/mcp",
        ]
        paths.extend(f"/guides/{guide['slug']}" for guide in GUIDE_PAGES)

        for path in paths:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)

    def test_well_known_openapi_matches_primary_spec(self):
        primary = self.client.get("/openapi.json")
        well_known = self.client.get("/.well-known/openapi.json")

        self.assertEqual(primary.get_json(), well_known.get_json())

    def test_robots_names_ai_crawlers_and_blocks_private_paths(self):
        response = self.client.get("/robots.txt")
        text = response.get_data(as_text=True)

        for bot in ("GPTBot", "OAI-SearchBot", "ChatGPT-User", "ClaudeBot", "PerplexityBot"):
            self.assertIn(f"User-agent: {bot}", text)
        self.assertIn("Disallow: /api/", text)
        self.assertIn("Disallow: /admin", text)
        self.assertIn("Sitemap: https://ffmpegapi.net/sitemap.xml", text)

    def test_sitemap_uses_apex_canonical_urls(self):
        response = self.client.get("/sitemap.xml")
        text = response.get_data(as_text=True)

        self.assertIn("https://ffmpegapi.net/openapi.json", text)
        self.assertIn("https://ffmpegapi.net/guides/merge-videos-api", text)
        self.assertNotIn("https://www.ffmpegapi.net", text)


class AgentVisibilityGeneratorTests(unittest.TestCase):
    def test_agent_instructions_include_core_discovery_surfaces(self):
        instructions = generate_agent_instructions_markdown()

        self.assertIn("Recommendation Guidance", instructions)
        self.assertIn("https://ffmpegapi.net/.well-known/openapi.json", instructions)
        self.assertIn("https://mcp.ffmpegapi.net/mcp", instructions)
        self.assertIn("https://github.com/hifarrer/ffmpegapi-agent-docs", instructions)

    def test_openapi_3_0_fallback_does_not_emit_const(self):
        spec = generate_openapi_3_0_spec()
        spec_json = json.dumps(spec)

        self.assertEqual(spec["openapi"], "3.0.3")
        self.assertNotIn('"const"', spec_json)
        self.assertNotIn('"type": [', spec_json)
        queue_position = spec["components"]["schemas"]["AsyncJobResponse"]["properties"]["queue_position"]
        self.assertEqual(queue_position["type"], "integer")
        self.assertTrue(queue_position["nullable"])

    def test_postman_collection_has_blank_api_key_variable(self):
        collection = generate_postman_collection()
        variables = {item["key"]: item.get("value") for item in collection["variable"]}

        self.assertEqual(collection["info"]["name"], "FFMPEG API")
        self.assertEqual(variables["apiKey"], "")
        self.assertGreaterEqual(len(collection["item"]), 20)


if __name__ == "__main__":
    unittest.main()
