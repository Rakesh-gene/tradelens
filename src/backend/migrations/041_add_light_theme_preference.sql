ALTER TABLE users
    DROP CONSTRAINT IF EXISTS users_theme_preference_check;

ALTER TABLE users
    ADD CONSTRAINT users_theme_preference_check
    CHECK (theme_preference IN ('light', 'ember', 'forest', 'ocean', 'plum', 'slate'));
