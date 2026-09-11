-- Correct imported rights terms. An explicitly stated issue price is already
-- the subscription price; only a stated premium must have face value added.
UPDATE nse_corporate_actions
SET issue_price = replace(substring(
        raw_description FROM
        '(?i)(?:issue\s+price\s*(?:of\s*)?|@\s*)(?:rs\.?|re\.?|inr)\s*([0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?)'
    ), ',', '')::NUMERIC,
    updated_at = NOW()
WHERE action_type = 'RIGHTS'
  AND raw_description ~* '(?:issue\s+price\s*(?:of\s*)?|@\s*)(?:rs\.?|re\.?|inr)\s*[0-9]';

UPDATE nse_corporate_actions
SET issue_price = replace(substring(
        raw_description FROM
        '(?i)(?:premium|prem)\s*(?:of\s*)?(?:rs\.?|re\.?|inr)?\s*([0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?)'
    ), ',', '')::NUMERIC + COALESCE(face_value, 0),
    updated_at = NOW()
WHERE action_type = 'RIGHTS'
  AND raw_description ~* '(?:premium|prem)\s*(?:of\s*)?(?:rs\.?|re\.?|inr)?\s*[0-9]';
