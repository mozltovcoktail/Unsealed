# Outreach email drafts — 2026-05-11

Two emails to send from Aaron's own address. Both regard apparent
inconsistencies between robots.txt and the operator's clear public
intent to make material programmatically available.

---

## 1. State Dept (history.state.gov) — FRUS bulk-download clarification

**To:** webmaster@state.gov (also cc: history@state.gov if you find a
contact for the Office of the Historian's web team)

**Subject:** robots.txt clarification — static.history.state.gov bulk FRUS EPUBs

Hello,

I'm building UNSEALED (https://github.com/mozltovcoktail/Unsealed), an
open-source search engine over declassified U.S. government records.
I'd like to index the FRUS volumes you publish, and I have a quick
question about your crawl policy.

`history.state.gov/historicaldocuments/ebooks` publishes direct links
to bulk EPUB downloads at
`static.history.state.gov/frus/<vol_id>/ebook/<vol_id>.epub` — the
intended pattern for readers who want full FRUS volumes.

The parent domain's robots.txt (`history.state.gov/robots.txt`) is
permissive with a 20-second crawl-delay (which I honor). But the
static subdomain's robots.txt
(`static.history.state.gov/robots.txt`) reads:

```
User-agent: Twitterbot
Disallow:

User-agent: *
Disallow: /
```

This looks like an unintended default — bulk EPUB downloads from a
static CDN, blanket-disallowed to all bots except Twitterbot.

Two questions:

1. **Is the static subdomain disallow intentional?** If so, I'll
   respect it and look for an alternative path (e.g., NARA Catalog
   API, FOIA request).
2. **If unintentional**, would you be willing to update
   `static.history.state.gov/robots.txt` to either match the parent
   domain's policy or explicitly allow EPUB downloads?

For context on my politeness: I download one EPUB per 20 seconds
(matching the parent domain's `Crawl-delay`), identify my bot via the
`From:` header pointing to the public GitHub repo, and cache
aggressively so each volume is fetched once total.

In the meantime I've removed the FRUS records I previously indexed
from my database while we sort this out.

Thank you,
Aaron Price
aaronmorrisprice@gmail.com
https://github.com/mozltovcoktail/Unsealed

---

## 2. NARA Catalog API — robots.txt vs. authenticated API access

**To:** Catalog_API@nara.gov (the address you've already emailed for
the API key request — likely the same team)

**Subject:** robots.txt clarification — Catalog API vs. /robots.txt

Hello,

Following up on my earlier request for a read-only Catalog API key
(sent 2026-05-10): one quick policy question before I switch the API
on once the key arrives.

`catalog.archives.gov/robots.txt` reads:

```
User-agent: *
Disallow: /
```

I read this as targeting web crawlers indexing the search UI, rather
than authenticated programmatic use of the v2 API. But I want to ask
explicitly rather than assume:

- Once I have the API key, is using the v2 REST endpoints
  (`/api/v2/records/search`, etc.) considered consistent with your
  robots.txt? Or does the blanket `Disallow: /` apply to the API too?

I'd plan to keep my volume well under the free tier (~100 queries/month
across ~8 declassification-themed terms, weekly), with caching so the
same query isn't re-issued unnecessarily.

If the API is exempt from the robots.txt rule, I'll proceed once the
key arrives. If not, I'll find another path to NARA-held material.

Thank you,
Aaron Price
aaronmorrisprice@gmail.com
https://github.com/mozltovcoktail/Unsealed
