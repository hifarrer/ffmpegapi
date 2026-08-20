"""Durable, bounded job dispatch for local media processing."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import logging
import os
import threading
import uuid

from sqlalchemy import and_, or_


class MediaJobQueue:
    """Claim jobs from PostgreSQL and run only the configured number at once."""

    def __init__(
        self,
        app,
        db,
        job_model,
        settings_model,
        processor,
        *,
        max_workers=8,
        lease_seconds=300,
        heartbeat_seconds=30,
        poll_seconds=2,
        max_attempts=3,
    ):
        self.app = app
        self.db = db
        self.Job = job_model
        self.SiteSettings = settings_model
        self.processor = processor
        self.max_workers = max_workers
        self.lease_seconds = lease_seconds
        self.heartbeat_seconds = heartbeat_seconds
        self.poll_seconds = poll_seconds
        self.max_attempts = max_attempts
        replica = os.environ.get("RAILWAY_REPLICA_ID", "local")
        self.worker_id = f"{replica}:{os.getpid()}:{uuid.uuid4().hex[:10]}"
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="media-job")
        self._active = {}
        self._active_lock = threading.RLock()
        self._dispatch_lock = threading.Lock()
        self._wake_event = threading.Event()
        self._stop_event = threading.Event()
        self._started = False
        self._start_lock = threading.Lock()

    def ensure_started(self):
        with self._start_lock:
            if self._started:
                return
            self._started = True
            threading.Thread(target=self._dispatch_loop, name="media-dispatcher", daemon=True).start()
            threading.Thread(target=self._heartbeat_loop, name="media-heartbeat", daemon=True).start()
            logging.info("Media queue started as %s", self.worker_id)

    def stop(self):
        self._stop_event.set()
        self._wake_event.set()
        self._executor.shutdown(wait=False, cancel_futures=False)

    def wake(self):
        self.ensure_started()
        self._wake_event.set()

    def dispatch_now(self):
        """Claim available FIFO work and return futures claimed by this call."""
        self.ensure_started()
        return self._claim_and_submit(blocking=True)

    def active_count(self):
        with self._active_lock:
            return len(self._active)

    def future_for(self, job_id):
        with self._active_lock:
            return self._active.get(job_id)

    def _dispatch_loop(self):
        while not self._stop_event.is_set():
            self._wake_event.wait(self.poll_seconds)
            self._wake_event.clear()
            if self._stop_event.is_set():
                break
            if self.app.config.get('TESTING') and not self.app.config.get('MEDIA_QUEUE_BACKGROUND_IN_TESTS', False):
                continue
            try:
                self._claim_and_submit()
            except Exception:
                logging.exception("Media queue dispatch failed")

    def _heartbeat_loop(self):
        while not self._stop_event.wait(self.heartbeat_seconds):
            with self._active_lock:
                active_ids = list(self._active)
            if not active_ids:
                continue
            try:
                with self.app.app_context():
                    expires = datetime.utcnow() + timedelta(seconds=self.lease_seconds)
                    self.Job.query.filter(
                        self.Job.job_id.in_(active_ids),
                        self.Job.worker_id == self.worker_id,
                        self.Job.status == "processing",
                    ).update({self.Job.lease_expires_at: expires}, synchronize_session=False)
                    self.db.session.commit()
            except Exception:
                logging.exception("Unable to renew media job leases")
                with self.app.app_context():
                    self.db.session.rollback()
                    self.db.session.remove()

    def _claim_and_submit(self, blocking=False):
        claimed = []
        futures = {}
        if not self._dispatch_lock.acquire(blocking=blocking):
            return futures
        try:
            with self.app.app_context():
                now = datetime.utcnow()
                settings = self.SiteSettings.query.order_by(self.SiteSettings.id).with_for_update().first()
                if settings is None:
                    settings = self.SiteSettings(concurrent_jobs=2)
                    self.db.session.add(settings)
                    self.db.session.flush()
                limit = max(1, min(self.max_workers, int(settings.concurrent_jobs or 2)))

                # Poison jobs are failed instead of being reclaimed forever after crashes.
                exhausted = self.Job.query.filter(
                    self.Job.status == "processing",
                    or_(self.Job.lease_expires_at.is_(None), self.Job.lease_expires_at <= now),
                    self.Job.attempt_count >= self.max_attempts,
                ).all()
                for job in exhausted:
                    job.status = "failed"
                    job.error_message = "Job could not be recovered after repeated worker interruptions"
                    job.finished_at = now
                    job.updated_at = now
                    job.worker_id = None
                    job.lease_expires_at = None

                active_leases = self.Job.query.filter(
                    self.Job.status == "processing",
                    self.Job.lease_expires_at > now,
                ).count()
                capacity = max(0, limit - active_leases)
                if capacity:
                    candidates = self.Job.query.filter(
                        or_(
                            self.Job.status == "pending",
                            and_(
                                self.Job.status == "processing",
                                or_(self.Job.lease_expires_at.is_(None), self.Job.lease_expires_at <= now),
                                self.Job.attempt_count < self.max_attempts,
                            ),
                        )
                    ).order_by(self.Job.created_at.asc(), self.Job.id.asc()).with_for_update(skip_locked=True).limit(capacity).all()
                    expires = now + timedelta(seconds=self.lease_seconds)
                    for job in candidates:
                        job.status = "processing"
                        job.worker_id = self.worker_id
                        job.lease_expires_at = expires
                        job.attempt_count = int(job.attempt_count or 0) + 1
                        job.started_at = job.started_at or now
                        job.updated_at = now
                        claimed.append(job.job_id)
                self.db.session.commit()
                self.db.session.remove()

            for job_id in claimed:
                future = self._executor.submit(self.processor, job_id, self.worker_id)
                with self._active_lock:
                    self._active[job_id] = future
                future.add_done_callback(lambda done, jid=job_id: self._job_finished(jid, done))
                futures[job_id] = future
            return futures
        except Exception:
            with self.app.app_context():
                self.db.session.rollback()
                self.db.session.remove()
            raise
        finally:
            self._dispatch_lock.release()

    def _job_finished(self, job_id, future):
        with self._active_lock:
            self._active.pop(job_id, None)
        try:
            future.result()
        except Exception:
            logging.exception("Unhandled media job failure for %s", job_id)
        self._wake_event.set()

    def counts(self):
        with self.app.app_context():
            now = datetime.utcnow()
            pending = self.Job.query.filter_by(status="pending").count()
            running = self.Job.query.filter(
                self.Job.status == "processing",
                or_(self.Job.lease_expires_at.is_(None), self.Job.lease_expires_at > now),
            ).count()
            return {"pending": pending, "running": running}

    def queue_position(self, job):
        if job.status != "pending":
            return None
        earlier = self.Job.query.filter(
            self.Job.status == "pending",
            or_(
                self.Job.created_at < job.created_at,
                and_(self.Job.created_at == job.created_at, self.Job.id < job.id),
            ),
        ).count()
        return earlier + 1
