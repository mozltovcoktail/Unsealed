#!/usr/bin/env python3
"""
UNSEALED — record ingester.

Sources are configured in ingest/sources.json. For each source group the
script will:
  1. Fetch the listing URL(s) (with TTL-aware on-disk cache)
  2. Discover linked release artifacts (.xlsx / .csv / detail HTML / API)
  3. Parse rows into the canonical schema
  4. Emit SQL INSERT OR IGNORE statements to db/ingest_<group>.sql
  5. Emit a health report to db/ingest_report.json
  6. Track newly-seen artifacts in ingest/seen_artifacts.json (hub-diff)

Output is intentionally SQL files (not direct D1 writes) so they can be
applied with `wrangler d1 execute unsealed --remote --file=...` and stay
inspectable / reversible. INSERT OR IGNORE on the content_hash column
makes re-applying the same SQL safe.

Usage:
  python3 ingest/ingest_secrets.py              # ingest all groups
  python3 ingest/ingest_secrets.py --group nara_ndc
  python3 ingest/ingest_secrets.py --dry-run    # parse, don't write SQL
  python3 ingest/ingest_secrets.py --limit 1000 # cap rows per group
  python3 ingest/ingest_secrets.py --no-cache   # bypass on-disk cache
  python3 ingest/ingest_secrets.py --cache-ttl 0  # ignore cache age

Dependencies (install once):
  pip3 install requests beautifulsoup4 openpyxl curl_cffi
  (curl_cffi is only required for sources with "impersonate" set in sources.json,
  currently aaro.mil — Akamai blocks vanilla urllib regardless of headers.)
"""
from __future__ import annotations

import argparse
import calendar
import datetime as _dt
import hashlib
import json
import re
import sys
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from urllib.parse import urljoin, urlparse

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    sys.stderr.write(
        "Missing deps. Run:  pip3 install requests beautifulsoup4 openpyxl\n"
    )
    sys.exit(1)

# Optional: curl_cffi gives us real-browser TLS fingerprints, which is the
# only way past Akamai-fronted .mil sources (e.g. aaro.mil) that JA3-block
# vanilla requests / urllib regardless of headers. Loaded lazily so the
# ingester still works without it for groups that don't need it.
try:
    from curl_cffi import requests as _cffi_requests  # type: ignore
    _HAS_CFFI = True
except ImportError:
    _HAS_CFFI = False

ROOT = Path(__file__).resolve().parent.parent
SOURCES_FILE = ROOT / "ingest" / "sources.json"
OUT_DIR = ROOT / "db"
CACHE_DIR = ROOT / "ingest" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
SEEN_ARTIFACTS_FILE = ROOT / "ingest" / "seen_artifacts.json"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/17.4 Safari/605.1.15"
)
FROM_HEADER = "unsealed-bot@github.com/mozltovcoktail/Unsealed"
TIMEOUT = 30

# Default cache TTL: hub pages get 7 days (we want to see new releases),
# content-addressed artifacts (dated .xlsx) effectively never expire.
DEFAULT_HUB_TTL_SEC = 7 * 24 * 3600
DEFAULT_ARTIFACT_TTL_SEC = 365 * 24 * 3600

RUN_ID = _dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


# ─── Canonical record ─────────────────────────────────────────────
@dataclass
class Record:
    title: str
    agency: str
    unsealed_date: str  # ISO 8601
    collection_id: str | None
    source_url: str
    description: str | None = None
    thumbnail_url: str | None = None
    source_artifact_url: str | None = None  # provenance
    is_sealed: int = 0  # 1 = record is on a candidate / pre-release list, not actually unsealed
    content_hash: str = ""

    def __post_init__(self):
        if not self.content_hash:
            h = hashlib.sha1()
            h.update((self.agency or "").encode("utf-8"))
            h.update(b"|")
            h.update((self.title or "").encode("utf-8"))
            h.update(b"|")
            h.update((self.source_url or "").encode("utf-8"))
            self.content_hash = h.hexdigest()


