-- Default local administrator. Change this password immediately after first use.
-- Email: admin@tradelens.local
-- Password: ChangeMe123!
INSERT INTO users (id, email, password_hash, is_admin)
VALUES (
    '00000000-0000-0000-0000-000000000001',
    'admin@tradelens.local',
    '9a4aabf0e5cf71cae2cea646613ce7e2a5919fa758e56819704be25a3a2c1f0b',
    TRUE
)
ON CONFLICT (email) DO NOTHING;
