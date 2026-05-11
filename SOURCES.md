# UNSEALED — Source Inventory

Living index of every U.S. Government document source we know about,
whether it's live, queued, blocked, or out of scope, plus the access
method and any legal/ethical notes.

The authoritative wiring lives in `ingest/sources.json` — this doc is the
human-readable backlog and audit trail that surrounds it.

Last manual review: 2026-05-10.

## Brand scope (DECIDED 2026-05-10)

UNSEALED ingests **records that were once classified and are now public** — no time bound, all the way back through the Cold War, WWII, and earlier where such material was eventually declassified. We do NOT ingest material that was unclassified-by-default (Federal Register, Congressional Record, GAO, USGS, NIST, Presidential Public Papers, etc.).

CRS Reports were unclassified-but-suppressed, not classified — moved to §5 (out of scope).

Brand strap (`index.html`) currently reads "RECENTLY DECLASSIFIED" — outdated under this scope, since we now want 1940s/50s/60s material too. Strap rewrite is a follow-up (see open decisions).

## Legend
- ✅ **LIVE** — parser runs in the weekly `ingest.yml`, rows are in D1
- 🟡 **PARTIAL** — code exists but blocked on something (API key, scope decision, etc.)
- 🔵 **QUEUED** — researched, prioritized, parser not yet written
- ⚫ **BLOCKED** — known source we cannot ingest right now (TLS/JS gating beyond what curl_cffi can reach, paywalled, etc.)
- ⚪ **OUT OF SCOPE** — deliberately excluded; reason given

## Legal / ethical framework

1. **Public domain.** Works of the U.S. Federal Government are not subject to copyright (17 U.S.C. §105). We can redistribute the underlying records.
2. **Robots.txt is respected** for every domain we crawl. If a path is `Disallow`, we skip it. (TODO: add a `robots.txt` check helper to `ingest_secrets.py`.)
3. **We identify ourselves.** Every request carries a UA and `From: unsealed-bot@github.com/mozltovcoktail/Unsealed` so site operators can contact us. For Akamai-fronted sources that JA3-fingerprint our UA, we route through `curl_cffi` with a real-Chrome handshake — same legal status, just defeats the bot-filter false positive.
4. **Polite rates.** Weekly cron + on-disk artifact cache. No source gets hit more than a few times per run.
5. **No classified material.** UNSEALED ingests material the publishing agency has chosen to make public. We do not exfiltrate, decrypt, or assemble anything that was meant to stay classified.
6. **Third-party aggregators** (GWU NSA, MuckRock, Black Vault, Mary Ferrell, etc.) compile public-domain gov docs but their compilations often have their own Terms of Service. We do NOT scrape them without an explicit per-source legal/ToS check. See the "Out of scope (for now)" section.

---

## 1. Federal — primary

| # | Source | Agency | Status | Access | Notes |
|---|---|---|:---:|---|---|
| 1.1 | NARA NDC quarterly release lists | NARA | ✅ | HTML hubs → .xlsx artifacts | `nara_ndc` group. ~11k records live. Auto-discovery (`discover.yml`) finds new release lists. |
| 1.2 | NARA Catalog API (`catalog.archives.gov/api/v2`) | NARA | 🟡 | REST API (key required) | `nara_catalog` group **SUSPENDED 2026-05-11**: `catalog.archives.gov/robots.txt` is `Disallow: /`. Per CONTEXT.md we don't run the parser until NARA confirms the API is exempt from the crawler-targeted robots policy. Email drafted (see [OUTREACH_DRAFTS.md](OUTREACH_DRAFTS.md)). API key request to `Catalog_API@nara.gov` (sent 2026-05-10) still pending. |
| 1.3 | AARO UAP cases & reports | AARO | ✅ | HTML scrape (curl_cffi) | `aaro` group. **54 records** live as of 2026-05-11 across 7 sub-sections (Case Resolutions, Reporting Trends, Official Imagery, UAP-Records, EFOIA Reading Room, Congressional Press Products, Resources). All tagged `topics=UAP`. |
| 1.4 | NASA NTRS | NASA | ✅ | REST API (federated at query time) | `/api/search` federates against `ntrs.nasa.gov/api`. Not ingested into D1 — live federation. |
| 1.5 | Internet Archive — National Security Archive collection | (IA mirror of CIA/NSA/etc.) | ✅ | IA advanced-search API (federated) | ~2.4M docs. Federated, not ingested. |
| 1.6 | **State FRUS** (1861–1989+) | State | 🟡 | Bulk EPUB downloads + GitHub TEI mirror for pub dates | `frus` group **SUSPENDED 2026-05-11**: `static.history.state.gov/robots.txt` is `Disallow: /` for all non-Twitterbot crawlers. The 313,257 previously-ingested FRUS records were **deleted from D1 the same day** for ethical compliance. The parent domain (history.state.gov) explicitly publishes the EPUB links, so this looks like an unintended default on the static subdomain — email drafted to webmaster (see [OUTREACH_DRAFTS.md](OUTREACH_DRAFTS.md)). Pending response. |
| 1.7 | **Project Blue Book** (USAF UFO investigation 1947–69) | USAF | ✅ | IA `project-blue-book` collection via advancedsearch API | `project_blue_book` group. **10,000 of 10,764 records** live (IA search caps at 10k/query; remainder is a cursor-pagination follow-up). All tagged `topics=UAP`. |
| 1.8 | **UAP misc** — ODNI / Navy / NASA | ODNI / Navy / NASA | ✅ | Hard-coded static list | `uap_misc` group. **6 records**: ODNI Preliminary UAP Assessment 2021, ODNI 2022 Annual Report, FLIR1/Gimbal/GoFast Navy videos, NASA UAP Independent Study 2023. All tagged `topics=UAP`. |

