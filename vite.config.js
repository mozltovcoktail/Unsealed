import { defineConfig } from 'vite';

// Port 5184 — 5183 was taken by LiveyCammy. Update ~/.claude/CLAUDE.md registry.
export default defineConfig({
  server: {
    port: 5184,
    strictPort: true,
    proxy: {
      // Forward API calls to wrangler pages dev (run separately on :8788)
      // during local dev. In prod, /api/* is served by the same origin.
      '/api': {
        target: 'http://127.0.0.1:8788',
        changeOrigin: true,
      },
    },
  },
  build: {
    target: 'es2022',
    cssCodeSplit: false,
  },
});
