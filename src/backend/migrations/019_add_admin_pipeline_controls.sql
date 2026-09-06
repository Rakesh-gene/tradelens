ALTER TABLE admin_pipeline_runs
    ADD COLUMN IF NOT EXISTS paused_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS terminated_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS last_resumed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS resume_count INTEGER NOT NULL DEFAULT 0;

ALTER TABLE admin_pipeline_run_items
    ADD COLUMN IF NOT EXISTS attempt_count INTEGER NOT NULL DEFAULT 0;

UPDATE admin_pipeline_run_items
SET attempt_count = 1
WHERE attempt_count = 0 AND started_at IS NOT NULL;
