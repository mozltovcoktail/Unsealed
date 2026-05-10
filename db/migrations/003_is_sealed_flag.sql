-- Migration 003 — add is_sealed flag to records.
--
-- Some artifact spreadsheets (notably the NDC IOD-candidate lists) describe
-- entries *proposed* for declassification, not actually released. We still
-- ingest them so the index is comprehensive, but the UI should filter them
-- out of the default view. is_sealed=1 means "this record is NOT actually
-- unsealed yet — show only when the user opts in".
--
-- SQLite supports ALTER TABLE ADD COLUMN for columns with a literal DEFAULT;
-- no table rebuild needed. Safe to re-apply: the second ADD COLUMN would
-- fail loudly rather than corrupting data.

ALTER TABLE records ADD COLUMN is_sealed INTEGER NOT NULL DEFAULT 0;
CREATE INDEX IF NOT EXISTS idx_records_is_sealed ON records(is_sealed);
