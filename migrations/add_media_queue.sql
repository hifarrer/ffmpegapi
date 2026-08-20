-- Durable bounded media queue settings and worker leases.
ALTER TABLE site_settings
    ADD COLUMN IF NOT EXISTS concurrent_jobs INTEGER NOT NULL DEFAULT 2;

ALTER TABLE jobs ADD COLUMN IF NOT EXISTS started_at TIMESTAMP;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS finished_at TIMESTAMP;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS worker_id VARCHAR(128);
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMP;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS attempt_count INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS ix_jobs_status_created_at ON jobs (status, created_at, id);
CREATE INDEX IF NOT EXISTS ix_jobs_worker_id ON jobs (worker_id);
CREATE INDEX IF NOT EXISTS ix_jobs_lease_expires_at ON jobs (lease_expires_at);
