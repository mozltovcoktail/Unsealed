// airpiehi.com/unsealed/* Worker.
//
// Mounts the unsealed.pages.dev app under airpiehi.com/unsealed/*.
// Pattern mirrors cammy-proxy: strip the /unsealed prefix and re-fetch
// against the Pages origin, setting Host so Pages routes correctly.

export default {
  async fetch(request) {
    const url = new URL(request.url);

    if (url.pathname === '/unsealed') {
      return Response.redirect(url.origin + '/unsealed/' + url.search, 301);
    }

    const stripped = url.pathname.replace(/^\/unsealed\//, '/');
    const target = new URL(stripped + url.search, 'https://unsealed.pages.dev');
    const proxyReq = new Request(target, request);
    proxyReq.headers.set('Host', 'unsealed.pages.dev');
    return fetch(proxyReq);
  },
};
