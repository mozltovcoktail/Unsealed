# UNSEALED — Agent Onboarding

Brutalist mobile-first search across recently declassified U.S. government records. Vite + vanilla JS frontend, Cloudflare Pages Functions for API, Cloudflare D1 (SQLite + FTS5) for storage.

## ⚠️ Hard rule: ethical, legal, no agency trouble

**Every technique, parser, ingest path, and deployment decision on UNSEALED MUST be:**

1. **Legal.** No CFAA / DMCA / state computer-fraud exposure. No copyright infringement (federal works are public domain — that's our basis; third-party compilations are NOT). No violation of any agency's enforceable Terms of Service.
2. **Respectful of `robots.txt` — always.** Before any new source goes live, its `robots.txt` is checked. `Disallow:` paths are not fetched, ever. `Crawl-delay:` is honored as a hard minimum between requests to that host (we enforce it in `fetch()` via the per-host `_LAST_FETCH_AT` tracker, not as a suggestion). If a `robots.txt` rule changes between runs and starts disallowing a path we previously crawled, the next run skips it — no grandfathering. Sitemap entries are treated as advisory hints, not as an override of explicit `Disallow:`.
3. **Respectful of bot protections — no circumvention.** When a publishing agency signals "humans only" through *active* anti-bot challenges (Akamai Bot Manager, Cloudflare Turnstile, reCAPTCHA, JS interstitials, behavioral analysis, rate-limit responses, CAPTCHAs of any kind), **we do not circumvent that signal** — not with Playwright, not with headless Chrome, not with CAPTCHA-solving services, not with residential proxies, not by rotating User-Agents to evade fingerprinting, not by mimicking human input patterns. The technical capability isn't the question; the operator's clearly-communicated intent is. A site that deploys active anti-bot measures has said "no automated access" as clearly as if they'd written it into `robots.txt`, and we respect that.

   The narrow exception is fixing **passive** false-positives — e.g. a WAF that JA3-fingerprints non-browser TLS handshakes and 403s legitimate clients regardless of intent. `curl_cffi` swapping in a real-Chrome handshake is permitted there because the site is rejecting normal browser-shaped requests by accident, and we're returning to "looks like a normal browser." If a site responds to that with an additional active challenge layer, we stop — we don't escalate.
4. **Non-antagonistic to U.S. government agencies, federal or state.** Nothing UNSEALED does should give a federal or state agency a reason to send a cease-and-desist, file a CFAA complaint, refer the project to law enforcement, or even publicly complain. The whole pitch is "this material is supposed to be public; we make it easier to find" — that only works if every source we touch agrees we're being a polite citizen, not an adversarial actor.

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
