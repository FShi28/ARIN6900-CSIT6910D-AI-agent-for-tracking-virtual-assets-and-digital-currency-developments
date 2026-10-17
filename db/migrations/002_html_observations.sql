-- Apply to schema v1 only, through migrate-db. Existing rows remain untouched.
PRAGMA foreign_keys = ON;
BEGIN IMMEDIATE;
CREATE TABLE html_observations (
    observation_id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE CHECK (length(trim(run_id)) > 0),
    extraction_id TEXT NOT NULL REFERENCES extractions(extraction_id) ON DELETE RESTRICT,
    collected_at TEXT NOT NULL CHECK (length(collected_at) = 20
        AND strftime('%Y-%m-%dT%H:%M:%SZ', collected_at, '+0 seconds') IS collected_at),
    downloaded_url TEXT NOT NULL CHECK (downloaded_url GLOB 'https://?*'),
    parent_url TEXT NOT NULL CHECK (parent_url GLOB 'https://?*'),
    raw_path TEXT NOT NULL CHECK (raw_path GLOB 'data/raw/*.html'),
    content_sha256 TEXT NOT NULL CHECK (length(content_sha256) = 64 AND content_sha256 NOT GLOB '*[^0-9a-f]*'),
    response_fingerprint TEXT NOT NULL CHECK (length(response_fingerprint) = 64 AND response_fingerprint NOT GLOB '*[^0-9a-f]*'),
    article_fingerprint TEXT NOT NULL CHECK (length(article_fingerprint) = 64 AND article_fingerprint NOT GLOB '*[^0-9a-f]*'),
    rule_id TEXT NOT NULL CHECK (rule_id = 'hkma-html-csrf-v1'),
    change_type TEXT NOT NULL CHECK (change_type IN ('new', 'unchanged', 'content_changed', 'page_changed'))
) STRICT;
CREATE INDEX idx_html_observations_extraction ON html_observations(extraction_id, observation_id);
CREATE TRIGGER html_observations_no_update BEFORE UPDATE ON html_observations
BEGIN SELECT RAISE(ABORT, 'HTML observations are immutable'); END;
PRAGMA user_version = 2;
COMMIT;
