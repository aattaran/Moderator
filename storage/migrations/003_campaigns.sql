-- Freebie campaign system

CREATE TABLE IF NOT EXISTS campaigns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id TEXT NOT NULL UNIQUE,
    tweet_text TEXT NOT NULL,
    keyword TEXT NOT NULL,
    download_url TEXT NOT NULL,
    tweet_url TEXT,
    freebie_name TEXT NOT NULL DEFAULT '',
    dm_template TEXT NOT NULL DEFAULT '',
    status TEXT DEFAULT 'draft',
    replies_count INTEGER DEFAULT 0,
    follows_count INTEGER DEFAULT 0,
    dms_sent INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS campaign_fulfillments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id TEXT NOT NULL,
    username TEXT NOT NULL,
    replied_at TIMESTAMP,
    is_following BOOLEAN DEFAULT 0,
    dm_sent BOOLEAN DEFAULT 0,
    dm_sent_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(campaign_id, username)
);

-- Columns added for robustness (safe to re-run — ALTER TABLE will fail silently if exists)
ALTER TABLE campaign_fulfillments ADD COLUMN dm_failed_at TIMESTAMP;
ALTER TABLE campaign_fulfillments ADD COLUMN skip_reason TEXT;

CREATE INDEX IF NOT EXISTS idx_campaigns_status ON campaigns(status);
CREATE INDEX IF NOT EXISTS idx_fulfillments_campaign ON campaign_fulfillments(campaign_id, dm_sent);