# ─── HTTP with on-disk cache ──────────────────────────────────────
def _cache_paths(url: str, binary: bool) -> tuple[Path, Path]:
    key = re.sub(r"[^a-zA-Z0-9]+", "_", url)[:160]
    suffix = ".bin" if binary else ".txt"
    return CACHE_DIR / f"{key}{suffix}", CACHE_DIR / f"{key}.meta.json"


def fetch(
    url: str,
    *,
    binary: bool = False,
    no_cache: bool = False,
    ttl_sec: int | None = None,
    extra_headers: dict | None = None,
    impersonate: str | None = None,
) -> bytes | str:
    cache, meta = _cache_paths(url, binary)
    if not no_cache and cache.exists():
        age = time.time() - cache.stat().st_mtime
        max_age = ttl_sec if ttl_sec is not None else DEFAULT_HUB_TTL_SEC
        if max_age <= 0 or age < max_age:
            return cache.read_bytes() if binary else cache.read_text("utf-8", "replace")
    print(f"  fetch {url}", file=sys.stderr)
    headers = {"user-agent": USER_AGENT, "From": FROM_HEADER}
    if extra_headers:
        headers.update(extra_headers)
    if impersonate:
        if not _HAS_CFFI:
            raise RuntimeError(
                f"source needs impersonate={impersonate!r} but curl_cffi is not installed. "
                "Run: pip3 install curl_cffi"
            )
        # curl_cffi sets its own UA/headers based on the impersonate profile.
        # We pass extra_headers (e.g. API keys) but not our default UA, which
        # would override the profile's fingerprint-consistent set.
        cffi_headers = dict(extra_headers) if extra_headers else None
        r = _cffi_requests.get(url, headers=cffi_headers, impersonate=impersonate, timeout=TIMEOUT)
    else:
        r = requests.get(url, headers=headers, timeout=TIMEOUT)
    r.raise_for_status()
    if binary:
        cache.write_bytes(r.content)
    else:
        cache.write_text(r.text, "utf-8")
    meta.write_text(
        json.dumps(
            {
                "url": url,
                "fetched_at": _dt.datetime.utcnow().isoformat() + "Z",
                "etag": r.headers.get("ETag"),
                "last_modified": r.headers.get("Last-Modified"),
                "status": r.status_code,
            }
        ),
        "utf-8",
    )
    return r.content if binary else r.text


# ─── Hub-diff: track artifact URLs across runs ────────────────────
def load_seen_artifacts() -> dict[str, list[str]]:
    if SEEN_ARTIFACTS_FILE.exists():
        try:
            return json.loads(SEEN_ARTIFACTS_FILE.read_text("utf-8"))
        except Exception:
            pass
    return {}


def save_seen_artifacts(seen: dict[str, list[str]]) -> None:
    SEEN_ARTIFACTS_FILE.write_text(json.dumps(seen, indent=2, sort_keys=True), "utf-8")


# ─── NARA NDC parser ──────────────────────────────────────────────
def parse_nara_ndc(group_cfg: dict, limit: int | None, *, fetch_opts) -> tuple[list[Record], list[str]]:
    out: list[Record] = []
    seen_xlsx: set[str] = set()

    for hub in group_cfg["urls"]:
        html = fetch(hub, **fetch_opts(is_hub=True))
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = urljoin(hub, a["href"])
            if href.lower().endswith((".xlsx", ".xls", ".csv")):
                seen_xlsx.add(href)

    print(f"[nara_ndc] {len(seen_xlsx)} release artifacts discovered", file=sys.stderr)
    artifacts = sorted(seen_xlsx)
    for art in artifacts:
        try:
            rows = _parse_release_artifact(art, fetch_opts=fetch_opts)
        except Exception as e:
            print(f"  skip {art}: {e}", file=sys.stderr)
            continue
        # IOD-candidate spreadsheets list entries proposed for declassification,
        # not yet released. Tag them so the UI can filter them out by default.
        sealed = 1 if "iod-candidate" in art.lower() else 0
        for row in rows:
            out.append(
                Record(
                    title=row.get("title", "").strip() or "(untitled)",
                    agency=group_cfg["agency"],
                    unsealed_date=row.get("unsealed_date") or "",
                    collection_id=row.get("collection_id")
                    or group_cfg["collection_id_default"],
                    source_url=row.get("source_url") or art,
                    description=row.get("description"),
                    source_artifact_url=art,
                    is_sealed=sealed,
                )
            )
            if limit and len(out) >= limit:
                return out, artifacts
    return out, artifacts


