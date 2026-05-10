import './style.css';

// Inline classified-folder SVG fallback when /api/thumb 404s in dev.
const CLASSIFIED_FOLDER_SVG =
  'data:image/svg+xml;utf8,' +
  encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120">` +
    `<rect width="120" height="120" fill="#fff"/>` +
    `<rect x="14" y="28" width="92" height="74" fill="none" stroke="#000" stroke-width="2"/>` +
    `<rect x="14" y="22" width="44" height="10" fill="#000"/>` +
    `<rect x="22" y="44" width="76" height="6" fill="#000"/>` +
    `<rect x="22" y="56" width="60" height="6" fill="#000"/>` +
    `<rect x="22" y="68" width="68" height="6" fill="#000"/>` +
    `<text x="60" y="92" font-family="ui-monospace,monospace" font-size="9" ` +
    `text-anchor="middle" fill="#000" letter-spacing="2">CLASSIFIED</text></svg>`,
  );

const $ = (sel) => document.querySelector(sel);
const qInput = $('#q');
const resultsEl = $('#results');
const resultsHint = $('#resultsHint');
const sourcesEl = $('#agencies'); // toggle row, repurposed for source filters
const recordCountEl = $('#recordCount');

const state = {
  query: '',
  sourceFilter: null, // null = all sources
  sources: [],        // [{id,label,sublabel}, ...]
  responseSources: [],
};

// ─── Search-as-you-type ────────────────────────────────────────────────
let searchTimer = null;
let inflightCtrl = null;

qInput.addEventListener('input', (e) => {
  state.query = e.target.value.trim();
  if (searchTimer) clearTimeout(searchTimer);
  searchTimer = setTimeout(runSearch, 120);
});

async function runSearch() {
  if (inflightCtrl) inflightCtrl.abort();
  inflightCtrl = new AbortController();

  if (!state.query) {
    state.responseSources = [];
    renderResults();
    return;
  }

  const params = new URLSearchParams({ q: state.query, limit: '12' });
  if (state.sourceFilter) params.set('source', state.sourceFilter);

  try {
    const r = await fetch(`/api/search?${params}`, { signal: inflightCtrl.signal });
    if (!r.ok) throw new Error(`status ${r.status}`);
    const data = await r.json();
    state.responseSources = data.sources || [];
    renderResults();
  } catch (err) {
    if (err.name === 'AbortError') return;
    resultsHint.textContent = '▮▮▮ FEDERATION ERROR ▮▮▮';
    resultsEl.replaceChildren(resultsHint);
  }
}

// ─── Rendering ─────────────────────────────────────────────────────────
function renderResults() {
  if (!state.query) {
    resultsHint.textContent = '▮▮▮ AWAITING QUERY ▮▮▮';
    resultsEl.replaceChildren(resultsHint);
    recordCountEl.textContent = '— RECORDS';
    return;
  }

  const totalShown = state.responseSources.reduce((n, s) => n + (s.results?.length || 0), 0);
  if (totalShown === 0) {
    resultsHint.textContent = '▮▮▮ NO MATCH ON RECORD ▮▮▮';
    resultsEl.replaceChildren(resultsHint);
    recordCountEl.textContent = '0 RECORDS';
    return;
  }

  const totalAcrossSources = state.responseSources.reduce(
    (n, s) => n + (typeof s.total === 'number' ? s.total : 0),
    0,
  );
  recordCountEl.textContent = totalAcrossSources
    ? `${formatCount(totalAcrossSources)} RECORDS`
    : `${totalShown} RECORDS`;

  const frag = document.createDocumentFragment();
  for (const src of state.responseSources) {
    if (!src.results || src.results.length === 0) continue;
    frag.appendChild(buildSourceSection(src));
  }
  resultsEl.replaceChildren(frag);
  observeReveals();
}

function buildSourceSection(src) {
  const sec = document.createElement('section');
  sec.className = 'source';
  sec.dataset.source = src.id;

  const head = document.createElement('header');
  head.className = 'source__head';
  const name = document.createElement('span');
  name.className = 'source__name';
  name.textContent = src.name || src.id;
  const count = document.createElement('span');
  count.className = 'source__count';
  count.textContent = src.total != null
    ? `${formatCount(src.total)} TOTAL · SHOWING ${src.results.length}`
    : `SHOWING ${src.results.length}`;
  head.append(name, count);

  const list = document.createElement('div');
  list.className = 'source__list';
  for (const rec of src.results) list.appendChild(buildRecord(rec));

  sec.append(head, list);
  return sec;
}

