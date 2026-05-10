# UNSEALED — Source Inventory

Living index of every U.S. Government document source we know about,
whether it's live, queued, blocked, or out of scope, plus the access
method and any legal/ethical notes.

The authoritative wiring lives in `ingest/sources.json` — this doc is the
human-readable backlog and audit trail that surrounds it.

Last manual review: 2026-05-10.

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
| 1.2 | NARA Catalog API (`catalog.archives.gov/api/v2`) | NARA | 🟡 | REST API (key required) | `nara_catalog` group. Parser written; awaiting `NARA_API_KEY` repo secret. Free tier: 10k queries/month. Email sent to `Catalog_API@nara.gov` 2026-05-10. |
| 1.3 | AARO UAP cases & reports | AARO | ✅ | HTML scrape (curl_cffi) | `aaro` group. 11 records live as of 2026-05-10. Akamai TLS-fingerprinting required curl_cffi escalation. |
| 1.4 | NASA NTRS | NASA | ✅ | REST API (federated at query time) | `/api/search` federates against `ntrs.nasa.gov/api`. Not ingested into D1 — live federation. |
| 1.5 | Internet Archive — National Security Archive collection | (IA mirror of CIA/NSA/etc.) | ✅ | IA advanced-search API (federated) | ~2.4M docs. Federated, not ingested. |

## 2. Federal — high-priority queue

These are the next big rocks. Each is in scope, scrape-friendly, and adds 100k+ new rows to D1.

| # | Source | Agency | Status | Access | Est. volume | Notes |
|---|---|---|:---:|---|---:|---|
| 2.1 | **govinfo.gov bulk data** | GPO | 🔵 | Bulk-data REST API | ≫1M | Master index of published federal docs — Federal Register, CFR, Congressional Record, GAO, Presidential papers. **Decision needed:** is this in-brand? (See open decisions.) |
| 2.2 | **CIA FOIA Reading Room (CREST)** | CIA | 🔵 | HTML scrape + search JSON | ~13M pages | Highest brand-fit. `cia.gov/readingroom`. Robots-friendly, has its own search backend. |
| 2.3 | **FBI Vault** | FBI | 🔵 | HTML scrape (Drupal) | ~100k docs | `vault.fbi.gov`. Topic-organized lists, predictable URLs. |
| 2.4 | **State FRUS** (Foreign Relations of the U.S.) | State | 🔵 | Full-text HTML + EPUB bulk | ~500k pages | `history.state.gov/historicaldocuments`. Gold-standard declassified diplomatic record, 1861–present. Bulk downloads available. |
| 2.5 | **State Virtual Reading Room** | State | 🔵 | Search API, paginated | ~100k docs | `foia.state.gov`. Hillary Clinton emails, Kissinger cables, ongoing FOIA releases. |
| 2.6 | **DOE OpenNet** | DOE | 🔵 | Search API at `osti.gov/opennet` | ~500k records | DOE/AEC declassified nuclear-related records. |
| 2.7 | **NSA Declassified Documents** | NSA | 🔵 | HTML scrape | small (<10k) | `nsa.gov/news-features/declassified-documents`. High-prestige releases (VENONA, BOURBON, etc.). |
| 2.8 | **JFK Records Collection** | NARA | 🔵 | NARA-hosted catalog + bulk lists | ~5M pages | `archives.gov/research/jfk`. Mostly digitized. Could fold into NARA Catalog group. |
| 2.9 | **CRS Reports** | LoC / Congress | 🔵 | Official JSON at `crsreports.congress.gov` | ~15k reports | Congressional Research Service — was suppressed for decades, now official + bulk-listable. |
| 2.10 | **ODNI — IC on the Record** | ODNI | 🔵 | HTML scrape | <5k | Post-Snowden surveillance declassifications. `dni.gov` + `icontherecord.tumblr.com`. |

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

## 4. Born-unclassified federal corpus

These are NOT "secret stuff that was declassified" — they were public-by-default from day one. Brand-fit is debatable. **Decision needed.**

