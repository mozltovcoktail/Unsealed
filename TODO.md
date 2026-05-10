# UNSEALED — Project TODO

## ★ Top priority — Aaron action

### 1. Register a NARA Catalog API key
**Why:** The catalog.archives.gov SPA blocks unauthenticated `/api/v2/*` calls. With a key, UNSEALED gains direct access to NARA's full catalog (currently the only major .gov source we can't federate against).

**How (5 min):**
1. Visit https://api.data.gov/signup/ (NARA Catalog v2 uses api.data.gov for key issuance — same system used by NASA, USDA, etc.)
2. Fill in name + email + a one-line description ("Searching declassified records via UNSEALED prototype")
3. Submit. Key arrives by email immediately, unrate-limited free tier is 1,000 requests/hour.
4. Save the key to `~/.secrets/nara_api_key` (`chmod 600`)
5. Tell Claude — I'll add a NARA federation source to `/api/search`, alongside Internet Archive and NASA NTRS.

**Backup path:** If api.data.gov isn't the right issuer, the NARA Catalog UI (https://catalog.archives.gov/) has a "Developer" link in the footer pointing to their actual key registration. Worst case: fill out the form there.

---

## Backlog

- **Department of War UAP source** — `ingest/sources.json::dow_uap.urls` is empty. Drop the canonical 2026 release URL when published.
- **PDF page-1 rasterization** — `functions/api/preview.js` returns metadata only. A pdf.js Worker could render real page-1 thumbnails on demand. Worth its own session.
- **pdf.js for cross-browser PDF rendering** — currently `/api/document` returns the direct IA PDF URL and we put it straight into an `<iframe>`. Desktop Chrome/Firefox/Edge render this inline natively. iOS Safari downloads instead. Headless Chromium (Playwright preview) renders blank. To bulletproof: ship Mozilla's pdf.js viewer (self-hosted in `/public/pdfjs/`) and a `/api/pdf-proxy?url=...` Cloudflare Worker that fetches IA PDFs and adds `Access-Control-Allow-Origin: *` so pdf.js can stream them. Estimated 30 min when prioritized.
- **Source filter toggles** — when federation is live, swap the agency toggle row for source toggles ("Internet Archive only", "NASA NTRS only", "Curated only").
- **Capacitor wrap (Phase 2 in-app browser)** — wrap UNSEALED with Capacitor and switch from `<iframe>` + new-tab fallback to `@capacitor/browser` (`Browser.open()`). On iOS this becomes SFSafariViewController, on Android it's Chrome Custom Tabs — system in-app browser, never leaves the app, swipe-back returns to UNSEALED. Solves the X-Frame-Options blocked sources cleanly. Defer until the web flow is solid.
- **Stale agency facet cache** — `/api/agencies` returns `cache-control: public, max-age=300`. Drop to `no-store` if instant updates after ingest matter.
