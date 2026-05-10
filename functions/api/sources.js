// GET /api/sources — return the list of federated sources for the toggle row.
// Replaces /api/agencies in the federated architecture.

export const onRequestGet = async () => {
  const sources = [
    { id: 'ia',      label: 'INTERNET ARCHIVE',  sublabel: 'NSA COLLECTION' },
    { id: 'ntrs',    label: 'NASA NTRS',         sublabel: 'TECHNICAL REPORTS' },
    { id: 'curated', label: 'CURATED',           sublabel: 'AARO / DOW / EDITORIAL' },
  ];
  return new Response(JSON.stringify({ sources }), {
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'cache-control': 'public, max-age=3600',
    },
  });
};
