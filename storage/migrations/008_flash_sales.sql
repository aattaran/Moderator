-- TikTok Shop flash sale (Flash Deal activity) state
--
-- Source of truth for "is a sale live right now". Captions read this, never a
-- hardcoded string, so a post can't advertise a discount the shop isn't charging.
--
-- Two separate proofs are required before a sale counts as live:
--   tiktok_activity_id  — the Flash Deal actually exists remotely (not just planned)
--   remote_verified_at  — we confirmed it was still running, recently
-- A row can be locally 'live' and remotely dead (ended by hand in Seller Center),
-- so freshness is part of the check, not just status.

CREATE TABLE IF NOT EXISTS flash_sales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    product_key TEXT NOT NULL,

    -- Discount. discount_type: percentage | fixed_amount
    -- percentage   -> discount_value is 1-99 (percent OFF)
    -- fixed_amount -> discount_value is the amount off, in `currency`
    discount_type TEXT NOT NULL,
    discount_value REAL NOT NULL,
    currency TEXT NOT NULL DEFAULT 'USD',

    -- Window. UTC ISO8601. Enforced on read, not just at creation.
    starts_at TIMESTAMP NOT NULL,
    ends_at TIMESTAMP NOT NULL,

    -- Remote linkage. NULL until the Flash Deal is created on TikTok Shop.
    tiktok_activity_id TEXT,
    shop_cipher TEXT,

    -- Lifecycle: draft | scheduled | live | ended | failed | aborted
    status TEXT NOT NULL DEFAULT 'draft',
    -- Last time the remote activity was confirmed still running.
    remote_verified_at TIMESTAMP,
    remote_synced_at TIMESTAMP,
    last_error TEXT,

    -- Set when a caption cited this sale, for post-hoc parity auditing.
    last_advertised_at TIMESTAMP,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_flash_sales_status ON flash_sales(status);
CREATE INDEX IF NOT EXISTS idx_flash_sales_window ON flash_sales(starts_at, ends_at);
CREATE INDEX IF NOT EXISTS idx_flash_sales_product ON flash_sales(product_key);