def _parse_release_artifact(url: str, *, fetch_opts) -> list[dict]:
    if url.lower().endswith(".csv"):
        text = fetch(url, **fetch_opts(is_hub=False))
        return _parse_csv_text(text, source_url=url)
    from openpyxl import load_workbook
    import io

    data = fetch(url, binary=True, **fetch_opts(is_hub=False))
    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    iso_date = _date_from_filename(url)
    rows: list[dict] = []
    for sheet in wb.worksheets:
        header = None
        for r in sheet.iter_rows(values_only=True):
            if header is None:
                if r and any(
                    isinstance(c, str) and ("title" in c.lower() or "entry" in c.lower())
                    for c in r if c
                ):
                    header = [
                        (c or "").strip().lower() if isinstance(c, str) else ""
                        for c in r
                    ]
                continue
            row = dict(zip(header, r))
            mapped = _map_ndc_row(row, default_date=iso_date, source_url=url)
            if mapped:
                rows.append(mapped)
    return rows


_FY_RX = re.compile(r"(?P<q>1st|2nd|3rd|4th)[^a-z0-9]+quarter[^a-z0-9]+(?:release[^a-z0-9]+)?(?:list[^a-z0-9]+)?(?:fy[^a-z0-9]*)?(?P<y>\d{2,4})", re.I)
_YEAR_FIRST_RX = re.compile(r"(?P<y>\d{4})[^a-z0-9]+ndc[^a-z0-9]+(?P<q>1st|2nd|3rd|4th)", re.I)
# FY2019-Q2, FY2020_Q1, fy2024q3 etc.
_FY_COMPACT_RX = re.compile(r"fy[-_]?(?P<y>20\d\d)[-_]?q(?P<q>[1-4])", re.I)
# 2023-3rd-quarter, 2024_4th_quarter
_CY_ORDINAL_RX = re.compile(
    r"(?P<y>20\d\d)[-_](?P<q>[1-4])(?:st|nd|rd|th)[-_]?quarter", re.I
)
# q4-2022, q1-2024 (quarter then year)
_CY_QYYYY_RX = re.compile(r"q(?P<q>[1-4])[-_](?P<y>20\d\d)", re.I)
# q1-february-23 (quarter, month-word, 2-digit year)
_CY_QMONTH_YY_RX = re.compile(
    r"q(?P<q>[1-4])[-_](?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[-_](?P<y>\d{2})\b",
    re.I,
)
# 2nd-qt-2023 (ordinal, qt/qtr, year)
_CY_ORD_QT_RX = re.compile(
    r"(?P<q>[1-4])(?:st|nd|rd|th)[-_](?:qt|qtr)[-_](?P<y>20\d\d)", re.I
)
# released-entries-05-12.xls → May 2012 (month-end)
_RELEASED_MONTH_RX = re.compile(
    r"released-entries-(?P<mo>\d{2})-(?P<y>\d{2})\.xlsx?$", re.I
)


def _q_to_iso(q: int, y: int, *, fiscal: bool) -> str:
    if fiscal:
        return {1: f"{y - 1:04d}-12-31", 2: f"{y:04d}-03-31",
                3: f"{y:04d}-06-30", 4: f"{y:04d}-09-30"}[q]
    return {1: f"{y:04d}-03-31", 2: f"{y:04d}-06-30",
            3: f"{y:04d}-09-30", 4: f"{y:04d}-12-31"}[q]


