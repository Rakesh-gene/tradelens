CREATE TABLE IF NOT EXISTS case_study_run_items (
    case_study_run_id UUID NOT NULL REFERENCES case_study_runs (id) ON DELETE CASCADE,
    isin TEXT NOT NULL REFERENCES nse_equities (isin),
    status TEXT NOT NULL CHECK (status IN ('PENDING', 'COMPLETED', 'FAILED', 'SKIPPED')),
    cases_recorded INTEGER NOT NULL DEFAULT 0 CHECK (cases_recorded >= 0),
    error_message TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (case_study_run_id, isin)
);
