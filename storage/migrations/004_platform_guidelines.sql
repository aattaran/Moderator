-- Add platform column to style_guidelines for per-platform learning
ALTER TABLE style_guidelines ADD COLUMN platform TEXT NOT NULL DEFAULT 'x';
CREATE INDEX IF NOT EXISTS idx_guidelines_platform_active ON style_guidelines(platform, active);