def _date_from_filename(url: str) -> str:
    name = url.rsplit("/", 1)[-1].lower()
    m = _RELEASED_MONTH_RX.search(name)
    if m:
        mo, y = int(m.group("mo")), 2000 + int(m.group("y"))
        if 1 <= mo <= 12:
            last = calendar.monthrange(y, mo)[1]
            return f"{y:04d}-{mo:02d}-{last:02d}"
    m = _FY_COMPACT_RX.search(name)
    if m:
        return _q_to_iso(int(m.group("q")), int(m.group("y")), fiscal=True)
    m = _CY_ORDINAL_RX.search(name)
    if m:
        return _q_to_iso(int(m.group("q")), int(m.group("y")), fiscal=False)
    m = _CY_ORD_QT_RX.search(name)
    if m:
        return _q_to_iso(int(m.group("q")), int(m.group("y")), fiscal=False)
    m = _CY_QMONTH_YY_RX.search(name)
    if m:
        return _q_to_iso(int(m.group("q")), 2000 + int(m.group("y")), fiscal=False)
    m = _CY_QYYYY_RX.search(name)
    if m:
        return _q_to_iso(int(m.group("q")), int(m.group("y")), fiscal=False)
    for rx in (_YEAR_FIRST_RX, _FY_RX):
        m = rx.search(name)
        if not m:
            continue
        q = {"1st": 1, "2nd": 2, "3rd": 3, "4th": 4}[m.group("q").lower()]
        y = int(m.group("y"))
        if y < 100:
            y += 2000
        return _q_to_iso(q, y, fiscal="fy" in name)
    return ""


def _parse_csv_text(text: str, source_url: str = "") -> list[dict]:
    import csv, io as _io

    rdr = csv.DictReader(_io.StringIO(text))
    iso = _date_from_filename(source_url) if source_url else ""
    return [
        m
        for m in (
            _map_ndc_row({k.lower(): v for k, v in r.items()}, default_date=iso, source_url=source_url)
            for r in rdr
        )
        if m
    ]


def _map_ndc_row(row: dict, default_date: str = "", source_url: str = "") -> dict | None:
    title = (
        row.get("record entry title")
        or row.get("entry title")
        or row.get("title")
        or row.get("series title")
        or row.get("collection title")
        or ""
    )
    if not title:
        return None
    def _s(v):
        return "" if v is None else str(v).strip()

    rg = _s(row.get("rg") or row.get("record group"))
    office = _s(row.get("office"))
    custodial = _s(row.get("custodial unit"))
    media = _s(row.get("media type"))
    hms_id = _s(
        row.get("hms record entry id# ")
        or row.get("hms record entry id#")
        or row.get("hms entry")
    )

    desc_bits = [b for b in (office, custodial, media) if b]
    description = " // ".join(desc_bits) if desc_bits else None

    date = (
        row.get("release date")
        or row.get("date released")
        or row.get("declass date")
        or ""
    )
    iso = _to_iso_date(str(date)) or default_date

    return {
        "title": str(title).strip(),
        "collection_id": (f"RG {str(rg).strip()}" if rg else None),
        "unsealed_date": iso,
        "description": description,
        "source_url": (f"{source_url}#hms-{hms_id}" if hms_id and source_url else source_url) or None,
    }


_DATE_RX = [
    re.compile(r"^(\d{4})-(\d{2})-(\d{2})"),
    re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})"),
    re.compile(r"^(\d{4})/(\d{1,2})/(\d{1,2})"),
    re.compile(r"^(\d{1,2})-(\d{1,2})-(\d{4})"),
]


def _to_iso_date(s: str) -> str | None:
    s = s.strip()
    if not s:
        return None
    for rx in _DATE_RX:
        m = rx.match(s)
        if not m:
            continue
        g = m.groups()
        if len(g[0]) == 4:
            y, mo, d = g
        else:
            mo, d, y = g
        try:
            return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
        except ValueError:
            return None
    return None


