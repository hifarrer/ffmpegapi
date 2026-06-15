import json
import os
import uuid
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SESSION_SECRET", "test-secret")

from main import app
from models import ApiKey, Job, SubscriptionPlan, User, UserSubscription, db


class CompressVideoEndpointTests(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()
        self.api_key = f"ffmpeg_test_{uuid.uuid4().hex}"

        with app.app_context():
            db.create_all()
            plan = SubscriptionPlan.query.filter_by(name="Compress Test").first()
            if not plan:
                plan = SubscriptionPlan(
                    name="Compress Test",
                    description="Test plan",
                    api_calls_per_month=1000,
                    monthly_price=0,
                    yearly_price=0,
                    is_active=True,
                )
                db.session.add(plan)
                db.session.commit()

            user = User(
                username=f"user_{uuid.uuid4().hex}",
                email=f"{uuid.uuid4().hex}@example.com",
                active=True,
                email_verified=True,
            )
            user.set_password("password")
            db.session.add(user)
            db.session.commit()

            key = ApiKey(key=self.api_key, name="Test key", user_id=user.id, is_active=True)
            subscription = UserSubscription(
                user_id=user.id,
                plan_id=plan.id,
                status="active",
                billing_cycle="monthly",
                current_period_start=datetime.utcnow(),
                current_period_end=datetime.utcnow() + timedelta(days=30),
                api_calls_used=0,
            )
            db.session.add_all([key, subscription])
            db.session.commit()

    def post_json(self, payload, api_key=None):
        headers = {"X-API-Key": api_key or self.api_key}
        return self.client.post("/api/compress_video", json=payload, headers=headers)

    def test_missing_api_key_returns_401(self):
        response = self.client.post("/api/compress_video", json={"video_url": "https://example.com/a.mp4"})

        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.get_json()["success"])

    def test_missing_video_url_returns_400(self):
        response = self.post_json({"crf": 28})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "video_url is required")

    def test_invalid_parameters_return_400(self):
        cases = [
            ({"video_url": "https://example.com/a.mp4", "crf": 10}, "crf must be between 18 and 35"),
            ({"video_url": "https://example.com/a.mp4", "preset": "tiny"}, "preset must be one of"),
            ({"video_url": "https://example.com/a.mp4", "max_width": 100}, "max_width must be between 144 and 3840"),
            ({"video_url": "https://example.com/a.mp4", "max_height": 100}, "max_height must be between 144 and 2160"),
            ({"video_url": "https://example.com/a.mp4", "audio_bitrate": "500k"}, "audio_bitrate must be one of"),
            ({"video_url": "https://example.com/a.mp4", "target_size_mb": 0.5}, "target_size_mb must be at least 1"),
        ]

        for payload, expected in cases:
            with self.subTest(payload=payload):
                response = self.post_json(payload)
                self.assertEqual(response.status_code, 400)
                self.assertIn(expected, response.get_json()["error"])

    def test_sync_success_returns_compression_metrics(self):
        captured = {}

        def fake_download(_url, output_path, _file_type):
            with open(output_path, "wb") as handle:
                handle.write(b"0" * 1000)
            return True, "downloaded"

        def fake_compress(_video_path, output_path, **kwargs):
            captured.update(kwargs)
            with open(output_path, "wb") as handle:
                handle.write(b"1" * 400)
            return True, "Video compressed successfully", "crf"

        with patch("main.download_file_from_url", side_effect=fake_download), \
             patch("main.compress_video_with_ffmpeg", side_effect=fake_compress), \
             patch("main.upload_to_storage", return_value="https://cdn.example/compressed.mp4"):
            response = self.post_json({
                "video_url": "https://example.com/video.mp4",
                "crf": 30,
                "preset": "fast",
                "max_width": 1280,
                "audio_bitrate": "96k",
            })

        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["download_url"], "https://cdn.example/compressed.mp4")
        self.assertEqual(payload["original_size_bytes"], 1000)
        self.assertEqual(payload["compressed_size_bytes"], 400)
        self.assertEqual(payload["compression_ratio"], 0.4)
        self.assertEqual(payload["compression_mode"], "crf")
        self.assertEqual(captured["crf"], 30)
        self.assertEqual(captured["preset"], "fast")
        self.assertEqual(captured["max_width"], 1280)
        self.assertEqual(captured["audio_bitrate"], "96k")

    def test_impossible_target_size_returns_400(self):
        def fake_download(_url, output_path, _file_type):
            with open(output_path, "wb") as handle:
                handle.write(b"0" * 1000)
            return True, "downloaded"

        with patch("main.download_file_from_url", side_effect=fake_download), \
             patch(
                 "main.compress_video_with_ffmpeg",
                 return_value=(False, "target_size_mb is too small for the source duration and selected audio_bitrate", None),
             ):
            response = self.post_json({
                "video_url": "https://example.com/video.mp4",
                "target_size_mb": 1,
            })

        self.assertEqual(response.status_code, 400)
        self.assertIn("target_size_mb is too small", response.get_json()["error"])

    def test_async_request_creates_job(self):
        started = {"value": False}

        class FakeThread:
            def __init__(self, target, args):
                self.target = target
                self.args = args
                self.daemon = False

            def start(self):
                started["value"] = True

        with patch("main.threading.Thread", FakeThread):
            response = self.post_json({
                "video_url": "https://example.com/video.mp4",
                "crf": 28,
                "async": True,
            })

        payload = response.get_json()
        self.assertEqual(response.status_code, 202)
        self.assertTrue(payload["success"])
        self.assertTrue(started["value"])

        with app.app_context():
            job = Job.query.filter_by(job_id=payload["job_id"]).first()
            self.assertIsNotNone(job)
            self.assertEqual(job.job_type, "compress_video")
            self.assertEqual(job.status, "pending")
            self.assertEqual(json.loads(job.input_data)["crf"], 28)


if __name__ == "__main__":
    unittest.main()
