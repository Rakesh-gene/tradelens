ALTER TABLE admin_pipeline_runs
    ADD COLUMN IF NOT EXISTS run_scope TEXT NOT NULL DEFAULT 'SELECTION';

ALTER TABLE admin_pipeline_runs
    ADD COLUMN IF NOT EXISTS batch_size INTEGER NOT NULL DEFAULT 25;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'admin_pipeline_runs_scope_check'
    ) THEN
        ALTER TABLE admin_pipeline_runs
            ADD CONSTRAINT admin_pipeline_runs_scope_check
            CHECK (run_scope IN ('SELECTION', 'ALL'));
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'admin_pipeline_runs_batch_size_check'
    ) THEN
        ALTER TABLE admin_pipeline_runs
            ADD CONSTRAINT admin_pipeline_runs_batch_size_check
            CHECK (batch_size BETWEEN 1 AND 100);
    END IF;
END $$;
