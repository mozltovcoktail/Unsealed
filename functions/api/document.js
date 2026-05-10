// GET /api/document?id=<source>:<identifier>
//
// Resolves a record to in-app viewing info:
//   {
//     id, title, source, source_url,
//     embeddable: bool,                 // true → safe to <iframe>
//     frame_url: string,                // url to put in the iframe (may differ from source_url)
//     reason: 'iframe-ok' | 'x-frame-options' | 'csp' | 'unreachable' | 'unknown',
//   }
//
// IA records get a special-cased frame URL (`archive.org/embed/<id>`) — IA's
// own embed reader is iframe-friendly by design and shows native page scans
// + OCR text in the publisher's UI.
//
// For everything else we HEAD the source URL and parse blocking headers.

const FETCH_TIMEOUT_MS = 5000;

export const onRequestGet = async ({ request, env }) => {
  const url = new URL(request.url);
  const id = url.searchParams.get('id') || '';
  if (!id) return json({ error: 'missing_id' }, 400);

  const [source, ...rest] = id.split(':');
  const identifier = rest.join(':');

  // Source-specific shortcuts.
  if (source === 'ia' && identifier) {
    // Use IA's metadata API to find a directly-frameable PDF. The browser's
    // native PDF viewer renders inside the iframe — better UX than IA's
    // BookReader (which fails to initialize for many NSA-collection items).
    const meta = await fetchIAMetadata(identifier);
    const pdfFile = meta?.files?.find((f) => f.format === 'Image Container PDF' || f.format === 'Text PDF' || /\.pdf$/i.test(f.name || ''));
    if (pdfFile?.name) {
      // Path-based proxy + self-hosted pdf.js viewer so PDFs render
      // identically across browsers (incl. iOS Safari + WKWebView).
      // Path-based avoids the double-encoding that breaks pdf.js's
      // ?file= parameter when it nests another query string.
      const proxyPath = `/api/pdf-ia/${encodeURIComponent(identifier)}`;
      const viewerUrl = `/pdfjs/web/viewer.html?file=${encodeURIComponent(proxyPath)}`;
      return json({
        id,
        source: 'ia',
        title: meta?.metadata?.title || null,
        description: meta?.metadata?.description || null,
        embeddable: true,
        frame_url: viewerUrl,
        source_url: `https://archive.org/details/${encodeURIComponent(identifier)}`,
        reason: 'pdf',
      });
    }
    // No PDF available — embed reader as last resort, but mark embeddable false
    // if there are zero viewable files at all (metadata-only items render blank).
    const hasViewable = meta?.files?.some((f) =>
      ['Image Container PDF', 'Text PDF', 'Single Page Processed JP2 ZIP', 'DjVuTXT'].includes(f.format)
    );
    return json({
      id,
      source: 'ia',
      title: meta?.metadata?.title || null,
      description: meta?.metadata?.description || null,
      embeddable: hasViewable,
      frame_url: hasViewable
        ? `https://archive.org/embed/${encodeURIComponent(identifier)}`
        : null,
      source_url: `https://archive.org/details/${encodeURIComponent(identifier)}`,
      reason: hasViewable ? 'iframe-ok' : 'no-viewable-content',
    });
  }

  if (source === 'curated') {
    const row = await env.DB.prepare(
      'SELECT id, title, source_url, agency, unsealed_date, collection_id, description, is_sealed FROM records WHERE id = ?1',
    ).bind(identifier).first();
    if (!row) return json({ error: 'not_found' }, 404);
    const probe = await probeFrameability(row.source_url);
    return json({
      id,
      source: 'curated',
      title: row.title,
      agency: row.agency,
      unsealed_date: row.unsealed_date,
      collection_id: row.collection_id,
      description: row.description,
      source_url: row.source_url,
      frame_url: row.source_url,
      embeddable: probe.embeddable,
      reason: probe.reason,
      is_sealed: row.is_sealed === 1,
    });
  }

  if (source === 'ntrs') {
    const sourceUrl = `https://ntrs.nasa.gov/citations/${encodeURIComponent(identifier)}`;
    const probe = await probeFrameability(sourceUrl);
    return json({
      id,
      source: 'ntrs',
      source_url: sourceUrl,
      frame_url: sourceUrl,
      embeddable: probe.embeddable, // expected false — NTRS sets X-Frame-Options
      reason: probe.reason,
    });
  }

  // Generic fallback — id is itself a URL.
  const probe = await probeFrameability(identifier);
  return json({
    id,
    source,
    source_url: identifier,
    frame_url: identifier,
    embeddable: probe.embeddable,
    reason: probe.reason,
  });
};

// HEAD the URL and parse iframe-blocking headers.
async function probeFrameability(target) {
  let url;
  try { url = new URL(target); } catch { return { embeddable: false, reason: 'unreachable' }; }

  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), FETCH_TIMEOUT_MS);
  try {
    const r = await fetch(url.toString(), {
      method: 'HEAD',
      signal: ctrl.signal,
      headers: { 'user-agent': 'UNSEALED/0.1 (+frame-probe)' },
      redirect: 'follow',
    });
    if (!r.ok) return { embeddable: false, reason: 'unreachable' };

    const xfo = (r.headers.get('x-frame-options') || '').toLowerCase();
    if (xfo.includes('deny') || xfo.includes('sameorigin')) {
      return { embeddable: false, reason: 'x-frame-options' };
    }

    const csp = r.headers.get('content-security-policy') || '';
    const m = csp.toLowerCase().match(/frame-ancestors\s+([^;]+)/);
    if (m) {
      const directive = m[1].trim();
      if (directive === "'none'" || directive.includes("'self'")) {
        return { embeddable: false, reason: 'csp' };
      }
    }

    return { embeddable: true, reason: 'iframe-ok' };
  } catch {
    return { embeddable: false, reason: 'unreachable' };
  } finally {
    clearTimeout(timer);
  }
}

async function fetchIAMetadata(identifier) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), FETCH_TIMEOUT_MS);
  try {
    const r = await fetch(
      `https://archive.org/metadata/${encodeURIComponent(identifier)}`,
      {
        signal: ctrl.signal,
        headers: { 'user-agent': 'UNSEALED/0.1 (+ia-meta)' },
        cf: { cacheTtl: 600, cacheEverything: true },
      },
    );
    if (!r.ok) return null;
    return await r.json();
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json; charset=utf-8' },
  });
}
