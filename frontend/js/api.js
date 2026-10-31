// Thin client for the FastAPI backend. Every error the server returns uses the
// envelope {"error": "...", "status": "error"}; it is surfaced as an Error.

async function request(path, options = {}) {
  const res = await fetch(path, options);
  let data = {};
  try {
    data = await res.json();
  } catch {
    /* non-JSON body (e.g. proxy error page) */
  }
  if (!res.ok) throw new Error(data.error || data.detail || `HTTP ${res.status}`);
  return data;
}

/** GET /api/health */
export const getHealth = () => request('/api/health');

/** POST /api/scan: returns the scan result, cached or live. */
export const scanRepo = (repoUrl, forceRefresh = false) =>
  request('/api/scan', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ repo_url: repoUrl, force_refresh: forceRefresh }),
  });

/** POST /api/multimodal-audit: Gemma 4 vision diagram check. */
export const auditDiagram = (scanId, file) => {
  const form = new FormData();
  form.append('scan_id', scanId);
  form.append('image', file);
  return request('/api/multimodal-audit', { method: 'POST', body: form });
};
