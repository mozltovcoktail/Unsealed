-- Migration 004 — add document_date to records.
--
-- For published-as-a-set sources (FRUS especially): unsealed_date is the
-- volume publication date (when the document became public), document_date
-- is the document's own creation date. The two diverge by years for modern
-- Cold War FRUS volumes (docs from 1969–76 released as a volume in 2006+).
--
-- Nullable: many sources (NDC release lists, AARO PDFs) only have one
-- meaningful date and we leave the other null.
--
-- SQLite ALTER TABLE ADD COLUMN with a literal default is safe — no rebuild.

ALTER TABLE records ADD COLUMN document_date TEXT;
CREATE INDEX IF NOT EXISTS idx_records_document_date ON records(document_date);
