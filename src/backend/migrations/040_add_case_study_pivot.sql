ALTER TABLE case_studies ADD COLUMN IF NOT EXISTS pivot_price NUMERIC;

UPDATE case_studies AS case_study
SET pivot_price = NULLIF(entry.candidate_fingerprint->'candidate'->>'pivot_price', '')::NUMERIC
FROM backtest_entries AS entry
WHERE entry.id = case_study.source_backtest_entry_id
  AND case_study.pivot_price IS NULL
  AND entry.candidate_fingerprint->'candidate'->>'pivot_price' IS NOT NULL;
