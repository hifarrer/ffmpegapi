-- One-time migration for Google OAuth (PostgreSQL).
-- Run if your database already existed before google_id was added.
ALTER TABLE "user" ADD COLUMN IF NOT EXISTS google_id VARCHAR(255);
ALTER TABLE "user" ALTER COLUMN password_hash DROP NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_user_google_id ON "user" (google_id);
