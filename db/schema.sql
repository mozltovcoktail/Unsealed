-- UNSEALED — SQLite/FTS5 schema (Cloudflare D1 compatible)
-- External-content FTS5 pattern: index stores tokens only, content table is canonical.

PRAGMA foreign_keys = ON;

-- ─── Canonical content table ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS records (
  id            INTEGER PRIMARY KEY,
  title         TEXT NOT NULL,
  agency        TEXT NOT NULL,             -- 'NARA' | 'CIA' | 'NASA' | 'DoW' | 'AARO' | ...
  unsealed_date TEXT NOT NULL,             -- ISO 8601 'YYYY-MM-DD' (D1 has no DATE type)
  collection_id TEXT,                      -- e.g. 'RG 263', 'JFK Assassination Records'
  source_url    TEXT NOT NULL,
  description   TEXT,                      -- often present in NDC release lists
  thumbnail_url TEXT,                      -- hot-link target; proxied via /api/thumb
  ingested_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_records_agency        ON records(agency);
CREATE INDEX IF NOT EXISTS idx_records_unsealed_date ON records(unsealed_date);

-- ─── FTS5 virtual table (external content) ────────────────────────────────
-- Trigram tokenizer → substring + typo-tolerant matching.
-- content='records' content_rowid='id' → no duplicated text storage.
CREATE VIRTUAL TABLE IF NOT EXISTS records_fts USING fts5(
  title,
  description,
  collection_id,
  content='records',
  content_rowid='id',
  tokenize='trigram'
);

-- ─── Sync triggers ────────────────────────────────────────────────────────
CREATE TRIGGER IF NOT EXISTS records_ai AFTER INSERT ON records BEGIN
  INSERT INTO records_fts(rowid, title, description, collection_id)
  VALUES (new.id, new.title, new.description, new.collection_id);
END;

CREATE TRIGGER IF NOT EXISTS records_ad AFTER DELETE ON records BEGIN
  INSERT INTO records_fts(records_fts, rowid, title, description, collection_id)
  VALUES('delete', old.id, old.title, old.description, old.collection_id);
END;

CREATE TRIGGER IF NOT EXISTS records_au AFTER UPDATE ON records BEGIN
  INSERT INTO records_fts(records_fts, rowid, title, description, collection_id)
  VALUES('delete', old.id, old.title, old.description, old.collection_id);
  INSERT INTO records_fts(rowid, title, description, collection_id)
  VALUES (new.id, new.title, new.description, new.collection_id);
END;

-- ─── Ranked search query (reference) ──────────────────────────────────────
-- Column weights: title 3.0, description 1.0, collection_id 0.5.
-- bm25() returns negative; ORDER BY rank ASC sorts best-first.
--
--   SELECT r.id, r.title, r.agency, r.unsealed_date, r.source_url, r.thumbnail_url,
--          bm25(records_fts, 3.0, 1.0, 0.5) AS rank
--   FROM records_fts
--   JOIN records r ON r.id = records_fts.rowid
--   WHERE records_fts MATCH ?1
--     AND (?2 IS NULL OR r.agency = ?2)
--   ORDER BY rank
--   LIMIT 25;
