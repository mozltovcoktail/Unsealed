// GET /api/thumb?id=<record_id>
// Same-origin proxy for record thumbnails — sidesteps hot-link breakage,
// lets us cache at the edge, and serves a placeholder SVG on miss/error.
//
// Allow-list of host patterns is intentional: only proxy from .gov / known
// archive CDNs, never arbitrary URLs.

const ALLOWED_HOST_PATTERNS = [
  /\.archives\.gov$/i,
  /\.nara\.gov$/i,
  /\.cia\.gov$/i,
  /\.nasa\.gov$/i,
  /\.defense\.gov$/i,
  /\.aaro\.mil$/i,
];

export const onRequestGet = async ({ request, env }) => {
  const url = new URL(request.url);
  const id = url.searchParams.get('id');
  if (!id) return placeholder();

  const row = await env.DB.prepare('SELECT thumbnail_url FROM records WHERE id = ?1')
    .bind(id)
    .first();
  const target = row?.thumbnail_url;
  if (!target) return placeholder();

  let targetUrl;
  try {
    targetUrl = new URL(target);
  } catch {
    return placeholder();
  }
  if (!ALLOWED_HOST_PATTERNS.some((re) => re.test(targetUrl.hostname))) {
    return placeholder();
  }

  // Edge cache via the Cache API.
  const cache = caches.default;
  const cacheKey = new Request(`https://unsealed.cache/thumb/${id}`, request);
  const cached = await cache.match(cacheKey);
  if (cached) return cached;

  try {
    const upstream = await fetch(targetUrl.toString(), {
      cf: { cacheTtl: 86400, cacheEverything: true },
      headers: { 'user-agent': 'UNSEALED/0.1 (+thumb-proxy)' },
    });
    if (!upstream.ok || !upstream.headers.get('content-type')?.startsWith('image/')) {
      return placeholder();
    }
    const resp = new Response(upstream.body, {
      headers: {
        'content-type': upstream.headers.get('content-type') || 'image/jpeg',
        'cache-control': 'public, max-age=86400, s-maxage=604800',
      },
    });
    await cache.put(cacheKey, resp.clone());
    return resp;
  } catch {
    return placeholder();
  }
};

// "Classified Folder" placeholder — pure SVG, brutalist, no fills.
function placeholder() {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120" width="120" height="120">
  <rect width="120" height="120" fill="#fff"/>
  <rect x="14" y="28" width="92" height="74" fill="none" stroke="#000" stroke-width="2"/>
  <rect x="14" y="22" width="44" height="10" fill="#000"/>
  <rect x="22" y="44" width="76" height="6" fill="#000"/>
  <rect x="22" y="56" width="60" height="6" fill="#000"/>
  <rect x="22" y="68" width="68" height="6" fill="#000"/>
  <text x="60" y="92" font-family="ui-monospace,monospace" font-size="9"
        text-anchor="middle" fill="#000" letter-spacing="2">CLASSIFIED</text>
</svg>`;
  return new Response(svg, {
    headers: {
      'content-type': 'image/svg+xml; charset=utf-8',
      'cache-control': 'public, max-age=86400',
    },
  });
}
