// GET /api/search?q=<query>&source=<ia|ntrs|curated>&limit=<n>
//
// Federated search across:
//   • Internet Archive — National Security Archive collection (~2.4M docs,
//     functionally a public mirror of CIA/NSA declassified material)
//   • NASA NTRS — NASA Technical Reports Server
//   • Curated D1 seed — AARO + DoW + editorial picks
//
// Results are returned grouped by source so the UI can render explicit
// "From: <source>" sections (no fake unified ranking).

const TIMEOUT_MS = 4500;
const PER_SOURCE_LIMIT_DEFAULT = 12;

export const onRequestGet = async ({ request, env }) => {
  const url = new URL(request.url);
  const q = (url.searchParams.get('q') || '').trim();
  const filter = url.searchParams.get('source'); // null = all sources
  const includeSealed = url.searchParams.get('include_sealed') === '1';
  const limit = Math.min(
    parseInt(url.searchParams.get('limit') || String(PER_SOURCE_LIMIT_DEFAULT), 10),
    50,
  );

  if (!q) return json({ query: '', sources: [] });

  const all = [
    { id: 'ia',      run: () => fetchInternetArchive(q, limit) },
    { id: 'ntrs',    run: () => fetchNTRS(q, limit) },
    { id: 'curated', run: () => fetchCurated(q, limit, env, { includeSealed }) },
  ];
  const wanted = filter ? all.filter((s) => s.id === filter) : all;

  const settled = await Promise.allSettled(
    wanted.map(({ run }) => withTimeout(run(), TIMEOUT_MS)),
  );

  const sources = settled
    .map((r, i) => {
      if (r.status === 'fulfilled' && r.value) return r.value;
      return {
        id: wanted[i].id,
        name: SOURCE_LABEL[wanted[i].id],
        total: null,
        results: [],
        error: r.status === 'rejected' ? String(r.reason).slice(0, 200) : 'empty',
      };
    });

  return json({ query: q, sources });
};

const SOURCE_LABEL = {
  ia:      'INTERNET ARCHIVE — NATIONAL SECURITY ARCHIVE',
  ntrs:    'NASA NTRS — TECHNICAL REPORTS',
  curated: 'CURATED — AARO / DOW / EDITORIAL',
};

// ─── Internet Archive (NSA collection) ─────────────────────────────────
async function fetchInternetArchive(q, limit) {
  const params = new URLSearchParams();
  params.set('q', `collection:nationalsecurityarchive ${q}`);
  ['identifier', 'title', 'date', 'creator', 'description'].forEach((f) =>
    params.append('fl[]', f),
  );
  params.set('rows', String(limit));
  params.set('output', 'json');

  const r = await fetch(`https://archive.org/advancedsearch.php?${params}`, {
    headers: { 'user-agent': 'UNSEALED/0.1 (+federation)' },
    cf: { cacheTtl: 60, cacheEverything: true },
  });
  if (!r.ok) throw new Error(`ia ${r.status}`);
  const data = await r.json();
  const docs = data?.response?.docs || [];

  return {
    id: 'ia',
    name: SOURCE_LABEL.ia,
    total: data?.response?.numFound ?? null,
    results: docs.map((d) => ({
      id: `ia:${d.identifier}`,
      title: pickFirst(d.title) || d.identifier,
      agency: identifierToAgency(d.identifier),
      unsealed_date: pickFirst(d.date)?.slice(0, 10) || null,
      collection_id: 'National Security Archive',
      source_url: `https://archive.org/details/${encodeURIComponent(d.identifier)}`,
      description: pickFirst(d.description) || null,
      thumbnail_url: `https://archive.org/services/img/${encodeURIComponent(d.identifier)}`,
    })),
  };
}

