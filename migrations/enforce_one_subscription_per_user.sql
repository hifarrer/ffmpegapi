-- Keep one canonical subscription row per user, then enforce the one-to-one
-- relationship already declared by the application model.
BEGIN;

WITH ranked AS (
    SELECT
        id,
        ROW_NUMBER() OVER (
            PARTITION BY user_id
            ORDER BY
                CASE status
                    WHEN 'admin_granted' THEN 0
                    WHEN 'active' THEN 1
                    WHEN 'trialing' THEN 2
                    ELSE 3
                END,
                updated_at DESC NULLS LAST,
                id DESC
        ) AS row_number
    FROM user_subscriptions
)
DELETE FROM user_subscriptions
WHERE id IN (SELECT id FROM ranked WHERE row_number > 1);

ALTER TABLE user_subscriptions
    ADD CONSTRAINT uq_user_subscriptions_user_id UNIQUE (user_id);

COMMIT;