## 2. Federal — high-priority queue

These are the next big rocks. Each is in scope, scrape-friendly, and adds 100k+ new rows to D1.

| # | Source | Agency | Status | Access | Est. volume | Notes |
|---|---|---|:---:|---|---:|---|
| 2.1 | **CIA FOIA Reading Room (CREST)** — IA mirror | CIA | ✅ | IA `collection:cia-collection` (federated at query time) | 377,846 records | `cia` source in `/api/search`. Includes the entire CREST CIA-RDP* corpus (274,825 docs) + ~103k other CIA records. Zero D1 cost. The direct cia.gov scrape is still blocked by Akamai Bot Manager (parser stub `parse_cia_ufo` retained for a future Playwright pass to capture cia.gov-only Special Collections — JFK, Studies in Intelligence, etc.). |
| ~~2.2~~ | ~~**FBI Vault**~~ | ~~FBI~~ | ⚪ | — | ~~~100k docs~~ | **MOVED TO §5 OUT OF SCOPE 2026-05-11.** `vault.fbi.gov` deploys active anti-bot challenges — defeating them violates the bot-protection rule in [CONTEXT.md](CONTEXT.md). Reach via IA federation where mirrored, or skip. |
| 2.3 | **State Virtual Reading Room** | State | 🔵 | Search API, paginated | ~100k docs | `foia.state.gov`. Hillary Clinton emails, Kissinger cables, ongoing FOIA releases. |
| 2.4 | **DOE OpenNet** | DOE | 🔵 | Search API at `osti.gov/opennet` | ~500k records | DOE/AEC declassified nuclear-related records. |
| 2.5 | **NSA Declassified Documents** | NSA | 🔵 | HTML scrape | small (<10k) | `nsa.gov/news-features/declassified-documents`. High-prestige releases (VENONA, BOURBON, etc.). |
| 2.6 | **JFK Records Collection** | NARA | 🔵 | NARA-hosted catalog + bulk lists | ~5M pages | `archives.gov/research/jfk`. Mostly digitized. Could fold into NARA Catalog group. |
| 2.7 | **ODNI — IC on the Record** | ODNI | 🔵 | HTML scrape | <5k | Post-Snowden surveillance declassifications. `dni.gov` + `icontherecord.tumblr.com`. |
| 2.8 | **DTIC** (Defense Technical Information Center) | DoD | 🔵 | Public-access search API at `discover.dtic.mil` | ~1M+ records | DoD's central technical-report repository. Many were classified SECRET/CONFIDENTIAL when written, declassified after 25 years. Likely the largest single declassified corpus we'd touch. |
| 2.9 | **Presidential Libraries** (9 institutions) | NARA | 🔵 | HTML scrape per library | varies — high decision-density per record | JFK/LBJ/Nixon/Ford/Carter/Reagan/GHWB/Clinton/GWB. Each has its own FOIA reading room with declassified NSC memos, briefings, Situation Room cables. Higher cultural value/record than bulk NDC release lists. |

## 3. Federal — specialty / smaller

Each adds <50k rows. Worth doing but lower priority than §2.

