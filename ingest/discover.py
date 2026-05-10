#!/usr/bin/env python3
"""
UNSEALED — Layer 1 source auto-discovery.

Two probes, both restricted to a strict `.gov` / `.mil` (+ explicit allow-list)
trust boundary:

  1. RSS / Atom feeds from agencies that publish them
     (NARA news, AARO press releases, etc.)
  2. Hub-page re-scan: visit pages already trusted in sources.json and
     extract any linked URLs that look like new declassification artifacts
     (.xlsx / .pdf / .csv / detail HTML) and have not been seen before.

Output: ingest/discovered.json — list of candidate sources with provenance.
A separate workflow promotes these into ingest/sources.json automatically
(domain-trust check) and opens a labeled PR.

Usage:
  python3 ingest/discover.py            # write discovered.json
  python3 ingest/discover.py --dry-run  # print to stdout

Dependencies: requests, beautifulsoup4 (already in ingester)
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urljoin, urlparse

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    sys.stderr.write(
        "Missing deps. Run:  pip3 install requests beautifulsoup4\n"
    )
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
SOURCES_FILE = ROOT / "ingest" / "sources.json"
DISCOVERED_FILE = ROOT / "ingest" / "discovered.json"
SEEN_FILE = ROOT / "ingest" / "discovered_seen.json"

USER_AGENT = "UNSEALED-discovery/0.1 (+contact: aaron)"
TIMEOUT = 30

# Trusted top-level domains. Anything outside this list is *never* auto-promoted.
TRUSTED_TLDS = (".gov", ".mil")
# Explicitly trusted non-.gov archives (curated, narrow). Add with care.
TRUSTED_HOSTS = {
    "nsarchive.gwu.edu",       # National Security Archive (academic)
    "governmentattic.org",     # Long-running FOIA-document archive
}

# Keywords that promote a candidate URL to "interesting".
INTEREST_RX = re.compile(
    r"(declassif|foia|release[-_ ]list|unseal|crest|mdr|cold[-_ ]war|"
    r"jfk|uap|ufo|aaro|catalog\.archives|reading[-_ ]?room)",
    re.I,
)

# RSS/Atom feeds to poll. Confine strictly to .gov/.mil.
FEEDS = [
    {
        "name": "archives.gov news",
        "url": "https://www.archives.gov/press/press-releases/feed",
    },
    {
        "name": "archives.gov news index",
        "url": "https://www.archives.gov/news/feed",
    },
    {
        "name": "AARO news",
        "url": "https://www.aaro.mil/DesktopModules/ArticleCS/RSS.ashx?ContentType=1&Site=1187&max=25",
    },
    # CIA press releases, FBI Vault — extend over time.
]

NOW = _dt.datetime.utcnow().isoformat() + "Z"


def fetch(url: str) -> str:
    r = requests.get(url, headers={"user-agent": USER_AGENT}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.text


def is_trusted(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    if not host:
        return False
    if host in TRUSTED_HOSTS:
        return True
    return any(host.endswith(tld) for tld in TRUSTED_TLDS)


def is_artifact(url: str) -> bool:
    u = url.lower().split("?", 1)[0]
    return u.endswith((".xlsx", ".xls", ".csv", ".pdf"))


def looks_interesting(url: str, title: str = "") -> bool:
    return bool(INTEREST_RX.search(url) or (title and INTEREST_RX.search(title)))


# ─── Probe 1: RSS / Atom feeds ─────────────────────────────────────
def probe_feeds() -> list[dict]:
    out: list[dict] = []
    for feed in FEEDS:
        try:
            xml = fetch(feed["url"])
        except Exception as e:
            print(f"  [feed] skip {feed['name']}: {e}", file=sys.stderr)
            continue
        try:
            root = ET.fromstring(xml)
        except ET.ParseError as e:
            print(f"  [feed] parse fail {feed['name']}: {e}", file=sys.stderr)
            continue

        # Handle both RSS 2.0 (<channel><item>) and Atom (<feed><entry>).
        items = root.findall(".//item")
        if not items:
            ns = {"a": "http://www.w3.org/2005/Atom"}
            items = root.findall(".//a:entry", ns)
            link_attr = "href"
            link_xpath = "a:link"
        else:
            link_attr = None
            link_xpath = "link"

        for it in items:
            link_el = it.find(link_xpath, {"a": "http://www.w3.org/2005/Atom"}) if "a:" in link_xpath else it.find(link_xpath)
            if link_el is None:
                continue
            url = (link_el.get(link_attr) if link_attr else (link_el.text or "")).strip()
            if not url or not is_trusted(url):
                continue
            title_el = it.find("title") or it.find("{http://www.w3.org/2005/Atom}title")
            title = (title_el.text or "").strip() if title_el is not None else ""
            if not looks_interesting(url, title):
                continue
            out.append({
                "url": url,
                "title": title,
                "found_via": f"rss:{feed['name']}",
                "found_at": NOW,
            })
    return out


# ─── Probe 2: re-scan trusted hub pages for new outbound links ─────
def probe_hubs() -> list[dict]:
    cfg = json.loads(SOURCES_FILE.read_text("utf-8"))
    known: set[str] = set()
    hubs: list[tuple[str, str]] = []  # (group, url)
    for group, body in cfg.items():
        if group.startswith("_") or not isinstance(body, dict):
            continue
        for u in body.get("urls", []) or []:
            known.add(u)
            hubs.append((group, u))

    out: list[dict] = []
    for group, hub in hubs:
        try:
            html = fetch(hub)
        except Exception as e:
            print(f"  [hub] skip {hub}: {e}", file=sys.stderr)
            continue
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = urljoin(hub, a["href"]).split("#", 1)[0]
            if href in known:
                continue
            if not is_trusted(href):
                continue
            text = a.get_text(strip=True) or ""
            if not (is_artifact(href) or looks_interesting(href, text)):
                continue
            out.append({
                "url": href,
                "title": text[:200],
                "found_via": f"hub-diff:{group}",
                "found_at": NOW,
            })
            known.add(href)
    return out


def load_seen() -> set[str]:
    if SEEN_FILE.exists():
        try:
            return set(json.loads(SEEN_FILE.read_text("utf-8")))
        except Exception:
            pass
    return set()


def save_seen(urls: set[str]) -> None:
    SEEN_FILE.write_text(json.dumps(sorted(urls), indent=2), "utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    seen = load_seen()
    candidates = probe_feeds() + probe_hubs()
    # Dedup by URL, keep first source attribution.
    by_url: dict[str, dict] = {}
    for c in candidates:
        by_url.setdefault(c["url"], c)
    fresh = [c for c in by_url.values() if c["url"] not in seen]

    print(
        f"discovery: {len(by_url)} total candidates, {len(fresh)} new since last run",
        file=sys.stderr,
    )

    if args.dry_run:
        print(json.dumps(fresh, indent=2))
        return 0

    DISCOVERED_FILE.write_text(json.dumps(fresh, indent=2, sort_keys=True), "utf-8")
    save_seen(seen | set(by_url))
    print(f"wrote {DISCOVERED_FILE.relative_to(ROOT)} ({len(fresh)} new)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
