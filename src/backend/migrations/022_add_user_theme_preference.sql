ALTER TABLE users
    ADD COLUMN IF NOT EXISTS theme_preference TEXT NOT NULL DEFAULT 'ember';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'users_theme_preference_check'
    ) THEN
        ALTER TABLE users ADD CONSTRAINT users_theme_preference_check
            CHECK (theme_preference IN ('ember', 'forest', 'ocean', 'plum', 'slate'));
    END IF;
END $$;
