-- Migration 002 — allow NULL unsealed_date.
-- Reality: many NDC release-list rows have no per-row date and no derivable
-- date from the artifact filename. Forcing NOT NULL caused INSERT OR IGNORE
-- to silently drop ~90% of rows on the first auto-discovery ingest.
--
-- SQLite can't drop a NOT NULL constraint via ALTER. Use the documented
-- table-rebuild pattern. Triggers and FTS5 are recreated by schema.sql on
-- next apply; here we only touch the records table itself.

PRAGMA foreign_keys = OFF;

CREATE TABLE records_new (
  id                  INTEGER PRIMARY KEY,
  title               TEXT NOT NULL,
  agency              TEXT NOT NULL,
  unsealed_date       TEXT,                       -- now nullable
  collection_id       TEXT,
  source_url          TEXT NOT NULL,
  description         TEXT,
  thumbnail_url       TEXT,
  ingested_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  source_artifact_url TEXT,
  ingest_run_id       TEXT,
  content_hash        TEXT
);

INSERT INTO records_new SELECT * FROM records;
DROP TABLE records;
ALTER TABLE records_new RENAME TO records;

CREATE INDEX IF NOT EXISTS idx_records_agency        ON records(agency);
CREATE INDEX IF NOT EXISTS idx_records_unsealed_date ON records(unsealed_date);
CREATE INDEX IF NOT EXISTS idx_records_artifact      ON records(source_artifact_url);
CREATE INDEX IF NOT EXISTS idx_records_run           ON records(ingest_run_id);
CREATE INDEX IF NOT EXISTS idx_records_hash          ON records(content_hash);

-- Re-create FTS triggers (DROP TABLE removed them).
DROP TRIGGER IF EXISTS records_ai;
DROP TRIGGER IF EXISTS records_ad;
DROP TRIGGER IF EXISTS records_au;

CREATE TRIGGER records_ai AFTER INSERT ON records BEGIN
  INSERT INTO records_fts(rowid, title, description, collection_id)
  VALUES (new.id, new.title, new.description, new.collection_id);
END;

CREATE TRIGGER records_ad AFTER DELETE ON records BEGIN
  INSERT INTO records_fts(records_fts, rowid, title, description, collection_id)
  VALUES('delete', old.id, old.title, old.description, old.collection_id);
END;

CREATE TRIGGER records_au AFTER UPDATE ON records BEGIN
  INSERT INTO records_fts(records_fts, rowid, title, description, collection_id)
  VALUES('delete', old.id, old.title, old.description, old.collection_id);
  INSERT INTO records_fts(rowid, title, description, collection_id)
  VALUES (new.id, new.title, new.description, new.collection_id);
END;

-- Re-sync FTS index against rebuilt table.
INSERT INTO records_fts(records_fts) VALUES('rebuild');

PRAGMA foreign_keys = ON;