// IA NSA collection IDs follow CIA-RDP* / FBI* / NSA* patterns. Quick label.
function identifierToAgency(id) {
  if (!id) return 'NSA';
  const u = String(id).toUpperCase();
  if (u.startsWith('CIA-RDP') || u.startsWith('CIA-')) return 'CIA';
  if (u.startsWith('FBI-')) return 'FBI';
  if (u.startsWith('NSA-')) return 'NSA';
  if (u.startsWith('DOD-') || u.startsWith('DOW-')) return 'DoW';
  if (u.startsWith('STATE-')) return 'STATE';
  return 'NSA';
}

// ─── NASA NTRS ─────────────────────────────────────────────────────────
async function fetchNTRS(q, limit) {
  const r = await fetch(
    `https://ntrs.nasa.gov/api/citations/search?q=${encodeURIComponent(q)}&size=${limit}`,
    {
      headers: { 'user-agent': 'UNSEALED/0.1 (+federation)' },
      cf: { cacheTtl: 60, cacheEverything: true },
    },
  );
  if (!r.ok) throw new Error(`ntrs ${r.status}`);
  const data = await r.json();
  const results = data?.results || [];

  return {
    id: 'ntrs',
    name: SOURCE_LABEL.ntrs,
    total: data?.stats?.total ?? null,
    results: results.map((d) => ({
      id: `ntrs:${d.id}`,
      title: d.title || `NTRS ${d.id}`,
      agency: 'NASA',
      unsealed_date: (d.distributionDate || d.submittedDate || '').slice(0, 10) || null,
      collection_id: d.center?.name || 'NTRS',
      source_url: `https://ntrs.nasa.gov/citations/${d.id}`,
      description: d.abstract || null,
      thumbnail_url: null,
    })),
  };
}

// ─── Curated (D1 FTS5) ─────────────────────────────────────────────────
async function fetchCurated(q, limit, env, { includeSealed = false } = {}) {
  const ftsQuery = toFtsQuery(q);
  if (!ftsQuery) {
    return { id: 'curated', name: SOURCE_LABEL.curated, total: 0, results: [] };
  }
  // is_sealed=1 records are NDC IOD-candidate entries — proposed for declass
  // but not actually released. Hidden by default; the UI exposes a toggle
  // that flips include_sealed=1.
  const sealedFilter = includeSealed ? '' : 'AND r.is_sealed = 0';
  const sql = `
    SELECT r.id, r.title, r.agency, r.unsealed_date, r.collection_id,
           r.source_url, r.description, r.thumbnail_url, r.is_sealed,
           bm25(records_fts, 3.0, 1.0, 0.5) AS rank
    FROM records_fts
    JOIN records r ON r.id = records_fts.rowid
    WHERE records_fts MATCH ?1 ${sealedFilter}
    ORDER BY rank
    LIMIT ?2
  `;
  const { results } = await env.DB.prepare(sql).bind(ftsQuery, limit).all();
  return {
    id: 'curated',
    name: SOURCE_LABEL.curated,
    total: results.length,
    results: results.map((r) => ({
      id: `curated:${r.id}`,
      title: r.title,
      agency: r.agency,
      unsealed_date: r.unsealed_date,
      collection_id: r.collection_id,
      source_url: r.source_url,
      description: r.description,
      thumbnail_url: r.thumbnail_url,
      is_sealed: r.is_sealed === 1,
    })),
  };
}

function toFtsQuery(raw) {
  const tokens = raw
    .split(/\s+/)
    .map((t) => t.replace(/["()*:^-]/g, ''))
    .filter((t) => t.length >= 2);
  if (tokens.length === 0) return null;
  return tokens
    .map((t, i) => (i === tokens.length - 1 ? `"${t}"*` : `"${t}"`))
    .join(' ');
}

// ─── Helpers ───────────────────────────────────────────────────────────
function pickFirst(v) {
  if (Array.isArray(v)) return v[0];
  return v ?? null;
}

function withTimeout(p, ms) {
  return Promise.race([
    p,
    new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), ms)),
  ]);
}

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'cache-control': 'no-store',
    },
  });
}
