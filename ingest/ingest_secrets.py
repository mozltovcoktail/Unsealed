#!/usr/bin/env python3
"""
UNSEALED — record ingester.

Sources are configured in ingest/sources.json. For each source group the
script will:
  1. Fetch the listing URL(s)
  2. Discover linked release artifacts (.xlsx / .csv / detail HTML)
  3. Parse rows into the canonical schema
  4. Emit SQL INSERT statements to db/ingest_<group>.sql

Output is intentionally SQL files (not direct D1 writes) so they can be
applied with `wrangler d1 execute unsealed --remote --file=...` and stay
inspectable / reversible.

Usage:
  python3 ingest/ingest_secrets.py              # ingest all groups
  python3 ingest/ingest_secrets.py --group nara_ndc
  python3 ingest/ingest_secrets.py --dry-run    # parse, don't write SQL
  python3 ingest/ingest_secrets.py --limit 1000 # cap rows per group

Dependencies (install once):
  pip3 install requests beautifulsoup4 openpyxl
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from urllib.parse import urljoin

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    sys.stderr.write(
        "Missing deps. Run:  pip3 install requests beautifulsoup4 openpyxl\n"
    )
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
SOURCES_FILE = ROOT / "ingest" / "sources.json"
OUT_DIR = ROOT / "db"
CACHE_DIR = ROOT / "ingest" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

USER_AGENT = "UNSEALED/0.1 (+ingest; contact: aaron)"
TIMEOUT = 30


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


# ─── HTTP with on-disk cache ──────────────────────────────────────
def fetch(url: str, *, binary: bool = False) -> bytes | str:
    key = re.sub(r"[^a-zA-Z0-9]+", "_", url)[:160]
    suffix = ".bin" if binary else ".txt"
    cache = CACHE_DIR / f"{key}{suffix}"
    if cache.exists():
        return cache.read_bytes() if binary else cache.read_text("utf-8", "replace")
    print(f"  fetch {url}", file=sys.stderr)
    r = requests.get(url, headers={"user-agent": USER_AGENT}, timeout=TIMEOUT)
    r.raise_for_status()
    if binary:
        cache.write_bytes(r.content)
        return r.content
    cache.write_text(r.text, "utf-8")
    return r.text


# ─── NARA NDC parser ──────────────────────────────────────────────
# NDC quarterly releases are linked from a hub page; the artifacts are
# .xlsx files with columns including Title, Record Group, Release Date.
def parse_nara_ndc(group_cfg: dict, limit: int | None) -> list[Record]:
    out: list[Record] = []
    seen_xlsx: set[str] = set()

    for hub in group_cfg["urls"]:
        html = fetch(hub)
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = urljoin(hub, a["href"])
            if href.lower().endswith((".xlsx", ".xls", ".csv")):
                seen_xlsx.add(href)

    print(f"[nara_ndc] {len(seen_xlsx)} release artifacts discovered", file=sys.stderr)
    for art in sorted(seen_xlsx):
        try:
            rows = _parse_release_artifact(art)
        except Exception as e:
            print(f"  skip {art}: {e}", file=sys.stderr)
            continue
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
                )
            )
            if limit and len(out) >= limit:
                return out
    return out


def _parse_release_artifact(url: str) -> list[dict]:
    if url.lower().endswith(".csv"):
        text = fetch(url)
        return _parse_csv_text(text, source_url=url)
    # .xlsx / .xls
    from openpyxl import load_workbook
    import io

    data = fetch(url, binary=True)
    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    iso_date = _date_from_filename(url)
    rows: list[dict] = []
    for sheet in wb.worksheets:
        header = None
        for r in sheet.iter_rows(values_only=True):
            if header is None:
                # NDC header row contains "title" or "entry title"
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


# Derive ISO date from filenames like "2nd-quarter-release-list-fy-26.xlsx"
# (FY26 Q2 → Jan-Mar 2026 → use 2026-03-31 as the period-end date).
_FY_RX = re.compile(r"(?P<q>1st|2nd|3rd|4th)[^a-z0-9]+quarter[^a-z0-9]+(?:release[^a-z0-9]+)?(?:list[^a-z0-9]+)?(?:fy[^a-z0-9]*)?(?P<y>\d{2,4})", re.I)
# Also match older "2024-ndc-2nd-quarter-release-list-..." (year-prefixed).
_YEAR_FIRST_RX = re.compile(r"(?P<y>\d{4})[^a-z0-9]+ndc[^a-z0-9]+(?P<q>1st|2nd|3rd|4th)", re.I)


def _date_from_filename(url: str) -> str:
    name = url.rsplit("/", 1)[-1].lower()
    for rx in (_YEAR_FIRST_RX, _FY_RX):
        m = rx.search(name)
        if not m:
            continue
        q = {"1st": 1, "2nd": 2, "3rd": 3, "4th": 4}[m.group("q").lower()]
        y = int(m.group("y"))
        if y < 100:
            y += 2000
        # Fiscal-year quarter end-dates (federal FY starts Oct):
        #   FYxx Q1 = Oct-Dec yy-1     end → Dec 31 (yy-1)
        #   Q2 = Jan-Mar yy             end → Mar 31 yy
        #   Q3 = Apr-Jun yy             end → Jun 30 yy
        #   Q4 = Jul-Sep yy             end → Sep 30 yy
        if "fy" in name:
            return {1: f"{y - 1:04d}-12-31", 2: f"{y:04d}-03-31",
                    3: f"{y:04d}-06-30", 4: f"{y:04d}-09-30"}[q]
        # Calendar-year quarter (older filenames)
        return {1: f"{y:04d}-03-31", 2: f"{y:04d}-06-30",
                3: f"{y:04d}-09-30", 4: f"{y:04d}-12-31"}[q]
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
    online = _s(row.get("online access"))
    hms_id = _s(
        row.get("hms record entry id# ")
        or row.get("hms record entry id#")
        or row.get("hms entry")
    )

    # Description: stitched from the surrounding columns since NDC sheets
    # don't carry an abstract.
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
        # No per-row URL in NDC lists — link back to the artifact + HMS id.
        "source_url": (f"{source_url}#hms-{hms_id}" if hms_id and source_url else source_url) or None,
    }


_DATE_RX = [
    re.compile(r"^(\d{4})-(\d{2})-(\d{2})"),
    re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})"),
    re.compile(r"^(\d{4})/(\d{1,2})/(\d{1,2})"),
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
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    return None


# ─── AARO parser (HTML detail page links) ─────────────────────────
def parse_aaro(group_cfg: dict, limit: int | None) -> list[Record]:
    out: list[Record] = []
    for hub in group_cfg["urls"]:
        html = fetch(hub)
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = urljoin(hub, a["href"])
            if not href.lower().endswith(".pdf"):
                continue
            title = (a.get_text(strip=True) or Path(href).stem).strip()
            out.append(
                Record(
                    title=title or "(untitled AARO release)",
                    agency=group_cfg["agency"],
                    unsealed_date="",  # AARO pages don't reliably expose dates inline
                    collection_id=group_cfg["collection_id_default"],
                    source_url=href,
                )
            )
            if limit and len(out) >= limit:
                return out
    return out


PARSERS = {
    "nara_ndc": parse_nara_ndc,
    "aaro": parse_aaro,
    # dow_uap intentionally absent until a verified source URL exists.
}


# ─── SQL emission ─────────────────────────────────────────────────
def emit_sql(group: str, records: list[Record]) -> Path:
    out_path = OUT_DIR / f"ingest_{group}.sql"
    # D1 wraps batches in its own transaction; explicit BEGIN/COMMIT errors out.
    with out_path.open("w", encoding="utf-8") as f:
        f.write(f"-- UNSEALED ingest — {group} — {len(records)} records\n")
        for r in records:
            f.write(
                "INSERT INTO records (title, agency, unsealed_date, collection_id, source_url, description, thumbnail_url) VALUES "
                f"({_q(r.title)}, {_q(r.agency)}, {_q(r.unsealed_date)}, {_q(r.collection_id)}, "
                f"{_q(r.source_url)}, {_q(r.description)}, {_q(r.thumbnail_url)});\n"
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
    args = ap.parse_args()

    cfg = json.loads(SOURCES_FILE.read_text("utf-8"))
    groups = [args.group] if args.group else [g for g in cfg if not g.startswith("_")]

    total = 0
    for g in groups:
        if g not in cfg:
            print(f"unknown group: {g}", file=sys.stderr)
            continue
        if g not in PARSERS:
            print(f"[{g}] no parser registered — skipping", file=sys.stderr)
            continue
        if not cfg[g].get("urls"):
            print(f"[{g}] no urls configured — skipping", file=sys.stderr)
            continue
        print(f"[{g}] parsing...", file=sys.stderr)
        recs = PARSERS[g](cfg[g], args.limit)
        print(f"[{g}] {len(recs)} records", file=sys.stderr)
        total += len(recs)
        if args.dry_run:
            for r in recs[:5]:
                print(json.dumps(asdict(r), indent=2))
            continue
        path = emit_sql(g, recs)
        print(f"[{g}] wrote {path.relative_to(ROOT)}", file=sys.stderr)

    print(f"total: {total} records", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
