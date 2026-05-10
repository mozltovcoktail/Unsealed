// GET /api/pdf-ia/<identifier>
//
// Path-based PDF proxy for Internet Archive items. Path-based (not ?url=)
// because pdf.js's viewer.html `?file=` parameter doesn't URL-decode its
// value, which made nested-query-string proxies render garbage.
//
// Resolves <identifier> → IA's metadata API → primary PDF file → streams
// it back through our edge with permissive CORS so pdf.js can fetch it.

const FETCH_TIMEOUT_MS = 10000;
const BROWSER_UA =
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 ' +
  '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36';

export const onRequestGet = async ({ params }) => {
  return handle(params, 'GET');
};
export const onRequestHead = async ({ params }) => {
  return handle(params, 'HEAD');
};

async function handle(params, method) {
  const identifier = sanitize(params?.identifier);
  if (!identifier) return error('bad_identifier', 400);

  // Look up the canonical PDF filename via IA's metadata API.
  const meta = await fetchJson(
    `https://archive.org/metadata/${encodeURIComponent(identifier)}`,
  );
  const pdfFile = meta?.files?.find(
    (f) =>
      f.format === 'Image Container PDF' ||
      f.format === 'Text PDF' ||
      /\.pdf$/i.test(f.name || ''),
  );
  if (!pdfFile?.name) return error('no_pdf', 404);

  const upstreamUrl = `https://archive.org/download/${encodeURIComponent(identifier)}/${encodeURIComponent(pdfFile.name)}`;

  // Retry once on transient upstream 5xx (IA bot-blocks bursts).
  let upstreamResp;
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      upstreamResp = await fetch(upstreamUrl, {
        method: 'GET',
        headers: { 'user-agent': BROWSER_UA, accept: 'application/pdf,*/*' },
        redirect: 'follow',
        cf: { cacheTtl: 3600, cacheEverything: true },
      });
    } catch (e) {
      if (attempt === 1) return error('upstream_fetch_failed', 502, String(e));
      continue;
    }
    if (upstreamResp.ok) break;
    if (attempt === 1) {
      return error('upstream_status', 502, String(upstreamResp.status));
    }
    await new Promise((r) => setTimeout(r, 800));
  }

  const ct = upstreamResp.headers.get('content-type') || '';
  if (/text\/html/i.test(ct)) {
    return error('not_a_pdf', 415, ct);
  }

  const out = new Headers();
  out.set('content-type', 'application/pdf');
  for (const k of ['content-length', 'last-modified', 'etag']) {
    const v = upstreamResp.headers.get(k);
    if (v) out.set(k, v);
  }
  out.set('accept-ranges', 'none');
  out.set('access-control-allow-origin', '*');
  out.set('cache-control', 'public, max-age=3600');

  return new Response(method === 'HEAD' ? null : upstreamResp.body, {
    status: 200,
    headers: out,
  });
}

// IA identifiers are alphanumerics + dot/dash/underscore. Anything else is
// rejected — protects against path traversal in the metadata API URL.
function sanitize(s) {
  if (!s || typeof s !== 'string') return null;
  if (!/^[A-Za-z0-9._-]+$/.test(s)) return null;
  return s;
}

async function fetchJson(url) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), FETCH_TIMEOUT_MS);
  try {
    const r = await fetch(url, {
      signal: ctrl.signal,
      headers: { 'user-agent': BROWSER_UA },
      cf: { cacheTtl: 600, cacheEverything: true },
    });
    if (!r.ok) return null;
    return await r.json();
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

function error(code, status, detail) {
  return new Response(
    JSON.stringify({ error: code, detail: detail || null }),
    {
      status,
      headers: {
        'content-type': 'application/json',
        'access-control-allow-origin': '*',
      },
    },
  );
}