| # | Source | Agency | Status | Notes |
|---|---|---|:---:|---|
| 4.1 | Federal Register | OFR / GPO | ⚪? | Daily executive-branch rulemaking. Via govinfo. |
| 4.2 | Code of Federal Regulations | OFR / GPO | ⚪? | Compiled regs. Via govinfo. |
| 4.3 | Congressional Record | Congress | ⚪? | Daily floor proceedings. Via govinfo. |
| 4.4 | GAO Reports | GAO | ⚪? | `gao.gov` — bulk API. Audit & evaluation reports. |
| 4.5 | USGS publications | USGS | ⚪? | Scientific reports. |
| 4.6 | NIST publications | NIST | ⚪? | Standards + research. |
| 4.7 | Presidential Public Papers | NARA / GPO | ⚪? | Press releases, exec orders. Via govinfo. |

## 5. Out of scope (for now)

| Source | Reason |
|---|---|
| GWU National Security Archive (`nsarchive.gwu.edu`) | Non-gov, academic. Their compilations may have site-specific ToS; need explicit permission/legal review before scrape. The underlying docs are public-domain so we could re-source them directly from the originating agency. |
| MuckRock (`muckrock.com`) | Non-gov, FOIA platform. Has Terms of Service governing crawler use. Has an API — use that path if we ever onboard, not scrape. |
| The Black Vault (`theblackvault.com`) | Non-gov, single-operator FOIA archive. ToS unclear. |
| Mary Ferrell Foundation | Non-gov, JFK-focused. Their digitizations have explicit "personal use" notices. |
| HathiTrust | Largely public-domain gov docs but the platform itself has access controls and a research-use agreement. |
| Any actually-classified material | Out of scope by definition. We index what the agency chose to publish. |

---

## Open scope decisions

These are surfaced for Aaron — see `CLAUDE.md` §"Defer to Aaron on product-level decisions".

🟧 **DECISION #1: Brand scope — does UNSEALED ingest only "declassified" material, or all unclassified federal records?**

- (a) **Declassified-only.** Strap reads "RECENTLY DECLASSIFIED". §1, §2, §3 are in. §4 is out. Strong brand identity; smaller corpus.
- (b) **All unclassified.** §4 in too: Federal Register, Congressional Record, GAO, USGS, NIST, Public Papers. Strap broadens to "U.S. GOVERNMENT RECORDS". Order-of-magnitude more rows; brand becomes "the search engine for federal publications". Closer to a govinfo mirror with extra reach.
- (c) **Two tiers.** Default search is declassified-only; a toggle (like the `+ SEALED` one we just shipped) opts users into the wider unclassified corpus. Best of both, but doubles the ingest + indexing cost.

**Recommend (a)** for now. UNSEALED's name and visual identity carry a strong "secrets revealed" promise. Born-public material would dilute that. If usage grows, (c) becomes easy to add — we already have the toggle-as-filter pattern.

🟧 **DECISION #2: Implementation priority for §2 sources?**

Default sequence (rough effort + payoff judgment):

- (a) **CIA CREST → State FRUS → FBI Vault → DOE OpenNet → NSA → ODNI** (brand-fit first, biggest-volume tail later)
- (b) **State FRUS → CIA CREST → FBI Vault → CRS → DOE OpenNet → NSA → ODNI** (cleanest data first — FRUS is unusually well-structured, fastest to ship)
- (c) Different order — name it.

**Recommend (b).** FRUS is the lowest-risk first parser to validate the §2 expansion pattern (one parser → 500k clean rows). CREST is the highest-prestige but messier (~13M scanned pages, OCR'd metadata varies). Doing FRUS first de-risks the toolchain before we hit the messier ones.

🟧 **DECISION #3: Third-party aggregators (§5) — keep excluded, or reach out for permission to ingest?**

- (a) **Keep excluded.** All their content is reachable upstream from the agency; we just write more parsers. Cleanest legally.
- (b) **Reach out** to GWU NSArchive and MuckRock for explicit permission to index their FOIA-release attachments. Could 10x our coverage of obscure agency releases overnight.
- (c) **MuckRock API only** — their public API is explicitly for programmatic use within their ToS. Lower-risk variant of (b).

**Recommend (a) for v1, revisit (c) later.** No legal exposure, no relationship overhead, and §2 + §3 alone are ~6 months of parser work.

---

## How to update this doc

When a source ships:
1. Update its row to ✅ and add live-volume notes.
2. Update `ingest/sources.json` with the actual config.
3. Commit both together.

When a source is added to the backlog:
1. Add a row in §2 or §3 with a status.
2. If it's a `.gov` / `.mil` URL discovered by `discover.yml`, it'll already be in `ingest/discovered_sources` table — cross-reference here.
