ALTER TABLE nse_corporate_actions
    ADD COLUMN IF NOT EXISTS face_value NUMERIC CHECK (face_value > 0),
    ADD COLUMN IF NOT EXISTS issue_price NUMERIC CHECK (issue_price >= 0),
    ADD COLUMN IF NOT EXISTS old_face_value NUMERIC CHECK (old_face_value > 0),
    ADD COLUMN IF NOT EXISTS new_face_value NUMERIC CHECK (new_face_value > 0),
    ADD COLUMN IF NOT EXISTS manual_price_factor NUMERIC CHECK (manual_price_factor > 0),
    ADD COLUMN IF NOT EXISTS manual_volume_factor NUMERIC CHECK (manual_volume_factor > 0),
    ADD COLUMN IF NOT EXISTS resolution_note TEXT,
    ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMPTZ;

UPDATE nse_corporate_actions
SET face_value = NULLIF(raw_payload->>'faceVal', '-')::NUMERIC
WHERE face_value IS NULL
  AND COALESCE(raw_payload->>'faceVal', '-') ~ '^[0-9]+(?:\.[0-9]+)?$';

UPDATE nse_corporate_actions
SET action_type = CASE
        WHEN upper(raw_description) ~ '(NCRPS|CCPS|DEBENTURE|WARRANT)' AND upper(raw_description) LIKE '%BONUS%'
            THEN 'NON_EQUITY_DISTRIBUTION'
        WHEN upper(raw_description) LIKE '%BONUS%'
             AND upper(raw_description) ~ '(SPLIT|SPLT|SUB[- ]DIVISION)'
            THEN 'BONUS_SPLIT'
        WHEN upper(raw_description) ~ '(SPLIT|SPLT|SUB[- ]DIVISION)'
            THEN 'SPLIT'
        WHEN upper(raw_description) ~ '(DEMERG|DE-MERG)'
            THEN 'DEMERGER'
        WHEN upper(raw_description) LIKE '%AMALGAMAT%'
            THEN 'AMALGAMATION'
        WHEN upper(raw_description) LIKE '%CAPITAL REDUCTION%'
            THEN 'CAPITAL_REDUCTION'
        WHEN upper(raw_description) ~ '(HIVE-OFF|HIVE OFF)'
            THEN 'HIVE_OFF'
        WHEN upper(raw_description) ~ 'SCHEME OF (AR+ANGEMENT|ARRANGEMENT)'
            THEN 'SCHEME_OF_ARRANGEMENT'
        ELSE action_type
    END
WHERE raw_description IS NOT NULL;

WITH parsed AS (
    SELECT
        source_event_key,
        substring(
            raw_description FROM
            '(?i)\m(?:from|frm)\s+(?:(?:rs\.?|re\.?|inr)\s*)?([0-9]+(?:\.[0-9]+)?)'
        )::NUMERIC AS old_value,
        substring(
            raw_description FROM
            '(?i)\mto\s+(?:(?:rs\.?|re\.?|inr)\s*)?([0-9]+(?:\.[0-9]+)?)'
        )::NUMERIC AS new_value
    FROM nse_corporate_actions
    WHERE action_type IN ('SPLIT', 'CONSOLIDATION', 'BONUS_SPLIT')
      AND raw_description IS NOT NULL
)
UPDATE nse_corporate_actions AS action
SET old_face_value = parsed.old_value,
    new_face_value = parsed.new_value,
    numerator = CASE
        WHEN action.action_type IN ('SPLIT', 'CONSOLIDATION') THEN parsed.new_value
        ELSE action.numerator
    END,
    denominator = CASE
        WHEN action.action_type IN ('SPLIT', 'CONSOLIDATION') THEN parsed.old_value
        ELSE action.denominator
    END,
    updated_at = NOW()
FROM parsed
WHERE action.source_event_key = parsed.source_event_key
  AND parsed.old_value > 0
  AND parsed.new_value > 0;

WITH priced AS (
    SELECT
        source_event_key,
        substring(
            raw_description FROM
            '(?i)(?:premium|prem|issue\s+price)\s*(?:rs\.?|re\.?|inr)?\s*([0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?)'
        )::NUMERIC AS premium
    FROM nse_corporate_actions
    WHERE action_type = 'RIGHTS' AND raw_description IS NOT NULL
)
UPDATE nse_corporate_actions AS action
SET issue_price = priced.premium + COALESCE(action.face_value, 0),
    updated_at = NOW()
FROM priced
WHERE action.source_event_key = priced.source_event_key
  AND priced.premium IS NOT NULL;

UPDATE nse_corporate_actions
SET cash_value = substring(
        raw_description FROM
        '(?i)(?:rs\.?|re\.?|inr)\s*([0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?)'
    )::NUMERIC,
    updated_at = NOW()
WHERE action_type = 'DIVIDEND'
  AND cash_value IS NULL
  AND raw_description ~* '(?:rs\.?|re\.?|inr)\s*[0-9]';

CREATE INDEX IF NOT EXISTS nse_corporate_actions_unresolved_idx
    ON nse_corporate_actions (action_type, ex_date)
    WHERE manual_price_factor IS NULL;
