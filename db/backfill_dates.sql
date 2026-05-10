-- UNSEALED — one-off backfill (2026-05-10).
-- Two operations, both safe to re-run:
--   1. unsealed_date for rows with derivable dates (10 release-list artifacts → 3,496 rows)
--   2. is_sealed=1 for IOD-candidate entries that aren't actually unsealed (2 artifacts → 7,024 rows)
--
-- Requires migration 003_is_sealed_flag.sql to be applied first.
-- All UPDATEs are scoped by source_artifact_url and gated on current state,
-- so reapplying is a no-op.

-- ─── unsealed_date backfill ───────────────────────────────────────────────

UPDATE records SET unsealed_date = '2019-09-30'
 WHERE unsealed_date IS NULL
   AND source_artifact_url = 'https://declassification.blogs.archives.gov/wp-content/uploads/sites/16/2019/10/FY2019-Q4-Release-List-Excel-Format.xlsx';

UPDATE records SET unsealed_date = '2023-09-30'
 WHERE unsealed_date IS NULL
   AND source_artifact_url = 'https://declassification.blogs.archives.gov/wp-content/uploads/sites/16/2023/10/2023-3rd-quarter-release-list.xlsx';

UPDATE records SET unsealed_date = '2024-09-30'
 WHERE unsealed_date IS NULL
   AND source_artifact_url = 'https://www.archives.gov/files/ndc-fy2024-q4-release-list-excel-format.xlsx';

UPDATE records SET unsealed_date = '2019-12-31'
 WHERE unsealed_date IS NULL
   AND source_artifact_url = 'https://declassification.blogs.archives.gov/wp-content/uploads/sites/16/2020/01/FY2020-Q1-Release-List-Excel-Format.xlsx';

UPDATE records SET unsealed_date = '2019-06-30'
 WHERE unsealed_date IS NULL
   AND source_artifact_url = 'https://declassification.blogs.archives.gov/wp-content/uploads/sites/16/2019/08/FY2019-Q3-Release-List-Excel-Format.xlsx';

UPDATE records SET unsealed_date = '2019-03-31'
 WHERE unsealed_date IS NULL
   AND source_artifact_url = 'https://declassification.blogs.archives.gov/wp-content/uploads/sites/16/2019/07/FY2019-Q2-Release-List-Excel-Format.xlsx';

UPDATE records SET unsealed_date = '2023-12-31'
 WHERE unsealed_date IS NULL
   AND source_artifact_url = 'https://declassification.blogs.archives.gov/wp-content/uploads/sites/16/2023/10/2023-4th-Quarter-Release-List-October-6th.xlsx';

UPDATE records SET unsealed_date = '2012-05-31'
 WHERE unsealed_date IS NULL
   AND source_artifact_url IN (
     'https://www.archives.gov/declassification/ndc/reports/released-entries-05-12.xls',
     'http://www.archives.gov/declassification/ndc/reports/released-entries-05-12.xls'
   );

UPDATE records SET unsealed_date = '2012-07-31'
 WHERE unsealed_date IS NULL
   AND source_artifact_url IN (
     'https://www.archives.gov/declassification/ndc/reports/released-entries-07-12.xls',
     'http://www.archives.gov/declassification/ndc/reports/released-entries-07-12.xls'
   );

UPDATE records SET unsealed_date = '2013-04-30'
 WHERE unsealed_date IS NULL
   AND source_artifact_url = 'https://www.archives.gov/declassification/ndc/reports/released-entries-04-13.xls';

UPDATE records SET unsealed_date = '2022-12-31'
 WHERE unsealed_date IS NULL
   AND source_artifact_url = 'https://www.archives.gov/files/declassification/ndc/release-list-q4-2022-excel.xlsx';

UPDATE records SET unsealed_date = '2023-06-30'
 WHERE unsealed_date IS NULL
   AND source_artifact_url = 'https://www.archives.gov/files/declassification/ndc/reports/release-list-projects-for-2nd-qt-2023.xlsx';

UPDATE records SET unsealed_date = '2023-03-31'
 WHERE unsealed_date IS NULL
   AND source_artifact_url = 'https://www.archives.gov/files/declassification/release-list-q1-february-23.xlsx';

-- ─── is_sealed tagging (IOD-candidate lists) ──────────────────────────────

UPDATE records SET is_sealed = 1
 WHERE is_sealed = 0
   AND source_artifact_url IN (
     'https://www.archives.gov/files/declassification/ndc/military-entries-that-are-potential-iod-candidates-as-of-5-16-2024.xlsx',
     'https://www.archives.gov/files/declassification/ndc/civilian-entries-that-are-potential-iod-candidates-as-of-5-16-2024.xlsx'
   );
