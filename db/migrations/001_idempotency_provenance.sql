-- Migration 001 — idempotency + provenance
-- Apply once on existing deployments:
--   wrangler d1 execute unsealed --remote --file=db/migrations/001_idempotency_provenance.sql

ALTER TABLE records ADD COLUMN source_artifact_url TEXT;
ALTER TABLE records ADD COLUMN ingest_run_id       TEXT;
ALTER TABLE records ADD COLUMN content_hash        TEXT;

-- Backfill content_hash for existing rows so the unique constraint can be added.
-- sha1(agency || '|' || title || '|' || source_url) — done in app code; here we
-- just leave the column nullable for now and rely on app-level dedup.
-- (SQLite can't add UNIQUE to an existing column without a table rebuild.)

CREATE INDEX IF NOT EXISTS idx_records_artifact ON records(source_artifact_url);
CREATE INDEX IF NOT EXISTS idx_records_run      ON records(ingest_run_id);
CREATE INDEX IF NOT EXISTS idx_records_hash     ON records(content_hash);

CREATE TABLE IF NOT EXISTS discovered_sources (
  id          INTEGER PRIMARY KEY,
  url         TEXT NOT NULL UNIQUE,
  domain      TEXT NOT NULL,
  found_via   TEXT NOT NULL,
  found_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  promoted_at TEXT,
  status      TEXT NOT NULL DEFAULT 'pending'
);
CREATE INDEX IF NOT EXISTS idx_discovered_status ON discovered_sources(status);