# ─── NARA Catalog API ─────────────────────────────────────────────
# Public JSON API at catalog.archives.gov. No auth required for reads.
# Docs: https://catalog.archives.gov/api/v2/api-docs
def parse_nara_catalog(group_cfg: dict, limit: int | None, *, fetch_opts) -> tuple[list[Record], list[str]]:
    import os

    api_key = os.environ.get("NARA_API_KEY", "").strip()
    if not api_key:
        print(
            "[nara_catalog] NARA_API_KEY env var not set — skipping. "
            "Request a free key at Catalog_API@nara.gov and add it as a repo secret.",
            file=sys.stderr,
        )
        return [], []

    out: list[Record] = []
    seen_naids: set[str] = set()
    artifacts: list[str] = []

    base = "https://catalog.archives.gov/api/v2/records/search"
    headers = {"x-api-key": api_key, "Accept": "application/json"}
    for query in group_cfg.get("queries", []):
        q = query["q"]
        per_query_limit = int(query.get("limit", 200))
        # Page in 100-row chunks (API max).
        offset = 0
        page_size = 100
        while offset < per_query_limit:
            url = (
                f"{base}?q={requests.utils.quote(q)}"
                f"&limit={min(page_size, per_query_limit - offset)}"
                f"&offset={offset}"
            )
            artifacts.append(url)
            try:
                text = fetch(url, **fetch_opts(is_hub=True), extra_headers=headers)
                payload = json.loads(text)
            except Exception as e:
                print(f"  [nara_catalog] skip {q} @ {offset}: {e}", file=sys.stderr)
                break
            hits = (
                payload.get("body", {})
                .get("hits", {})
                .get("hits", [])
            )
            if not hits:
                break
            for hit in hits:
                src = hit.get("_source") or {}
                rec = src.get("record") or {}
                naid = str(rec.get("naId") or hit.get("_id") or "")
                if not naid or naid in seen_naids:
                    continue
                seen_naids.add(naid)
                title = (rec.get("title") or "").strip()
                if not title:
                    continue
                # Date heuristics
                date_iso = ""
                dates = rec.get("productionDates") or rec.get("inclusiveDates") or []
                if isinstance(dates, list) and dates:
                    first = dates[0]
                    if isinstance(first, dict):
                        date_iso = (
                            _to_iso_date(str(first.get("logicalDate", "")))
                            or _to_iso_date(str(first.get("startDate", "")))
                            or ""
                        )
                # Best-effort description
                scope = (rec.get("scopeAndContentNote") or "").strip()
                source_url = f"https://catalog.archives.gov/id/{naid}"
                out.append(
                    Record(
                        title=title,
                        agency=group_cfg["agency"],
                        unsealed_date=date_iso,
                        collection_id=group_cfg["collection_id_default"],
                        source_url=source_url,
                        description=scope[:500] if scope else None,
                        source_artifact_url=url,
                    )
                )
                if limit and len(out) >= limit:
                    return out, artifacts
            offset += page_size
    return out, artifacts


# ─── AARO parser ──────────────────────────────────────────────────
# AARO Cases-and-Reports page: each release sits inside a list-item that
# contains a date string like "October 2024" near the PDF anchor.
_MONTH_RX = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+(\d{1,2},\s*)?(\d{4})\b",
    re.I,
)
_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _date_near(node) -> str:
    """Walk up the DOM looking for a Month-Year string."""
    cur = node
    for _ in range(4):
        if cur is None:
            break
        text = cur.get_text(" ", strip=True) if hasattr(cur, "get_text") else ""
        m = _MONTH_RX.search(text)
        if m:
            mo = _MONTHS[m.group(1).lower()[:4].rstrip()]
            day = int((m.group(2) or "1").strip(", ").strip()) if m.group(2) else 1
            y = int(m.group(3))
            return f"{y:04d}-{mo:02d}-{day:02d}"
        cur = getattr(cur, "parent", None)
    return ""


def parse_aaro(group_cfg: dict, limit: int | None, *, fetch_opts) -> tuple[list[Record], list[str]]:
    out: list[Record] = []
    artifacts: list[str] = []
    for hub in group_cfg["urls"]:
        artifacts.append(hub)
        html = fetch(hub, **fetch_opts(is_hub=True))
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = urljoin(hub, a["href"])
            if not href.lower().endswith(".pdf"):
                continue
            title = (a.get_text(strip=True) or Path(href).stem).strip()
            date = _date_near(a)
            out.append(
                Record(
                    title=title or "(untitled AARO release)",
                    agency=group_cfg["agency"],
                    unsealed_date=date,
                    collection_id=group_cfg["collection_id_default"],
                    source_url=href,
                    source_artifact_url=hub,
                )
            )
            if limit and len(out) >= limit:
                return out, artifacts
    return out, artifacts


