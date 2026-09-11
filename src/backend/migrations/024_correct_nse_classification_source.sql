ALTER TABLE market_macro_sectors
    ALTER COLUMN taxonomy_source SET DEFAULT 'NSE';

ALTER TABLE market_industries
    ALTER COLUMN taxonomy_source SET DEFAULT 'NSE';

ALTER TABLE market_basic_industries
    ALTER COLUMN taxonomy_source SET DEFAULT 'NSE';

UPDATE market_macro_sectors
SET taxonomy_source = 'NSE', updated_at = NOW()
WHERE code LIKE 'NSE-MACRO-%' AND taxonomy_source = 'NSE_INDICES';

UPDATE market_sectors
SET taxonomy_source = 'NSE', updated_at = NOW()
WHERE code LIKE 'NSE-SECTOR-%' AND taxonomy_source = 'NSE_INDICES';

UPDATE market_industries
SET taxonomy_source = 'NSE', updated_at = NOW()
WHERE code LIKE 'NSE-INDUSTRY-%' AND taxonomy_source = 'NSE_INDICES';

UPDATE market_basic_industries
SET taxonomy_source = 'NSE', updated_at = NOW()
WHERE code LIKE 'NSE-BASIC-%' AND taxonomy_source = 'NSE_INDICES';
