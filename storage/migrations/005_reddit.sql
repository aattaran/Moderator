-- Reddit karma tracking and promotional ratio

CREATE TABLE IF NOT EXISTS reddit_karma_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    comment_karma INTEGER DEFAULT 0,
    link_karma INTEGER DEFAULT 0,
    total_karma INTEGER DEFAULT 0,
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_reddit_karma_username ON reddit_karma_log(username);

-- Add subreddit and promotional tracking to posts/comments
ALTER TABLE posts ADD COLUMN subreddit TEXT;
ALTER TABLE posts ADD COLUMN is_promotional BOOLEAN DEFAULT 0;
ALTER TABLE comments ADD COLUMN subreddit TEXT;
ALTER TABLE comments ADD COLUMN is_promotional BOOLEAN DEFAULT 0;