PARSERS = {
    "nara_ndc": parse_nara_ndc,
    "nara_catalog": parse_nara_catalog,
    "aaro": parse_aaro,
    # dow_uap intentionally absent until a verified source URL exists.
}


# ─── SQL emission ─────────────────────────────────────────────────
def emit_sql(group: str, records: list[Record]) -> Path:
    out_path = OUT_DIR / f"ingest_{group}.sql"
    with out_path.open("w", encoding="utf-8") as f:
        f.write(f"-- UNSEALED ingest — {group} — {len(records)} records — run {RUN_ID}\n")
        for r in records:
            f.write(
                "INSERT OR IGNORE INTO records "
                "(title, agency, unsealed_date, collection_id, source_url, "
                "description, thumbnail_url, source_artifact_url, is_sealed, "
                "ingest_run_id, content_hash) "
                "VALUES ("
                f"{_q(r.title)}, {_q(r.agency)}, {_q(r.unsealed_date)}, {_q(r.collection_id)}, "
                f"{_q(r.source_url)}, {_q(r.description)}, {_q(r.thumbnail_url)}, "
                f"{_q(r.source_artifact_url)}, {int(r.is_sealed)}, "
                f"{_q(RUN_ID)}, {_q(r.content_hash)}"
                ");\n"
            )
    return out_path


def _q(v: str | None) -> str:
    if v is None or v == "":
        return "NULL"
    return "'" + str(v).replace("'", "''") + "'"


# ─── CLI ──────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", help="run only one source group")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--no-cache", action="store_true", help="bypass on-disk cache")
    ap.add_argument(
        "--cache-ttl", type=int, default=None,
        help="hub-page cache TTL in seconds (default: 7d). 0 = always re-fetch."
    )
    ap.add_argument(
        "--self-test", action="store_true",
        help="run internal asserts (date parsing) and exit"
    )
    args = ap.parse_args()

    if args.self_test:
        _self_test()
        print("self-test ok", file=sys.stderr)
        return 0

    cfg = json.loads(SOURCES_FILE.read_text("utf-8"))
    groups = [args.group] if args.group else [g for g in cfg if not g.startswith("_")]

    seen_artifacts = load_seen_artifacts()
    report: dict = {
        "run_id": RUN_ID,
        "groups": {},
        "total_records": 0,
        "new_artifacts": {},
    }

    def make_fetch_opts(impersonate: str | None):
        def fetch_opts(*, is_hub: bool) -> dict:
            ttl = (
                args.cache_ttl
                if args.cache_ttl is not None
                else (DEFAULT_HUB_TTL_SEC if is_hub else DEFAULT_ARTIFACT_TTL_SEC)
            )
            opts = {"no_cache": args.no_cache, "ttl_sec": ttl}
            if impersonate:
                opts["impersonate"] = impersonate
            return opts
        return fetch_opts

    for g in groups:
        if g not in cfg:
            print(f"unknown group: {g}", file=sys.stderr)
            continue
        if g not in PARSERS:
            print(f"[{g}] no parser registered — skipping", file=sys.stderr)
            report["groups"][g] = {"status": "skipped_no_parser"}
            continue
        if not (cfg[g].get("urls") or cfg[g].get("queries")):
            print(f"[{g}] no urls/queries configured — skipping", file=sys.stderr)
            report["groups"][g] = {"status": "skipped_no_urls"}
            continue
        print(f"[{g}] parsing...", file=sys.stderr)
        try:
            recs, artifacts = PARSERS[g](cfg[g], args.limit, fetch_opts=make_fetch_opts(cfg[g].get("impersonate")))
        except Exception as e:
            print(f"[{g}] FAILED: {e}", file=sys.stderr)
            report["groups"][g] = {"status": "error", "error": str(e)}
            continue
        prev = set(seen_artifacts.get(g, []))
        new = sorted(set(artifacts) - prev)
        seen_artifacts[g] = sorted(set(artifacts) | prev)
        if new:
            print(f"[{g}] {len(new)} NEW artifacts since last run", file=sys.stderr)
            report["new_artifacts"][g] = new

        print(f"[{g}] {len(recs)} records, {len(artifacts)} artifacts", file=sys.stderr)
        report["groups"][g] = {
            "status": "ok",
            "records": len(recs),
            "artifacts": len(artifacts),
            "new_artifacts": len(new),
        }
        report["total_records"] += len(recs)
        if args.dry_run:
            for r in recs[:5]:
                print(json.dumps(asdict(r), indent=2))
            continue
        path = emit_sql(g, recs)
        print(f"[{g}] wrote {path.relative_to(ROOT)}", file=sys.stderr)

    if not args.dry_run:
        save_seen_artifacts(seen_artifacts)
        report_path = OUT_DIR / "ingest_report.json"
        report_path.write_text(json.dumps(report, indent=2), "utf-8")
        print(f"wrote {report_path.relative_to(ROOT)}", file=sys.stderr)

    print(f"total: {report['total_records']} records", file=sys.stderr)
    return 0


