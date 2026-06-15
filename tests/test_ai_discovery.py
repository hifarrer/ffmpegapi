import json
import unittest

from ai_discovery import (
    ENDPOINTS,
    error_examples_for_endpoint,
    generate_app_submission_markdown,
    generate_llms_txt,
    generate_openapi_spec,
    generate_skill_markdown,
    request_example_for_endpoint,
    request_schema_for_endpoint,
    response_examples_for_endpoint,
    response_schema_for_endpoint,
)


class AiDiscoveryCatalogTests(unittest.TestCase):
    def test_each_endpoint_has_agent_contract_metadata(self):
        operation_ids = [endpoint["operation_id"] for endpoint in ENDPOINTS]
        self.assertEqual(len(operation_ids), len(set(operation_ids)))

        for endpoint in ENDPOINTS:
            with self.subTest(endpoint=endpoint["operation_id"]):
                request_schema = request_schema_for_endpoint(endpoint)
                self.assertEqual(request_schema["type"], "object")
                self.assertIn("properties", request_schema)
                self.assertIn("additionalProperties", request_schema)

                request_example = request_example_for_endpoint(endpoint)
                self.assertTrue(request_example)

                response_schema = response_schema_for_endpoint(endpoint)
                self.assertEqual(response_schema["type"], "object")
                self.assertIn("properties", response_schema)

                success_examples = response_examples_for_endpoint(endpoint)
                self.assertIn("success", success_examples)
                self.assertTrue(success_examples["success"]["value"])

                error_examples = error_examples_for_endpoint(endpoint, 400)
                self.assertIn("error", error_examples)
                self.assertFalse(error_examples["error"]["value"]["success"])

    def test_llm_markdown_mentions_agent_discovery_surfaces(self):
        llms = generate_llms_txt()
        self.assertIn("Hosted FFmpeg API alternative", llms)
        self.assertIn("/openapi.json", llms)
        self.assertIn("/skill.md", llms)
        self.assertIn("https://mcp.ffmpegapi.net/mcp", llms)

        skill = generate_skill_markdown()
        self.assertIn("When to Use", skill)
        self.assertIn("X-API-Key", skill)

        submission = generate_app_submission_markdown()
        self.assertIn("MCP server URL", submission)
        self.assertIn("/privacy", submission)
        self.assertIn("/terms", submission)


class OpenApiDiscoveryTests(unittest.TestCase):
    def test_openapi_has_all_public_endpoint_contracts(self):
        spec = generate_openapi_spec()
        self.assertEqual(spec["openapi"], "3.1.0")
        self.assertEqual(len(spec["paths"]), 24)
        self.assertIn("ErrorResponse", spec["components"]["schemas"])
        self.assertIn("AsyncJobResponse", spec["components"]["schemas"])
        self.assertIn("CompressVideoResponse", spec["components"]["schemas"])
        self.assertIn("/api/compress_video", spec["paths"])
        self.assertEqual(
            spec["paths"]["/api/compress_video"]["post"]["operationId"],
            "compressVideo",
        )

        for endpoint in ENDPOINTS:
            with self.subTest(endpoint=endpoint["operation_id"]):
                operation = spec["paths"][endpoint["path"]][endpoint["method"].lower()]
                response_content = operation["responses"]["200"]["content"]["application/json"]
                self.assertIn("examples", response_content)
                self.assertIn("schema", response_content)
                response_text = json.dumps(response_content["examples"])
                self.assertNotIn('"string"', response_text)

                if endpoint["method"] != "GET":
                    request_content = operation["requestBody"]["content"]["application/json"]
                    self.assertIn("examples", request_content)
                    schema_text = json.dumps(request_content["schema"]).lower()
                    self.assertNotIn("api_key", schema_text)
                    self.assertNotIn("x-api-key", schema_text)

    def test_openapi_error_responses_have_examples(self):
        spec = generate_openapi_spec()
        for path_item in spec["paths"].values():
            for operation in path_item.values():
                for status_code in ("400", "401", "500"):
                    content = operation["responses"][status_code]["content"]["application/json"]
                    self.assertIn("examples", content)
                    self.assertFalse(content["examples"]["error"]["value"]["success"])


if __name__ == "__main__":
    unittest.main()