function buildRecord(rec) {
  const el = document.createElement('article');
  el.className = 'record';
  el.dataset.id = rec.id;

  const thumbWrap = document.createElement('div');
  thumbWrap.className = 'record__thumb-wrap';
  const img = document.createElement('img');
  img.alt = '';
  img.loading = 'lazy';
  // For federated results, hot-link directly; curated:* falls back to /api/thumb.
  img.src = rec.thumbnail_url || `/api/thumb?id=${encodeURIComponent(stripPrefix(rec.id))}`;
  img.addEventListener('error', () => { img.src = CLASSIFIED_FOLDER_SVG; }, { once: true });
  thumbWrap.appendChild(img);

  const body = document.createElement('div');
  body.className = 'record__body';

  const meta = document.createElement('div');
  meta.className = 'record__meta';
  // Filter null/undefined — Element.append(null) stringifies to "null".
  const metaPills = [
    span(rec.agency || 'UNKNOWN'),
    span(rec.unsealed_date),
    span(rec.collection_id),
  ].filter(Boolean);
  meta.append(...metaPills);

  const title = document.createElement('h2');
  title.className = 'record__title';
  title.textContent = rec.title;

  const desc = document.createElement('p');
  desc.className = 'record__desc';
  desc.textContent = rec.description || '— NO ABSTRACT ON FILE —';

  const src = document.createElement('a');
  src.className = 'record__src';
  src.href = rec.source_url;
  src.target = '_blank';
  src.rel = 'noopener noreferrer';
  src.textContent = '→ VIEW SOURCE';

  body.append(meta, title, desc, src);
  el.append(thumbWrap, body);

  // Whole-card click → open in-app document overlay. Shift/cmd-click bypasses
  // (browser default opens the link in a new tab/window).
  el.addEventListener('click', (e) => {
    if (e.target.closest('a')) return; // explicit "→ VIEW SOURCE" still works
    if (e.metaKey || e.ctrlKey || e.shiftKey) return;
    e.preventDefault();
    openDocument(rec);
  });

  if (matchMedia('(hover: hover) and (pointer: fine)').matches) {
    title.addEventListener('click', (e) => {
      // On desktop, separate the re-classify toggle from open-document.
      if (e.detail === 2) {
        e.stopPropagation();
        el.classList.toggle('is-reclassified');
      }
    });
  }
  return el;
}

function stripPrefix(id) {
  const i = String(id).indexOf(':');
  return i === -1 ? id : String(id).slice(i + 1);
}

function span(text) {
  if (!text) return null;
  const s = document.createElement('span');
  s.textContent = text;
  return s;
}

function formatCount(n) {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1).replace(/\.0$/, '') + 'M';
  if (n >= 1_000) return (n / 1_000).toFixed(1).replace(/\.0$/, '') + 'K';
  return String(n);
}

// ─── IntersectionObserver — unveil on first scroll-into-view ──────────
let io = null;
function observeReveals() {
  if (io) io.disconnect();
  io = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-revealed');
          io.unobserve(entry.target);
        }
      }
    },
    { rootMargin: '0px 0px -10% 0px', threshold: 0.15 },
  );
  for (const el of resultsEl.querySelectorAll('.record')) io.observe(el);
}

// ─── Source filter toggles ────────────────────────────────────────────
async function loadSources() {
  try {
    const r = await fetch('/api/sources');
    if (!r.ok) return;
    const data = await r.json();
    state.sources = data.sources || [];
    renderSourceToggles();
  } catch {
    // Pages Functions not running — no toggles, federation also won't work.
  }
}

function renderSourceToggles() {
  sourcesEl.replaceChildren();
  if (state.sources.length === 0) return;

  for (const s of state.sources) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'agency'; // reuses existing brutalist toggle styling
    btn.setAttribute('aria-pressed', state.sourceFilter === s.id ? 'true' : 'false');
    const lamp = document.createElement('span');
    lamp.className = 'agency__lamp';
    const label = document.createElement('span');
    label.textContent = s.label;
    const sub = document.createElement('span');
    sub.className = 'agency__count';
    sub.textContent = s.sublabel || '';
    btn.append(lamp, label, sub);
    btn.addEventListener('click', () => {
      state.sourceFilter = state.sourceFilter === s.id ? null : s.id;
      renderSourceToggles();
      runSearch();
    });
    sourcesEl.appendChild(btn);
  }
}

loadSources();

// ─── In-app document viewer ──────────────────────────────────────────
// Click any record → full-screen brutalist overlay. If the source allows
// iframing, embeds the publisher's own page (no restyle). If blocked,
// falls back to a metadata card with explicit "open in new tab" action.

let overlayEl = null;
let escListener = null;

