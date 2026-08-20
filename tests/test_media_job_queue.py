import io
import os
import sys
import threading
import time
import unittest
import uuid
from datetime import datetime, timedelta
from flask import jsonify, request

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SESSION_SECRET", "test-secret")

from job_queue import MediaJobQueue
from main import (
    Job,
    SiteSettings,
    User,
    _BoundedDiskTail,
    _bounded_subprocess_run,
    _execute_queued_media_request,
    _queued_media_handlers,
    _serialize_media_request,
    app,
    db,
)


class MediaJobQueueTests(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        with app.app_context():
            db.create_all()
            Job.query.delete()
            db.session.commit()
            self.user = User(
                username=f"queue-{uuid.uuid4().hex}",
                email=f"queue-{uuid.uuid4().hex}@example.com",
                email_verified=True,
            )
            self.user.set_password("password")
            db.session.add(self.user)
            settings = SiteSettings.get_settings()
            settings.concurrent_jobs = 2
            db.session.commit()
            self.user_id = self.user.id

    def tearDown(self):
        if hasattr(self, "queue"):
            self.queue.stop()

    def _new_job(self, created_offset=0, **kwargs):
        with app.app_context():
            job = Job(
                user_id=self.user_id,
                job_type="queue_test",
                status=kwargs.pop("status", "pending"),
                input_data="{}",
                created_at=datetime.utcnow() + timedelta(seconds=created_offset),
                **kwargs,
            )
            db.session.add(job)
            db.session.commit()
            return job.job_id

    def test_fifo_dispatch_never_exceeds_two_jobs(self):
        release = threading.Event()
        two_started = threading.Event()
        started = []
        started_lock = threading.Lock()

        def processor(job_id, worker_id):
            with started_lock:
                started.append(job_id)
                if len(started) == 2:
                    two_started.set()
            release.wait(5)
            return {"payload": {"success": True}, "status_code": 200}

        self.queue = MediaJobQueue(app, db, Job, SiteSettings, processor, poll_seconds=60)
        job_ids = [self._new_job(index) for index in range(3)]
        claimed = self.queue.dispatch_now()
        self.assertTrue(two_started.wait(2))
        self.assertEqual(list(claimed), job_ids[:2])
        self.assertEqual(self.queue.active_count(), 2)
        with app.app_context():
            self.assertEqual(Job.query.filter_by(job_id=job_ids[2]).one().status, "pending")

        release.set()
        for future in claimed.values():
            future.result(timeout=2)
        with app.app_context():
            Job.query.filter(Job.job_id.in_(job_ids[:2])).update(
                {
                    Job.status: "completed",
                    Job.worker_id: None,
                    Job.lease_expires_at: None,
                    Job.finished_at: datetime.utcnow(),
                },
                synchronize_session=False,
            )
            db.session.commit()
        deadline = time.time() + 2
        while self.queue.active_count() and time.time() < deadline:
            time.sleep(0.01)
        third = self.queue.dispatch_now()
        self.assertIn(job_ids[2], third)
        third[job_ids[2]].result(timeout=2)

    def test_expired_job_at_retry_limit_is_failed(self):
        job_id = self._new_job(
            status="processing",
            lease_expires_at=datetime.utcnow() - timedelta(minutes=1),
            attempt_count=3,
        )
        self.queue = MediaJobQueue(
            app,
            db,
            Job,
            SiteSettings,
            lambda *_: {"payload": {"success": True}, "status_code": 200},
            poll_seconds=60,
        )
        self.queue.dispatch_now()
        with app.app_context():
            job = Job.query.filter_by(job_id=job_id).one()
            self.assertEqual(job.status, "failed")
            self.assertIsNotNone(job.finished_at)

    def test_runtime_limit_changes_only_affect_new_claims(self):
        release = threading.Event()
        started = []
        started_lock = threading.Lock()

        def processor(job_id, worker_id):
            with started_lock:
                started.append(job_id)
            release.wait(5)
            return {"payload": {"success": True}, "status_code": 200}

        with app.app_context():
            settings = SiteSettings.get_settings()
            settings.concurrent_jobs = 1
            db.session.commit()

        self.queue = MediaJobQueue(app, db, Job, SiteSettings, processor, poll_seconds=60)
        job_ids = [self._new_job(index) for index in range(3)]
        first = self.queue.dispatch_now()
        self.assertEqual(list(first), job_ids[:1])

        with app.app_context():
            settings = SiteSettings.get_settings()
            settings.concurrent_jobs = 2
            db.session.commit()
        second = self.queue.dispatch_now()
        self.assertEqual(list(second), job_ids[1:2])

        with app.app_context():
            settings = SiteSettings.get_settings()
            settings.concurrent_jobs = 1
            db.session.commit()
        self.assertEqual(self.queue.dispatch_now(), {})
        self.assertEqual(self.queue.active_count(), 2)
        self.assertNotIn(job_ids[2], started)

        release.set()
        for future in [*first.values(), *second.values()]:
            future.result(timeout=2)

    def test_second_worker_cannot_claim_an_already_leased_job(self):
        release = threading.Event()

        def processor(job_id, worker_id):
            release.wait(5)
            return {"payload": {"success": True}, "status_code": 200}

        self.queue = MediaJobQueue(app, db, Job, SiteSettings, processor, poll_seconds=60)
        other_queue = MediaJobQueue(app, db, Job, SiteSettings, processor, poll_seconds=60)
        self.addCleanup(other_queue.stop)
        job_id = self._new_job()

        claimed = self.queue.dispatch_now()
        self.assertIn(job_id, claimed)
        self.assertEqual(other_queue.dispatch_now(), {})

        release.set()
        claimed[job_id].result(timeout=2)


class BoundedSubprocessTests(unittest.TestCase):
    def test_capture_is_limited_to_tail(self):
        result = _bounded_subprocess_run(
            [sys.executable, "-c", "import sys; sys.stdout.write('a' * 1200000 + 'TAIL')"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0)
        self.assertLessEqual(len(result.stdout.encode()), 1024 * 1024)
        self.assertTrue(result.stdout.endswith("TAIL"))

    def test_disk_capture_is_physically_bounded(self):
        capture = _BoundedDiskTail(max_bytes=1024)
        try:
            capture.write(b"a" * 5000)
            capture.write(b"TAIL")
            capture.handle.seek(0, os.SEEK_END)
            self.assertLessEqual(capture.handle.tell(), 1024)
            self.assertTrue(capture.read(False).endswith(b"TAIL"))
        finally:
            capture.close()


class QueueCoverageTests(unittest.TestCase):
    def test_every_local_media_endpoint_is_registered(self):
        expected = {
            "merge_image_audio",
            "merge_videos",
            "neonvideo_merge_videos",
            "picture_in_picture",
            "add_watermark",
            "split_audio",
            "split_audio_segments",
            "split_audio_time",
            "add_subtitles",
            "trim_audio",
            "trim_video",
            "split_video",
            "video_loop",
            "endless_loop",
            "get_first_frame_image",
            "get_last_frame_image",
            "compress_video",
            "extract_audio_mp3",
            "convert_video_to_gif",
            "convert_to_vertical",
            "convert_to_tiktok_portrait",
            "add_tiktok_captions",
            "add_text_overlay_captions",
        }
        self.assertEqual(set(_queued_media_handlers), expected)
        self.assertNotIn("youtube_to_mp4", _queued_media_handlers)

    def test_multipart_request_is_spooled_replayed_and_cleaned(self):
        def multipart_handler():
            return jsonify({
                "success": True,
                "label": request.form["label"],
                "content": request.files["media"].read().decode("utf-8"),
            })

        _queued_media_handlers["multipart_test"] = multipart_handler
        try:
            with app.test_request_context(
                "/api/multipart-test",
                method="POST",
                data={
                    "async": "true",
                    "label": "sample",
                    "media": (io.BytesIO(b"media-bytes"), "clip.mp4"),
                },
            ):
                serialized = _serialize_media_request()

            spool_path = serialized["_queued_files"][0]["path"]
            self.assertTrue(os.path.exists(spool_path))
            self.assertTrue(serialized["_requested_async"])

            job = Job(job_type="multipart_test", status="processing", input_data="{}")
            with app.app_context():
                result = _execute_queued_media_request(job, serialized)

            self.assertTrue(result["success"])
            self.assertEqual(result["label"], "sample")
            self.assertEqual(result["content"], "media-bytes")
            self.assertFalse(os.path.exists(spool_path))
        finally:
            _queued_media_handlers.pop("multipart_test", None)


if __name__ == "__main__":
    unittest.main()
