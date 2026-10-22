-- Add topic column to posts table
ALTER TABLE posts ADD COLUMN topic TEXT DEFAULT NULL;

-- Style guidelines table — stores evolving content guidelines
CREATE TABLE IF NOT EXISTS style_guidelines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version INTEGER NOT NULL,
    guidelines_text TEXT NOT NULL,
    analysis_summary TEXT NOT NULL,
    top_patterns TEXT NOT NULL DEFAULT '[]',
    anti_patterns TEXT NOT NULL DEFAULT '[]',
    posts_analyzed INTEGER NOT NULL DEFAULT 0,
    avg_engagement_score REAL DEFAULT 0.0,
    active BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_style_guidelines_active ON style_guidelines(active);
