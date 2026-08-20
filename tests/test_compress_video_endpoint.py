import json
import os
import uuid
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SESSION_SECRET", "test-secret")

from main import app
from models import ApiKey, Job, SiteSettings, SubscriptionPlan, User, UserSubscription, db


class CompressVideoEndpointTests(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()
        self.api_key = f"ffmpeg_test_{uuid.uuid4().hex}"

        with app.app_context():
            db.create_all()
            Job.query.delete()
            SiteSettings.get_settings().concurrent_jobs = 2
            db.session.commit()
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
            self.user_id = user.id

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

        def fake_download(_url, output_path, _file_type, max_bytes=None):
            captured["max_bytes"] = max_bytes
            with open(output_path, "wb") as handle:
                handle.write(b"0" * 1000)
            return True, "downloaded"

        def fake_compress(_video_path, output_path, **kwargs):
            captured.update(kwargs)
            with open(output_path, "wb") as handle:
                handle.write(b"1" * 400)
            return True, "Video compressed successfully", "crf"

        with patch("main.get_remote_file_size_bytes", return_value=(None, None)), \
             patch("main.download_file_from_url", side_effect=fake_download), \
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
        self.assertIsNotNone(captured["max_bytes"])

    def test_impossible_target_size_returns_400(self):
        def fake_download(_url, output_path, _file_type, max_bytes=None):
            with open(output_path, "wb") as handle:
                handle.write(b"0" * 1000)
            return True, "downloaded"

        with patch("main.get_remote_file_size_bytes", return_value=(None, None)), \
             patch("main.download_file_from_url", side_effect=fake_download), \
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

    def test_preflight_oversize_video_returns_413(self):
        detected_size = 501 * 1024 * 1024

        with patch("main.get_remote_file_size_bytes", return_value=(detected_size, None)), \
             patch("main.COMPRESS_VIDEO_MAX_INPUT_BYTES", 500 * 1024 * 1024), \
             patch("main.COMPRESS_VIDEO_MAX_INPUT_MB", 500), \
             patch("main.process_compress_video_payload") as process_payload:
            response = self.post_json({"video_url": "https://example.com/video.mp4"})

        payload = response.get_json()
        self.assertEqual(response.status_code, 413)
        self.assertFalse(payload["success"])
        self.assertEqual(payload["detected_size_bytes"], detected_size)
        self.assertIn("maximum supported size", payload["error"])
        process_payload.assert_not_called()

    def test_streamed_oversize_download_returns_413(self):
        with patch("main.get_remote_file_size_bytes", return_value=(None, None)), \
             patch("main.download_file_from_url", return_value=(False, "Video exceeds maximum supported size of 500 MB")), \
             patch("main.compress_video_with_ffmpeg") as compress:
            response = self.post_json({"video_url": "https://example.com/video.mp4"})

        self.assertEqual(response.status_code, 413)
        self.assertIn("maximum supported size", response.get_json()["error"])
        compress.assert_not_called()

    def test_large_sync_request_auto_creates_async_job(self):
        detected_size = 101 * 1024 * 1024

        with patch("main.get_remote_file_size_bytes", return_value=(detected_size, None)), \
             patch("main.COMPRESS_VIDEO_MAX_INPUT_BYTES", 500 * 1024 * 1024), \
             patch("main.COMPRESS_VIDEO_SYNC_MAX_BYTES", 100 * 1024 * 1024):
            response = self.post_json({
                "video_url": "https://example.com/video.mp4",
                "crf": 28,
            })

        payload = response.get_json()
        self.assertEqual(response.status_code, 202)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["detected_size_bytes"], detected_size)
        self.assertIn("synchronous compression limit", payload["message"])

        with app.app_context():
            job = Job.query.filter_by(job_id=payload["job_id"]).first()
            self.assertIsNotNone(job)
            self.assertEqual(job.job_type, "compress_video")
            queued_input = json.loads(job.input_data)
            self.assertTrue(queued_input["_requested_async"])
            self.assertEqual(queued_input["_queued_json"]["crf"], 28)

    def test_async_request_creates_job(self):
        with patch("main.get_remote_file_size_bytes", return_value=(None, None)):
            response = self.post_json({
                "video_url": "https://example.com/video.mp4",
                "crf": 28,
                "async": True,
            })

        payload = response.get_json()
        self.assertEqual(response.status_code, 202)
        self.assertTrue(payload["success"])

        with app.app_context():
            job = Job.query.filter_by(job_id=payload["job_id"]).first()
            self.assertIsNotNone(job)
            self.assertEqual(job.job_type, "compress_video")
            self.assertEqual(job.status, "pending")
            queued_input = json.loads(job.input_data)
            self.assertTrue(queued_input["_requested_async"])
            self.assertEqual(queued_input["_queued_json"]["crf"], 28)

    def test_sync_request_is_automatically_queued_when_capacity_is_busy(self):
        with app.app_context():
            settings = SiteSettings.get_settings()
            settings.concurrent_jobs = 1
            blocker = Job(
                user_id=self.user_id,
                job_type="queue-blocker",
                status="processing",
                input_data="{}",
                worker_id="other-replica",
                lease_expires_at=datetime.utcnow() + timedelta(minutes=5),
                attempt_count=1,
            )
            db.session.add(blocker)
            db.session.commit()

        with patch("main.get_remote_file_size_bytes", return_value=(None, None)):
            response = self.post_json({
                "video_url": "https://example.com/video.mp4",
                "crf": 28,
            })

        payload = response.get_json()
        self.assertEqual(response.status_code, 202)
        self.assertEqual(payload["status"], "pending")
        self.assertEqual(payload["queue_position"], 1)


if __name__ == "__main__":
    unittest.main()
