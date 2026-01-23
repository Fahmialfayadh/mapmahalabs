-- D1 Schema for MahaMap-Lite
-- Run this in Cloudflare D1 console or via wrangler

CREATE TABLE IF NOT EXISTS map_layers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    folder_path TEXT NOT NULL,
    description TEXT,
    source_link TEXT,
    layer_type TEXT DEFAULT 'tiles',  -- 'tiles' | 'geojson'
    is_insight BOOLEAN DEFAULT 0,
    article_url TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Example: Create index for faster queries
CREATE INDEX IF NOT EXISTS idx_layers_created ON map_layers(created_at DESC);