def _self_test() -> None:
    cases = [
        # FY-compact: FY2019-Q2 → fiscal Q2 = calendar Q1 of 2019
        ("https://declassification.blogs.archives.gov/wp-content/uploads/sites/16/2019/07/FY2019-Q2-Release-List-Excel-Format.xlsx", "2019-03-31"),
        ("https://declassification.blogs.archives.gov/wp-content/uploads/sites/16/2019/08/FY2019-Q3-Release-List-Excel-Format.xlsx", "2019-06-30"),
        ("https://declassification.blogs.archives.gov/wp-content/uploads/sites/16/2019/10/FY2019-Q4-Release-List-Excel-Format.xlsx", "2019-09-30"),
        ("https://declassification.blogs.archives.gov/wp-content/uploads/sites/16/2020/01/FY2020-Q1-Release-List-Excel-Format.xlsx", "2019-12-31"),
        # Calendar-year ordinal quarter
        ("https://declassification.blogs.archives.gov/wp-content/uploads/sites/16/2023/10/2023-3rd-quarter-release-list.xlsx", "2023-09-30"),
        ("https://declassification.blogs.archives.gov/wp-content/uploads/sites/16/2023/10/2023-4th-Quarter-Release-List-October-6th.xlsx", "2023-12-31"),
        # Existing patterns still work
        ("https://www.archives.gov/files/declassification/ndc/2024-ndc-1st-quarter-release-list-excel.xlsx", "2024-03-31"),
        ("https://www.archives.gov/files/2nd-quarter-release-list-fy-26.xlsx", "2026-03-31"),
        # released-entries-MM-YY (legacy monthly NDC lists) → month-end of 20YY-MM
        ("https://www.archives.gov/declassification/ndc/reports/released-entries-05-12.xls", "2012-05-31"),
        ("https://www.archives.gov/declassification/ndc/reports/released-entries-07-12.xls", "2012-07-31"),
        ("https://www.archives.gov/declassification/ndc/reports/released-entries-04-13.xls", "2013-04-30"),
        # q4-2022 form (quarter then calendar year)
        ("https://www.archives.gov/files/declassification/ndc/release-list-q4-2022-excel.xlsx", "2022-12-31"),
        # 2nd-qt-2023 form (ordinal + qt/qtr abbreviation)
        ("https://www.archives.gov/files/declassification/ndc/reports/release-list-projects-for-2nd-qt-2023.xlsx", "2023-06-30"),
        # q1-february-23 form (quarter, month-word, 2-digit year)
        ("https://www.archives.gov/files/declassification/release-list-q1-february-23.xlsx", "2023-03-31"),
    ]
    for url, expected in cases:
        got = _date_from_filename(url)
        assert got == expected, f"{url}\n  expected {expected!r}, got {got!r}"


if __name__ == "__main__":
    sys.exit(main())
