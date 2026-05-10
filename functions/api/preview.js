// GET /api/preview?id=<record_id>
// Agentic on-demand retrieval: HEAD/GET the source URL, decide whether the
// PDF (or HTML detail page) is reachable, and return a small JSON payload
// the UI can use to render a "Page 1" preview area.
//
// Scope of the prototype: this does NOT render a PDF page-1 raster. That
// would require a PDF→image worker (pdfjs in a Worker), which is real work
// and a separate decision. For now, we:
//   - check reachability + content-type of the source URL
//   - if HTML, scrape the first <meta og:image> or first <img> as a preview
//   - if PDF, return { kind: 'pdf', url, bytes } so the client can show a
//     deep link + (eventually) hand off to a renderer
//
// Hardening: hard timeout, host allow-list, response size cap.

const ALLOWED_HOST_PATTERNS = [
  /\.archives\.gov$/i,
  /\.nara\.gov$/i,
  /\.cia\.gov$/i,
  /\.nasa\.gov$/i,
  /\.defense\.gov$/i,
  /\.aaro\.mil$/i,
];
const FETCH_TIMEOUT_MS = 8000;
const MAX_HTML_BYTES = 512 * 1024;

export const onRequestGet = async ({ request, env }) => {
  const url = new URL(request.url);
  const id = url.searchParams.get('id');
  if (!id) return json({ error: 'missing_id' }, 400);

  const row = await env.DB.prepare(
    'SELECT id, title, source_url, thumbnail_url FROM records WHERE id = ?1',
  )
    .bind(id)
    .first();
  if (!row) return json({ error: 'not_found' }, 404);

  let target;
  try {
    target = new URL(row.source_url);
  } catch {
    return json({ error: 'bad_source_url' }, 502);
  }
  if (!ALLOWED_HOST_PATTERNS.some((re) => re.test(target.hostname))) {
    return json({ kind: 'external', reachable: null, source_url: row.source_url });
  }

  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), FETCH_TIMEOUT_MS);
  try {
    const head = await fetch(target.toString(), {
      method: 'HEAD',
      signal: ctrl.signal,
      headers: { 'user-agent': 'UNSEALED/0.1 (+preview-agent)' },
    });
    const ct = head.headers.get('content-type') || '';
    const len = parseInt(head.headers.get('content-length') || '0', 10) || null;

    if (ct.includes('application/pdf')) {
      return json({
        kind: 'pdf',
        reachable: head.ok,
        source_url: row.source_url,
        bytes: len,
        page1_image: null, // future: pdf.js render in a separate Worker
      });
    }

    if (!ct.includes('text/html')) {
      return json({ kind: 'other', reachable: head.ok, source_url: row.source_url, content_type: ct });
    }

    // HTML detail page: pull first og:image / <img>.
    const get = await fetch(target.toString(), {
      signal: ctrl.signal,
      headers: { 'user-agent': 'UNSEALED/0.1 (+preview-agent)' },
    });
    const buf = await readCapped(get.body, MAX_HTML_BYTES);
    const html = new TextDecoder('utf-8', { fatal: false }).decode(buf);
    const ogImage = extractOgImage(html, target);
    const firstImg = ogImage || extractFirstImg(html, target);
    return json({
      kind: 'html',
      reachable: get.ok,
      source_url: row.source_url,
      preview_image: firstImg,
    });
  } catch (err) {
    return json({ kind: 'unreachable', reachable: false, error: String(err) });
  } finally {
    clearTimeout(timer);
  }
};

async function readCapped(stream, max) {
  const reader = stream.getReader();
  const chunks = [];
  let total = 0;
  while (total < max) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value);
    total += value.byteLength;
  }
  reader.cancel().catch(() => {});
  const out = new Uint8Array(Math.min(total, max));
  let off = 0;
  for (const c of chunks) {
    if (off + c.byteLength > max) {
      out.set(c.subarray(0, max - off), off);
      break;
    }
    out.set(c, off);
    off += c.byteLength;
  }
  return out;
}

function extractOgImage(html, base) {
  const m = html.match(/<meta[^>]+property=["']og:image["'][^>]+content=["']([^"']+)["']/i);
  return m ? resolve(m[1], base) : null;
}
function extractFirstImg(html, base) {
  const m = html.match(/<img[^>]+src=["']([^"']+)["']/i);
  return m ? resolve(m[1], base) : null;
}
function resolve(href, base) {
  try {
    return new URL(href, base).toString();
  } catch {
    return null;
  }
}
function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json; charset=utf-8' },
  });
}
