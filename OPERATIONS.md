# UNSEALED — operations

How the corpus stays current. Three workflows in `.github/workflows/`:

| Workflow | Cron | What it does |
| --- | --- | --- |
| `discover.yml` | Mon 08:33 UTC | Probes RSS + re-scans known hub pages for new `.gov`/`.mil` links. Auto-promotes trusted URLs into `ingest/sources.json`. Opens a PR labeled `auto-merge-after-24h`. |
| `auto-merge.yml` | Daily 12:11 UTC | Squash-merges any open PR labeled `auto-merge-after-24h` that's >24h old and not blocked. |
| `ingest.yml` | Mon 09:17 UTC | Runs `ingest_secrets.py`, applies generated SQL to remote D1, commits the run report. |

Discovery runs ~45 min before ingest so any same-day promotion lands first.

## Trust model

Auto-discovery is **bounded by domain allow-list**. Only URLs whose host ends in `.gov` / `.mil`, or matches `TRUSTED_HOSTS` in `ingest/discover.py` and `ingest/promote.py`, are auto-promoted. Anything else stays in `ingest/discovered.json` with `status: rejected` for human review.

Every auto-promotion is logged to `ingest/promotion_log.jsonl` (append-only) and visible in the discovery PR.

## Audit and override

- **See what was added recently:** `git log --grep "discovery:" --oneline`
- **Block a pending PR from auto-merging:** add the `block-auto-merge` label.
- **Revert a bad source:** `git revert <commit>` on `main`.
- **Reject a discovered URL permanently:** add it to `ingest/discovered_seen.json` (it won't be re-surfaced).
- **Disable everything:** edit any workflow's `on:` block (e.g. comment out `schedule:`).

## Required repo secrets

| Secret | Purpose |
| --- | --- |
| `CLOUDFLARE_API_TOKEN` | D1:Edit scope, scoped to the `unsealed` database |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare account ID |
| `NARA_API_KEY` | *(optional)* enables `nara_catalog` parser. Email `Catalog_API@nara.gov` to request a free read-only key. Without it, that parser silently skips. |

`GITHUB_TOKEN` is provided automatically by Actions and is used for opening + merging the discovery PRs.

## Idempotency

The ingester emits `INSERT OR IGNORE` with a `content_hash` UNIQUE constraint on the `records` table, so re-applying any `db/ingest_<group>.sql` is a no-op. The migration in `db/migrations/001_idempotency_provenance.sql` adds the new columns and indexes; the `ingest.yml` workflow applies all migrations before each run (errors on already-applied migrations are ignored).

## Manual ingest

```bash
python3 ingest/ingest_secrets.py                  # all groups
python3 ingest/ingest_secrets.py --group nara_ndc
python3 ingest/ingest_secrets.py --no-cache       # bypass cache
python3 ingest/ingest_secrets.py --dry-run        # parse, print, don't write SQL

# Apply locally (dev D1):
for f in db/ingest_*.sql; do npm run d1:apply:local -- --file="$f"; done

# Apply to remote (prod D1):
for f in db/ingest_*.sql; do wrangler d1 execute unsealed --remote --file="$f"; done
```

## Manual discovery

```bash
python3 ingest/discover.py --dry-run    # preview candidates
python3 ingest/discover.py              # writes ingest/discovered.json
python3 ingest/promote.py               # promotes trusted URLs into sources.json
```

## Adding a new RSS feed

Edit `FEEDS` at the top of `ingest/discover.py`. Must be a `.gov` / `.mil` host (the trust check still applies after parsing).

## Adding a new trusted non-`.gov` host

Edit `TRUSTED_HOSTS` in **both** `ingest/discover.py` and `ingest/promote.py`. Keep this list narrow — the `.gov`/`.mil` boundary is what makes auto-promotion safe.