async function openDocument(rec) {
  if (!overlayEl) overlayEl = buildOverlayShell();
  overlayEl.dataset.state = 'loading';
  overlayEl.querySelector('.viewer__title').textContent = rec.title || '';
  overlayEl.querySelector('.viewer__source').textContent = sourceLabelFromId(rec.id);
  overlayEl.querySelector('.viewer__open-original').href = rec.source_url || '#';
  overlayEl.querySelector('.viewer__body').replaceChildren(loadingNode());
  document.body.appendChild(overlayEl);
  document.body.style.overflow = 'hidden';

  escListener = (e) => { if (e.key === 'Escape') closeDocument(); };
  document.addEventListener('keydown', escListener);

  let info;
  try {
    const r = await fetch(`/api/document?id=${encodeURIComponent(rec.id)}`);
    info = r.ok ? await r.json() : null;
  } catch {
    info = null;
  }

  // Merge known fields from the record card into info for the fallback card.
  info = { ...rec, ...(info || {}) };

  if (info && info.embeddable && info.frame_url) {
    overlayEl.dataset.state = 'iframe';
    const frame = document.createElement('iframe');
    frame.className = 'viewer__frame';
    frame.src = info.frame_url;
    // Intentionally no `sandbox` — strict sandbox flags break heavy publisher
    // JS (e.g. Internet Archive's BookReader), which renders blank with
    // `sandbox="allow-scripts allow-same-origin"`. We're framing trusted
    // .gov/.archive sources only.
    frame.setAttribute('referrerpolicy', 'no-referrer');
    frame.setAttribute('allow', 'fullscreen');
    overlayEl.querySelector('.viewer__body').replaceChildren(frame);
  } else {
    overlayEl.dataset.state = 'fallback';
    overlayEl.querySelector('.viewer__body').replaceChildren(buildFallbackCard(info));
  }
}

function buildOverlayShell() {
  const root = document.createElement('div');
  root.className = 'viewer';
  root.innerHTML = `
    <header class="viewer__bar">
      <button type="button" class="viewer__back" aria-label="Close document">← BACK</button>
      <div class="viewer__heads">
        <span class="viewer__source"></span>
        <span class="viewer__title"></span>
      </div>
      <a class="viewer__open-original" target="_blank" rel="noopener noreferrer">↗ OPEN ORIGINAL</a>
    </header>
    <div class="viewer__body"></div>
  `;
  root.querySelector('.viewer__back').addEventListener('click', closeDocument);
  // Click on the dim border around the panel closes (mobile backdrop).
  root.addEventListener('click', (e) => {
    if (e.target === root) closeDocument();
  });
  return root;
}

function closeDocument() {
  if (!overlayEl) return;
  overlayEl.remove();
  document.body.style.overflow = '';
  if (escListener) document.removeEventListener('keydown', escListener);
  escListener = null;
}

function loadingNode() {
  const el = document.createElement('div');
  el.className = 'viewer__loading';
  el.textContent = '▮▮▮ RETRIEVING ▮▮▮';
  return el;
}

function buildFallbackCard(info) {
  const card = document.createElement('div');
  card.className = 'viewer__fallback';

  const reasonText =
    info.reason === 'x-frame-options'
      ? 'Source blocks embedded viewing (X-Frame-Options).'
      : info.reason === 'csp'
      ? 'Source blocks embedded viewing (Content-Security-Policy).'
      : info.reason === 'unreachable'
      ? 'Source unreachable from our edge.'
      : 'Source cannot be embedded.';

  const dl = document.createElement('dl');
  dl.className = 'viewer__meta';
  for (const [k, v] of [
    ['AGENCY', info.agency],
    ['UNSEALED', info.unsealed_date],
    ['COLLECTION', info.collection_id],
  ]) {
    if (!v) continue;
    const dt = document.createElement('dt'); dt.textContent = k;
    const dd = document.createElement('dd'); dd.textContent = v;
    dl.append(dt, dd);
  }

  const desc = document.createElement('p');
  desc.className = 'viewer__abstract';
  desc.textContent = info.description || '— NO ABSTRACT ON FILE —';

  const note = document.createElement('p');
  note.className = 'viewer__note';
  note.textContent = reasonText;

  const action = document.createElement('a');
  action.className = 'viewer__action';
  action.href = info.source_url;
  action.target = '_blank';
  action.rel = 'noopener noreferrer';
  action.textContent = '↗ OPEN IN NEW TAB';

  card.append(dl, desc, note, action);
  return card;
}

function sourceLabelFromId(id) {
  if (!id) return '';
  const s = String(id).split(':')[0];
  return ({ ia: 'INTERNET ARCHIVE', ntrs: 'NASA NTRS', curated: 'CURATED' })[s] || s.toUpperCase();
}
