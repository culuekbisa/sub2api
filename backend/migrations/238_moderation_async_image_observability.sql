ALTER TABLE content_moderation_logs
    ADD COLUMN IF NOT EXISTS moderation_endpoint_id VARCHAR(128) NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS moderation_endpoint_name VARCHAR(255) NOT NULL DEFAULT '';

-- Some deployments include the optional async image worker schema while the
-- standard v0.2.2 image path does not. Keep this migration safe for both
-- layouts: endpoint observability is required for moderation logs, whereas
-- async-image metadata is applied only when that table exists.
ALTER TABLE IF EXISTS async_image_tasks
    ADD COLUMN IF NOT EXISTS storage_keys JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS requested_images INT NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS actual_images INT NOT NULL DEFAULT 0;

DO $$
BEGIN
    IF to_regclass('public.async_image_tasks') IS NOT NULL THEN
        UPDATE async_image_tasks
        SET actual_images = jsonb_array_length(result->'data')
        WHERE status = 'completed'
          AND actual_images = 0
          AND jsonb_typeof(result->'data') = 'array';
    END IF;
END
$$;
