// Small DOM + formatting helpers shared by every module.
// All untrusted text (API data, model output) must go through esc() or md().

/** document.getElementById shorthand. */
export const $ = (id) => document.getElementById(id);

/** HTML-escape a value for safe interpolation into innerHTML. */
export const esc = (value) =>
  String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);

/** Render Markdown (model output, GRAPH_REPORT.md) to sanitized HTML. */
export const md = (text) => window.DOMPurify.sanitize(window.marked.parse(String(text || '')));

/** Pill badge, e.g. severity or cache status. */
export const badge = (text, cls) =>
  `<span class="inline-block text-[10px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded ring-1 ${cls}">${esc(text)}</span>`;

/** Muted placeholder for empty lists. */
export const empty = (msg) => `<div class="text-sm text-slate-500 italic">${esc(msg)}</div>`;

/** Tailwind classes per severity level. */
export const SEVERITY_CLASSES = {
  critical: 'bg-rose-500/20 text-rose-300 ring-rose-500/40',
  high: 'bg-orange-500/20 text-orange-300 ring-orange-500/40',
  medium: 'bg-amber-500/20 text-amber-200 ring-amber-500/40',
  low: 'bg-sky-500/20 text-sky-300 ring-sky-500/40',
};