| # | Source | Agency | Status | Access | Notes |
|---|---|---|:---:|---|---|
| 3.1 | NRO FOIA Reading Room | NRO | 🔵 | HTML scrape | `nro.gov/Freedom-of-Information-Act-FOIA/Declassified-Records/` |
| 3.2 | DIA FOIA | DIA | 🔵 | HTML scrape | `dia.mil/FOIA/FOIA-Electronic-Reading-Room/`. Note: Akamai-fronted, may need curl_cffi. |
| 3.3 | DoD service-branch FOIA reading rooms | Army / Navy / AF / USMC / USCG / SF | 🔵 | HTML scrape, varied CMS | One parser per branch. Modest per-branch volume. |
| 3.4 | DOJ FOIA Library | DOJ | 🔵 | HTML scrape | `justice.gov/oip/foia-library` |
| 3.5 | DHS / ICE / CBP / USCIS / TSA FOIA libraries | DHS | 🔵 | HTML scrape | One parser per component. |
| 3.6 | ATF / DEA / USPS-OIG / VA / IRS / Treasury FOIA libraries | various | 🔵 | HTML scrape | Long tail. |
| 3.7 | NGA FOIA | NGA | 🔵 | HTML scrape | `nga.mil/foia` |
| 3.8 | Department of War / OSD UAP records | DoW | 🟡 | URL TBD | `ingest/sources.json::dow_uap.urls` empty until 2026 release URL provided. |
| 3.9 | Wilson Center Digital Archive | (academic, but hosts gov-released material) | 🔵 | API | Cold War international docs. ToS review needed before scrape. |
| 3.10 | **NSA Cryptologic History** | NSA | 🔵 | HTML scrape | `nsa.gov/about/cryptologic-heritage/historical-figures-publications/`. Declassified Cold War SIGINT histories (TICOM, VENONA studies, etc.). Small but high-prestige. |
| 3.11 | **CIA Center for the Study of Intelligence (CSI)** | CIA | 🔵 | HTML scrape | `cia.gov/resources/csi/studies-in-intelligence/`. Declassified analytic histories, officer biographies. |
| 3.12 | **Naval History and Heritage Command** | Navy | 🔵 | HTML scrape | `history.navy.mil`. Declassified WWII/Cold War naval operations. |
| 3.13 | **Air Force Historical Research Agency (AFHRA)** | USAF | 🔵 | HTML scrape | `afhra.af.mil`. Declassified Air Force operational histories. |
| 3.14 | **Army Center of Military History** | Army | 🔵 | HTML scrape | `history.army.mil`. Declassified Vietnam-era / Cold War operational histories. |
| 3.15 | **ISCAP / PIDB decisions** | NARA / ISCAP | 🔵 | HTML scrape | `archives.gov/declassification/iscap` + `pidb`. Records released after appeals from declassification denials. Small but unique. |

## 4. Born-unclassified federal corpus — EXCLUDED (decided 2026-05-10)

These were public-by-default from day one. UNSEALED's brand is records that *were* classified, so this whole tier is out:

- govinfo.gov (Federal Register, CFR, Congressional Record, GAO, USGS, NIST, Presidential Public Papers, etc.)
- Public agency press releases / annual reports / public-affairs materials

