import os
import unittest
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SESSION_SECRET", "test-secret")

from main import app, create_endless_loop_with_ffmpeg
from models import ApiKey, ApiLog, Job, SubscriptionPlan, User, UserSubscription, db


class EndlessLoopEndpointTests(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()
        self.api_key = f"ffmpeg_test_{uuid.uuid4().hex}"

        with app.app_context():
            db.create_all()
            Job.query.delete()
            db.session.commit()
            plan = SubscriptionPlan.query.filter_by(name="Endless Loop Test").first()
            if not plan:
                plan = SubscriptionPlan(
                    name="Endless Loop Test",
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

    def post_json(self, payload):
        return self.client.post(
            "/api/endless_loop",
            json=payload,
            headers={"X-API-Key": self.api_key},
        )

    def test_missing_video_url_returns_400(self):
        response = self.post_json({"duration": 30})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "video_url is required")

    def test_invalid_duration_returns_400(self):
        cases = [
            ({}, "duration is required"),
            ({"duration": 0}, "duration must be a positive number of seconds"),
            ({"duration": -1}, "duration must be a positive number of seconds"),
            ({"duration": "abc"}, "duration must be a positive number of seconds"),
        ]

        for partial_payload, expected_error in cases:
            with self.subTest(partial_payload=partial_payload):
                payload = {"video_url": "https://example.com/clip.mp4"}
                payload.update(partial_payload)
                response = self.post_json(payload)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.get_json()["error"], expected_error)

        response = self.client.post(
            "/api/endless_loop",
            data='{"video_url": "https://example.com/clip.mp4", "duration": 1e999}',
            content_type="application/json",
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "duration must be a positive number of seconds")

    def test_job_status_request_is_recorded_in_api_history(self):
        with app.app_context():
            key = ApiKey.query.filter_by(key=self.api_key).one()
            job = Job(
                user_id=key.user_id,
                job_type='endless_loop',
                status='pending',
            )
            db.session.add(job)
            db.session.commit()
            job_id = job.job_id
            user_id = key.user_id
            api_key_id = key.id

        response = self.client.get(
            f'/api/job/{job_id}/status',
            headers={'X-API-Key': self.api_key},
        )

        self.assertEqual(response.status_code, 200)
        with app.app_context():
            log = ApiLog.query.filter_by(
                user_id=user_id,
                api_key_id=api_key_id,
                endpoint=f'/api/job/{job_id}/status',
            ).one()
            self.assertEqual(log.method, 'GET')
            self.assertEqual(log.status_code, 200)

    def test_success_reports_loop_math_for_partial_final_loop(self):
        captured = {}

        def fake_download(_url, output_path):
            with open(output_path, "wb") as handle:
                handle.write(b"video")
            return True, "downloaded"

        def fake_loop(_video_path, output_path, duration):
            captured["duration"] = duration
            with open(output_path, "wb") as handle:
                handle.write(b"looped")
            return True, "Endless loop created successfully"

        with patch("main.download_video_from_url", side_effect=fake_download), \
             patch("main.get_video_duration", return_value=(120.0, None)), \
             patch("main.create_endless_loop_with_ffmpeg", side_effect=fake_loop), \
             patch("main.upload_to_storage", return_value="https://cdn.example/endless.mp4"):
            response = self.post_json({
                "video_url": "https://example.com/clip.mp4",
                "duration": 1205,
            })

        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["download_url"], "https://cdn.example/endless.mp4")
        self.assertEqual(payload["loops_required"], 11)
        self.assertEqual(payload["estimated_full_loops"], 10)
        self.assertEqual(payload["partial_final_loop_seconds"], 5)
        self.assertEqual(payload["target_duration_seconds"], 1205)
        self.assertEqual(captured["duration"], 1205)

    def test_success_supports_target_shorter_than_source(self):
        def fake_download(_url, output_path):
            with open(output_path, "wb") as handle:
                handle.write(b"video")
            return True, "downloaded"

        def fake_loop(_video_path, output_path, _duration):
            with open(output_path, "wb") as handle:
                handle.write(b"looped")
            return True, "Endless loop created successfully"

        with patch("main.download_video_from_url", side_effect=fake_download), \
             patch("main.get_video_duration", return_value=(120.0, None)), \
             patch("main.create_endless_loop_with_ffmpeg", side_effect=fake_loop), \
             patch("main.upload_to_storage", return_value="https://cdn.example/endless.mp4"):
            response = self.post_json({
                "video_url": "https://example.com/clip.mp4",
                "duration": 30,
            })

        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["loops_required"], 1)
        self.assertEqual(payload["estimated_full_loops"], 0)
        self.assertEqual(payload["partial_final_loop_seconds"], 30)

    def test_success_applies_watermark(self):
        calls = {"watermark": False}

        def fake_video_download(_url, output_path):
            with open(output_path, "wb") as handle:
                handle.write(b"video")
            return True, "downloaded"

        def fake_file_download(_url, output_path, _file_type):
            with open(output_path, "wb") as handle:
                handle.write(b"watermark")
            return True, "downloaded"

        def fake_loop(_video_path, output_path, _duration):
            with open(output_path, "wb") as handle:
                handle.write(b"looped")
            return True, "Endless loop created successfully"

        def fake_watermark(_video_path, _watermark_path, output_path):
            calls["watermark"] = True
            with open(output_path, "wb") as handle:
                handle.write(b"watermarked")
            return True, "Watermark added successfully"

        with patch("main.download_video_from_url", side_effect=fake_video_download), \
             patch("main.download_file_from_url", side_effect=fake_file_download), \
             patch("main.get_video_duration", return_value=(120.0, None)), \
             patch("main.create_endless_loop_with_ffmpeg", side_effect=fake_loop), \
             patch("main.add_watermark_with_ffmpeg", side_effect=fake_watermark), \
             patch("main.upload_to_storage", return_value="https://cdn.example/watermarked.mp4"):
            response = self.post_json({
                "video_url": "https://example.com/clip.mp4",
                "duration": 1205,
                "watermark_url": "https://example.com/logo.png",
            })

        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(calls["watermark"])
        self.assertIn("_endless_loop_watermarked.mp4", payload["filename"])


class EndlessLoopFfmpegTests(unittest.TestCase):
    def test_helper_uses_stream_loop_and_target_duration(self):
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["kwargs"] = kwargs
            return SimpleNamespace(returncode=0, stderr="")

        with patch("main.subprocess.run", side_effect=fake_run):
            success, message = create_endless_loop_with_ffmpeg("input.mp4", "output.mp4", 1205.5)

        self.assertTrue(success)
        self.assertEqual(message, "Endless loop created successfully")
        self.assertIn("-stream_loop", captured["cmd"])
        stream_loop_index = captured["cmd"].index("-stream_loop")
        self.assertEqual(captured["cmd"][stream_loop_index + 1], "-1")
        self.assertIn("-t", captured["cmd"])
        duration_index = captured["cmd"].index("-t")
        self.assertEqual(captured["cmd"][duration_index + 1], "1205.5")


if __name__ == "__main__":
    unittest.main()
