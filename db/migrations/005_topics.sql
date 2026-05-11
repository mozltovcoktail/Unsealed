-- Migration 005 — add topics tag column to records.
--
-- Free-form topic tagging for cross-agency themes (UAP, NUCLEAR, VIETNAM,
-- CIVIL_RIGHTS, etc.) so the UI can filter by topic alongside source filters.
--
-- Format: comma-delimited with leading + trailing commas for unambiguous
-- LIKE matching. Empty / NULL = no topics.
--   ",UAP,"             → tagged UAP only
--   ",UAP,NUCLEAR,"     → tagged UAP and NUCLEAR
--   "" / NULL           → untagged
-- Query pattern: WHERE topics LIKE '%,UAP,%'

ALTER TABLE records ADD COLUMN topics TEXT;
CREATE INDEX IF NOT EXISTS idx_records_topics ON records(topics);