(govinfo's bulk API would still be useful as a *cross-reference* — e.g., looking up the original classification authority for an EO cited in a declassified doc — but not as an ingest target.)

## 5. Out of scope (for now)

| Source | Reason |
|---|---|
| CRS Reports (`crsreports.congress.gov`) | Unclassified-but-suppressed, not classified. Out under the "previously classified" brand-scope rule. |
| Federal Register / CFR / Congressional Record / GAO / USGS / NIST / Presidential Public Papers / govinfo.gov | Born-unclassified — see §4. |
| GWU National Security Archive (`nsarchive.gwu.edu`) | Non-gov, academic. Their compilations may have site-specific ToS; need explicit permission/legal review before scrape. The underlying docs are public-domain so we could re-source them directly from the originating agency. |
| MuckRock (`muckrock.com`) | Non-gov, FOIA platform. Has Terms of Service governing crawler use. Has an API — use that path if we ever onboard, not scrape. |
| The Black Vault (`theblackvault.com`) | Non-gov, single-operator FOIA archive. ToS unclear. |
| Mary Ferrell Foundation | Non-gov, JFK-focused. Their digitizations have explicit "personal use" notices. |
| HathiTrust | Largely public-domain gov docs but the platform itself has access controls and a research-use agreement. |
| Any actually-classified material | Out of scope by definition. We index what the agency chose to publish. |
| **FBI Vault** (`vault.fbi.gov`) — direct scrape | Active anti-bot challenges = clear "humans only" signal per CONTEXT.md rule (2026-05-11). Parser stub `parse_fbi_ufo` retained in case the host policy changes or an IA mirror covers the content; do not enable. |
| **CIA cia.gov/readingroom** — direct scrape | Active Akamai Bot Manager JS challenge. Covered instead via IA federation (`collection:cia-collection`, 377,846 records) per row 2.1. Direct scrape stays excluded. |

---

## Decisions log

- **2026-05-10 — Brand scope:** previously-classified only, no time bound (§1+§2+§3 in, §4 out, CRS moved to §5). Strap text in `index.html` likely wants a rewrite to drop "RECENTLY" — TBD.
- **2026-05-10 — Parser order:** **State FRUS → CIA CREST → FBI Vault → DOE OpenNet → NSA Declass → ODNI**, then §3 long tail.
- **2026-05-10 — Aggregators:** keep §5 excluded. No outreach to GWU NSArchive / MuckRock / Black Vault for v1.
- **2026-05-11 — UAP sprint:** detour from sequential parser order to pull all UAP-related sources in one push. Delivered AARO expansion (54), Project Blue Book bulk-pull (10,000), and a UAP misc group (6). Total 10,060 UAP-tagged records.
- **2026-05-11 — Topic tagging system:** schema migration 005 added `records.topics TEXT` column (`,TAG1,TAG2,` delimited). General mechanism — drop-in for future `NUCLEAR`, `VIETNAM`, `CIVIL_RIGHTS` etc. toggles. UI exposes a `+ UAP` toggle alongside `+ SEALED`.
- **2026-05-11 — Playwright is now blocking work:** both CIA CREST and FBI Vault serve Akamai Bot Manager JS challenges that defeat curl_cffi. The §2 priority order needs Playwright integration to proceed past §2.1.
- **2026-05-11 — Bot-protection respect codified in CONTEXT.md:** active anti-bot signals (Akamai Bot Manager, Cloudflare Turnstile, reCAPTCHA, JS interstitials, behavioral analysis, CAPTCHAs) are treated as a "humans only" signal — same posture as robots.txt. **CIA cia.gov/readingroom and FBI Vault both moved from ⚫ BLOCKED to ⚪ OUT OF SCOPE.** CIA CREST content reaches us via IA federation (377k records); FBI Vault content stays unreachable unless an IA mirror surfaces.
- **2026-05-11 — Compliance audit findings:** discovered five issues against the freshly-codified CONTEXT.md rules.
  1. **`static.history.state.gov` blanket-Disallow** — 313,257 FRUS records were ingested in violation. **Deleted from D1.** `frus` group suspended pending webmaster reply. Outreach email drafted in `OUTREACH_DRAFTS.md`.
  2. **`catalog.archives.gov` blanket-Disallow** — `nara_catalog` parser suspended even though API key arrival is still pending. Outreach drafted.
  3. **USER_AGENT had been spoofing Safari** for every non-curl_cffi request since the AARO fix. **Reverted to honest `UNSEALED-bot/0.4 (+https://github.com/mozltovcoktail/Unsealed)`.** curl_cffi paths (AARO) still emit their own browser fingerprint via the `impersonate` flag — that's the narrow exception in CONTEXT.md and stays.
  4. **No programmatic robots.txt enforcement** — added `_robots_allowed()` helper in `ingest_secrets.py`; `fetch()` now refuses any Disallow'd URL with `RuntimeError`. Per-host cached for the run.
  5. **`nara_ndc` was missing crawl-delay** — `archives.gov/robots.txt` asks for `Crawl-delay: 10`. Added `crawl_delay_sec: 10` to the group config.
- **2026-05-11 — Additions to queue:** DTIC and Presidential Libraries added to §2, NSA Cryptologic History / CIA CSI / Naval History / AFHRA / Army CMH / ISCAP / PIDB added to §3. CIA CREST remains next per brand-fit priority.
- **2026-05-11 — Steady-state quota fix:** ingester loads `ingest/seen_hashes.json` (set of content_hashes already in D1, refreshed once per run from `SELECT content_hash FROM records`) and skips re-emitting them. Keeps weekly re-ingest inside D1 Workers Free 100k writes/day even as the corpus grows.

---

## How to update this doc

When a source ships:
1. Update its row to ✅ and add live-volume notes.
2. Update `ingest/sources.json` with the actual config.
3. Commit both together.

When a source is added to the backlog:
1. Add a row in §2 or §3 with a status.
2. If it's a `.gov` / `.mil` URL discovered by `discover.yml`, it'll already be in `ingest/discovered_sources` table — cross-reference here.
