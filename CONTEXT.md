# UNSEALED — Agent Onboarding

Brutalist mobile-first search across recently declassified U.S. government records. Vite + vanilla JS frontend, Cloudflare Pages Functions for API, Cloudflare D1 (SQLite + FTS5) for storage.

## ⚠️ Hard rule: ethical, legal, no agency trouble

**Every technique, parser, ingest path, and deployment decision on UNSEALED MUST be:**

1. **Legal.** No CFAA / DMCA / state computer-fraud exposure. No copyright infringement (federal works are public domain — that's our basis; third-party compilations are NOT). No violation of any agency's enforceable Terms of Service.
2. **Respectful of `robots.txt` — always.** Before any new source goes live, its `robots.txt` is checked. `Disallow:` paths are not fetched, ever. `Crawl-delay:` is honored as a hard minimum between requests to that host (we enforce it in `fetch()` via the per-host `_LAST_FETCH_AT` tracker, not as a suggestion). If a `robots.txt` rule changes between runs and starts disallowing a path we previously crawled, the next run skips it — no grandfathering. Sitemap entries are treated as advisory hints, not as an override of explicit `Disallow:`.
3. **Respectful of bot protections — no circumvention.** When a publishing agency signals "humans only" through *active* anti-bot challenges (Akamai Bot Manager, Cloudflare Turnstile, reCAPTCHA, JS interstitials, behavioral analysis, rate-limit responses, CAPTCHAs of any kind), **we do not circumvent that signal** — not with Playwright, not with headless Chrome, not with CAPTCHA-solving services, not with residential proxies, not by rotating User-Agents to evade fingerprinting, not by mimicking human input patterns. The technical capability isn't the question; the operator's clearly-communicated intent is. A site that deploys active anti-bot measures has said "no automated access" as clearly as if they'd written it into `robots.txt`, and we respect that.

   The narrow exception is fixing **passive** false-positives — e.g. a WAF that JA3-fingerprints non-browser TLS handshakes and 403s legitimate clients regardless of intent. `curl_cffi` swapping in a real-Chrome handshake is permitted there because the site is rejecting normal browser-shaped requests by accident, and we're returning to "looks like a normal browser." If a site responds to that with an additional active challenge layer, we stop — we don't escalate.
4. **Non-antagonistic to U.S. government agencies, federal or state.** Nothing UNSEALED does should give a federal or state agency a reason to send a cease-and-desist, file a CFAA complaint, refer the project to law enforcement, or even publicly complain. The whole pitch is "this material is supposed to be public; we make it easier to find" — that only works if every source we touch agrees we're being a polite citizen, not an adversarial actor.
5. **We are a discovery layer, not a storage repository.** UNSEALED's job is to make freely-online records *findable* by indexing their metadata and linking out to the publisher's hosted copy. It is NOT a mirror, archive, or hosting service for the records themselves.

   **What we store** (in D1 and only D1):
   - Title, agency, dates (unsealed_date, document_date), collection_id, topics, source_url, source_artifact_url, content_hash, is_sealed flag, short description snippet (≤500 chars — enough for search context and a card preview, not a substitute for the original).

   **What we do NOT store, anywhere we control** (D1, Cloudflare R2/KV, GitHub, local disk past a single run):
   - Full document bodies, PDF/EPUB/DOCX/scanned-image binaries, OCR text dumps, page-rasterized thumbnails of document interiors, or anything that approaches the original document's content.
   - Cached binary artifacts beyond the runtime of a single ingest pass. The local `ingest/cache/` directory may briefly hold a fetched EPUB or HTML page during parsing, but those binaries are deleted after extraction and never committed to git, never uploaded to R2/KV, never sync'd anywhere durable. (Today the cache is gitignored and holds only short JSON/HTML index pages — no binaries persist.)
   - Thumbnails for declassified document interiors. `/api/thumb` is a same-origin proxy that hot-links the publisher's thumbnail with edge caching only — Cloudflare's CDN may hold it briefly, but it's not ours to retain.

   **Why this principle exists:**
   - **Legal cleanliness:** federal works are public domain, so we *could* store them. But storing 313k FRUS docs makes UNSEALED a hosting platform with hosting-platform problems — takedown requests, accuracy obligations, the question of "whose copy is canonical." Linking out keeps us a pointer.
   - **Source-of-truth preservation:** if the publisher updates, redacts further, or pulls a record, the user gets the publisher's current version, not our stale snapshot.
   - **Cost discipline:** keeps Cloudflare free tier viable as we scale to millions of records. D1 holds bytes-of-metadata-per-row; R2 holding millions of PDFs would not be free.
   - **Brand integrity:** the pitch is "we find what's already public." If we host copies, the pitch becomes "we mirror public records," which is a different, smaller project (and a more legally-exposed one).

   **When a source disappears:** the broken `source_url` is the user's signal that the publisher pulled the record. We don't backfill, don't mirror, don't substitute. We may remove the dead row from D1 in a sweep, but we don't try to keep the content alive.

**What this means concretely:**

| ✅ OK | ❌ NOT OK |
|---|---|
| Reading `robots.txt` before each new source goes live; honoring `Disallow:` and `Crawl-delay:` as hard rules | Ignoring `robots.txt` to crawl forbidden paths or go faster than the declared crawl-delay |
| `curl_cffi` to defeat **passive** TLS-fingerprint false-positives where a real browser would just work (aaro.mil case) | Playwright / headless Chrome / CAPTCHA-solvers / residential proxies / behavioral mimicry to defeat **active** anti-bot challenges (CIA CREST, FBI Vault, anything with `bm-verify`, Turnstile, reCAPTCHA, JS interstitials) |
| Identifying ourselves with `From: unsealed-bot@github.com/...` and an honest UA | Spoofing identity, pretending to be a different bot, pretending to be a human user, rotating UAs to evade rate limits |
| Bulk EPUB / API downloads from endpoints the publisher built for bulk programmatic access (FRUS, NARA Catalog API, IA advancedsearch) | Bulk-scraping a paginated search UI never meant to serve bulk traffic |
| Public-domain federal works (17 USC §105) — copy freely | Third-party aggregators' curated compilations (GWU NSArchive, MuckRock, Black Vault) without per-source ToS check |
| FOIA-released documents the agency chose to publish | Material the agency clearly didn't intend to be public (leaked, draft, or still-classified docs) |
| Backing off when a host returns 429 / Retry-After / 503 | Retrying through rate limits, treating 429 as transient noise |
| Storing **metadata** in D1 (title, dates, source_url, short ≤500-char description) | Storing document binaries (PDF/EPUB/DOCX), full OCR text, or page-image thumbnails of document interiors — in D1, R2, KV, git, or local disk past one run |
| Linking out to the publisher's URL so the user gets the canonical copy | Mirroring the document content under our own URL or domain |
| Hot-linking thumbnails via `/api/thumb` (edge cache, no persistent storage) | Persisting fetched binaries to R2 / KV / disk for re-serving |

**When in doubt:** assume the more restrictive interpretation. Use FOIA, NARA Catalog API, IA federation, or skip the source entirely. There is always another path to the underlying public-domain content; never the path that involves circumventing an agency's clearly-deployed "humans only" signal.

**Sources that hit this rule become ⚪ OUT OF SCOPE in [SOURCES.md](SOURCES.md), not 🔵 QUEUED.** As of 2026-05-11 this applies to CIA CREST (`cia.gov/readingroom` — Akamai Bot Manager JS challenge) and FBI Vault (`vault.fbi.gov` — same). Content overlap is reachable via the IA / NSArchive federation we already do plus NARA Catalog API once we have the key.

**No reputational risk takes:** UNSEALED is a public open-source project with Aaron's name on it. "UNSEALED bypasses CIA bot protection" is a worse headline than "UNSEALED indexes the same content via NARA's open API" — even if the technical achievement is the same and the legal exposure is the same (negligible). The framing matters.

---

## Why this stack
- **D1 over self-hosted SQLite**: native FTS5, free tier covers our scale (500MB cap), single binding from Pages Functions, no second deploy target.
- **Vite vanilla JS**: matches the rest of Aaron's portfolio (CardVault / Colorbolt / Neutralize / Zero Views all on this exact stack).
- **External-content FTS5 + trigram tokenizer**: storage-efficient (no duplicated text) and gives substring + typo-tolerant matches without a secondary fuzzy index.

## Layout
```
UNSEALED_Web/
├── db/
│   ├── schema.sql          # FTS5 external-content schema + sync triggers
│   ├── seed.sql            # 12 verified real records for UI testing
│   └── ingest_*.sql        # generated by ingest_secrets.py
├── functions/api/
│   ├── search.js           # GET /api/search — BM25-ranked, typo-tolerant
│   ├── agencies.js         # GET /api/agencies — facet counts
│   ├── thumb.js            # GET /api/thumb — same-origin proxy + edge cache
│   └── preview.js          # GET /api/preview — agentic on-demand retrieval
├── ingest/
│   ├── sources.json        # URL config — drop new sources here
│   └── ingest_secrets.py   # parser → emits db/ingest_<group>.sql
├── src/
│   ├── main.js             # search-as-you-type, IO unveil, agency toggles
│   └── style.css           # vanilla CSS, brutalist tokens
├── index.html
├── vite.config.js          # port 5183
├── wrangler.toml           # D1 binding, Pages Functions
└── package.json
```

## Migration story (away from D1, if ever needed)
- Schema is plain SQLite — works as-is on libSQL/Turso, local SQLite, Postgres with minor tweaks (FTS5 → tsvector, triggers → generated column).
- All DB access goes through `env.DB` in Pages Functions — single seam to swap.
- Ingest pipeline emits `.sql` files, not direct API calls — re-applies anywhere `psql` / `wrangler d1 execute` runs.

## Day-one workflow
```
npm install
wrangler d1 create unsealed                       # → paste database_id into wrangler.toml
npm run d1:apply:local                            # apply schema
npm run d1:seed:local                             # 12 real records
# in two terminals:
npm run dev                                       # vite on :5183
wrangler pages dev ./dist --d1=DB --port 8788     # API
```

## Conventions
- Every result starts redacted. IntersectionObserver unveils on scroll-in. Desktop click on title re-redacts (analog "RE-CLASSIFY" feel).
- Border-radius is 0 everywhere. 1px / 2px solid black borders only.
- Monospace for metadata + query field. Sans-serif heavyweight for titles + masthead.
- All host calls (thumb proxy, preview agent) gate on a `.gov` / `.mil` allow-list. Never proxy arbitrary URLs.

## Staying current

Three GitHub Actions keep the corpus fresh — see [OPERATIONS.md](OPERATIONS.md).
- `discover.yml` (weekly) finds new `.gov`/`.mil` source URLs.
- `ingest.yml` (weekly) re-runs the parsers and upserts into D1.
- `auto-merge.yml` (daily) merges discovery PRs after a 24h review window.

Trust boundary: only `.gov` / `.mil` (+ a tiny curated list) auto-promote.
Every auto-add is a reviewable, revertable commit.

## Open product questions (not yet decided)
- PDF page-1 rasterization — preview.js currently returns metadata only. A pdf.js Worker is the obvious next move but warrants its own decision.
- Verified Department of War UAP source URL — `ingest/sources.json::dow_uap.urls` is empty until provided.
- Offline mode — currently online-first. Browser-side wa-sqlite was rejected for v1 due to cold-start size.
