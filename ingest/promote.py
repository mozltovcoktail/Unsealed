#!/usr/bin/env python3
"""
Promote entries from ingest/discovered.json into ingest/sources.json.

Trust rule (DECISION #3 in repo history): auto-add ALL `.gov` / `.mil` URLs.
Anything outside the allow-list is left in discovered.json with status='rejected'.

The CI workflow runs:
    python3 ingest/promote.py
    git add ingest/sources.json ingest/discovered.json
    # opens a labeled PR if there are changes

Each promotion is recorded so the resulting commit / PR is fully auditable.
"""
from __future__ import annotations

import datetime as _dt
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
SOURCES_FILE = ROOT / "ingest" / "sources.json"
DISCOVERED_FILE = ROOT / "ingest" / "discovered.json"
PROMOTION_LOG = ROOT / "ingest" / "promotion_log.jsonl"

TRUSTED_TLDS = (".gov", ".mil")
TRUSTED_HOSTS = {"nsarchive.gwu.edu", "governmentattic.org"}


def host(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def is_trusted(url: str) -> bool:
    h = host(url)
    return bool(h) and (h in TRUSTED_HOSTS or any(h.endswith(t) for t in TRUSTED_TLDS))


# Map a discovered URL to a source group. Heuristic: by host.
def group_for(url: str) -> str:
    h = host(url)
    if "archives.gov" in h or "catalog.archives.gov" in h:
        return "nara_ndc"
    if "aaro.mil" in h:
        return "aaro"
    # Default landing zone for new trusted domains: a per-host group named
    # discovered_<host-with-dashes>. Schema-compatible.
    safe = h.replace(".", "_") if h else "unknown"
    return f"discovered_{safe}"


def main() -> int:
    if not DISCOVERED_FILE.exists():
        print("no discovered.json — nothing to promote", file=sys.stderr)
        return 0
    discovered = json.loads(DISCOVERED_FILE.read_text("utf-8"))
    if not discovered:
        print("discovered.json is empty", file=sys.stderr)
        return 0

    cfg = json.loads(SOURCES_FILE.read_text("utf-8"))
    promoted: list[dict] = []
    rejected: list[dict] = []

    for cand in discovered:
        url = cand.get("url", "")
        if not is_trusted(url):
            cand["status"] = "rejected"
            cand["reason"] = "outside .gov/.mil allow-list"
            rejected.append(cand)
            continue

        g = group_for(url)
        body = cfg.setdefault(
            g,
            {
                "agency": "AUTO",
                "collection_id_default": f"Auto-discovered ({host(url)})",
                "urls": [],
                "_auto": True,
            },
        )
        urls = body.setdefault("urls", [])
        if url in urls:
            cand["status"] = "already-known"
            continue
        urls.append(url)
        cand["status"] = "promoted"
        cand["promoted_at"] = _dt.datetime.utcnow().isoformat() + "Z"
        cand["promoted_into"] = g
        promoted.append(cand)

    if promoted:
        SOURCES_FILE.write_text(json.dumps(cfg, indent=2, sort_keys=False) + "\n", "utf-8")
        print(f"promoted {len(promoted)} URLs into {SOURCES_FILE.relative_to(ROOT)}", file=sys.stderr)
        with PROMOTION_LOG.open("a", encoding="utf-8") as f:
            for p in promoted:
                f.write(json.dumps(p) + "\n")

    if rejected:
        print(f"rejected {len(rejected)} URLs (outside trust boundary)", file=sys.stderr)

    # Clear the discovered file — successful runs commit the resulting sources.json change.
    # Keep rejections so they're visible in the PR for human review.
    DISCOVERED_FILE.write_text(json.dumps(rejected, indent=2), "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
