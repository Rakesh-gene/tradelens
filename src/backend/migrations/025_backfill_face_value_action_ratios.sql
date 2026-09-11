-- NSE often expresses splits/consolidations as a face-value change instead of
-- a colon ratio (for example, "From Rs 10/- ... To Rs 2/-"). Backfill the
-- normalized multiplier inputs for actions imported before that format was
-- understood by the application parser.
WITH parsed AS (
    SELECT
        source_event_key,
        substring(
            raw_description FROM
            '(?i)\mfrom\s+(?:(?:rs\.?|inr)\s*)?([0-9]+(?:\.[0-9]+)?)'
        )::NUMERIC AS old_face_value,
        substring(
            raw_description FROM
            '(?i)\mto\s+(?:(?:rs\.?|inr)\s*)?([0-9]+(?:\.[0-9]+)?)'
        )::NUMERIC AS new_face_value
    FROM nse_corporate_actions
    WHERE action_type IN ('SPLIT', 'CONSOLIDATION')
      AND (numerator IS NULL OR denominator IS NULL)
      AND raw_description IS NOT NULL
)
UPDATE nse_corporate_actions AS action
SET numerator = parsed.new_face_value,
    denominator = parsed.old_face_value,
    updated_at = NOW()
FROM parsed
WHERE action.source_event_key = parsed.source_event_key
  AND parsed.old_face_value > 0
  AND parsed.new_face_value > 0;
