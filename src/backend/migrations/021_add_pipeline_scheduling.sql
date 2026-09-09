ALTER TABLE admin_pipeline_runs
    ALTER COLUMN requested_by DROP NOT NULL;

ALTER TABLE admin_pipeline_runs
    ADD COLUMN IF NOT EXISTS trigger_source TEXT NOT NULL DEFAULT 'MANUAL',
    ADD COLUMN IF NOT EXISTS scheduled_for DATE;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'admin_pipeline_runs_trigger_source_check'
    ) THEN
        ALTER TABLE admin_pipeline_runs
            ADD CONSTRAINT admin_pipeline_runs_trigger_source_check
            CHECK (trigger_source IN ('MANUAL', 'SCHEDULED'));
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS admin_pipeline_runs_scheduled_for_idx
    ON admin_pipeline_runs (scheduled_for)
    WHERE trigger_source = 'SCHEDULED' AND scheduled_for IS NOT NULL;
