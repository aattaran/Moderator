-- Moderator initial schema

CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    content TEXT NOT NULL,
    content_style TEXT NOT NULL,
    media_urls TEXT DEFAULT '[]',
    posted_at TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'draft',
    engagement_likes INTEGER DEFAULT 0,
    engagement_reposts INTEGER DEFAULT 0,
    engagement_replies INTEGER DEFAULT 0,
    engagement_views INTEGER DEFAULT 0,
    scraped_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    target_post_url TEXT NOT NULL,
    target_author TEXT NOT NULL,
    content TEXT NOT NULL,
    comment_style TEXT NOT NULL,
    topic TEXT NOT NULL,
    posted_at TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'draft',
    engagement_likes INTEGER DEFAULT 0,
    engagement_replies INTEGER DEFAULT 0,
    scraped_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS target_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    username TEXT NOT NULL,
    follower_count INTEGER DEFAULT 0,
    avg_engagement_rate REAL DEFAULT 0.0,
    relevance_score REAL DEFAULT 0.5,
    last_checked TIMESTAMP,
    active BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(platform, username)
);

CREATE TABLE IF NOT EXISTS weight_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    name TEXT NOT NULL,
    weight REAL NOT NULL DEFAULT 1.0,
    period_start TIMESTAMP NOT NULL,
    period_end TIMESTAMP,
    sample_count INTEGER DEFAULT 0,
    avg_engagement REAL DEFAULT 0.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(category, name, period_start)
);

CREATE TABLE IF NOT EXISTS agent_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent TEXT NOT NULL,
    task_type TEXT NOT NULL,
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'running',
    iterations INTEGER DEFAULT 0,
    error_message TEXT,
    api_tokens_used INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_posts_platform_status ON posts(platform, status);
CREATE INDEX IF NOT EXISTS idx_posts_posted_at ON posts(posted_at);
CREATE INDEX IF NOT EXISTS idx_posts_content_style ON posts(content_style);
CREATE INDEX IF NOT EXISTS idx_comments_posted_at ON comments(posted_at);
CREATE INDEX IF NOT EXISTS idx_comments_topic ON comments(topic);
CREATE INDEX IF NOT EXISTS idx_target_accounts_platform ON target_accounts(platform, active);
CREATE INDEX IF NOT EXISTS idx_weight_entries_category ON weight_entries(category, name);
CREATE INDEX IF NOT EXISTS idx_agent_runs_status ON agent_runs(status);
CREATE INDEX IF NOT EXISTS idx_agent_runs_agent ON agent_runs(agent, task_type);
