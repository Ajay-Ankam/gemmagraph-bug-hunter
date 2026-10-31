// Renders a scan result into the three dashboard columns.

import { $, esc, md, badge, empty, SEVERITY_CLASSES } from './dom.js';
import { drawGraph } from './graph.js';
import { renderPatch } from './patch.js';

const CONFIDENCE_CLASSES = { high: 'text-rose-300', medium: 'text-amber-300', low: 'text-slate-400' };

/** Scan bar: cache badge, latency, timing breakdown, timestamp. */
export function renderMeta(scan, roundTripMs) {
  const cacheBadge = scan.cached
    ? badge('CACHE HIT ⚡', 'bg-emerald-500/15 text-emerald-300 ring-emerald-500/40')
    : badge('LIVE GEMMA 4 AUDIT', 'bg-violet-500/15 text-violet-300 ring-violet-500/40');
  const t = scan.timings_ms || {};
  const breakdown = !scan.cached && t.gemma
    ? `<span class="text-slate-500">graphify ${(t.graphify / 1000).toFixed(1)}s · gemma ${(t.gemma / 1000).toFixed(1)}s</span>` : '';
  const when = scan.scanned_at
    ? `<span class="text-slate-500">scanned ${new Date(scan.scanned_at * 1000).toLocaleString()}</span>` : '';
  $('scanMeta').innerHTML = `${cacheBadge}<span class="font-mono text-slate-200">${roundTripMs.toLocaleString()} ms</span>${breakdown}${when}<span class="font-mono text-slate-500">${esc(scan.repo)}</span>`;
}

function stat(label, value, cls = 'text-white') {
  return `<div class="bg-slate-900/70 rounded-lg p-2.5"><div class="text-lg font-semibold ${cls}">${esc(value)}</div><div class="text-[10px] uppercase tracking-wider text-slate-500">${label}</div></div>`;
}

/** Left column: stats, health score, god nodes, cycles, graph, GRAPH_REPORT.md. */
export function renderTopology(graph, audit, reportMd) {
  const st = graph.stats || {};
  const cycles = graph.circular_dependencies || [];
  $('stats').innerHTML = stat('Nodes', st.nodes ?? 0) + stat('Edges', st.edges ?? 0) + stat('Files', st.files ?? 0)
    + stat('Cycles', cycles.length, cycles.length ? 'text-rose-400' : 'text-emerald-400');

  const hs = audit.health_score;
  const hsClass = hs >= 75 ? 'bg-emerald-500/15 text-emerald-300' : hs >= 50 ? 'bg-amber-500/15 text-amber-300' : 'bg-rose-500/15 text-rose-300';
  $('healthScore').innerHTML = typeof hs === 'number' ? `<span class="text-xs font-semibold px-2 py-0.5 rounded ${hsClass}">Health ${hs}/100</span>` : '';

  const gods = graph.god_nodes || [];
  const maxDegree = Math.max(1, ...gods.map((n) => n.degree));
  $('godNodes').innerHTML = gods.length ? gods.map((n, i) => `
    <li class="text-sm">
      <div class="flex items-baseline justify-between gap-2"><span class="font-mono text-slate-100 truncate">${i + 1}. ${esc(n.label)}</span><span class="text-xs text-slate-400 shrink-0">${n.degree} edges</span></div>
      <div class="text-[11px] text-slate-500 font-mono truncate">${esc(n.source_file || '')}${n.source_location ? ':' + esc(n.source_location) : ''}</div>
      <div class="h-1 mt-1 rounded bg-slate-800"><div class="h-1 rounded bg-gradient-to-r from-violet-500 to-cyan-400" style="width:${(n.degree / maxDegree) * 100}%"></div></div>
    </li>`).join('') : empty('No god nodes detected.');

  $('graphCycles').innerHTML = cycles.length ? cycles.map((c) => `
    <div class="rounded-lg bg-rose-500/5 ring-1 ring-rose-500/25 p-2.5">
      <div class="font-mono text-xs text-rose-200 break-all">${c.cycle.map(esc).join(' <span class="text-rose-500">→</span> ')}</div>
      ${(c.evidence || []).map((e) => `<div class="text-[11px] text-slate-400 font-mono mt-1">${esc(e.location)} · ${esc(e.from)} <span class="text-slate-600">${esc(e.relation)}</span> ${esc(e.to)}</div>`).join('')}
    </div>`).join('') : empty('No import cycles. 🎉');

  $('reportMd').innerHTML = md(reportMd || '_No report._');
  drawGraph(graph.file_graph);
}

function hotspotCard(h) {
  const sev = String(h.severity || 'low').toLowerCase();
  const radius = (h.blast_radius || []).length
    ? `<div class="mt-2 text-[11px] text-slate-500">Blast radius: ${h.blast_radius.map((x) => `<span class="font-mono text-slate-400">${esc(x)}</span>`).join(', ')}</div>` : '';
  return `<div class="rounded-lg bg-slate-900/70 ring-1 ring-slate-800 p-3">
    <div class="flex items-center gap-2 flex-wrap">${badge(sev, SEVERITY_CLASSES[sev] || SEVERITY_CLASSES.low)}${h.category ? `<span class="text-xs text-slate-300">${esc(h.category)}</span>` : ''}</div>
    <div class="font-mono text-xs text-cyan-300 mt-1.5">${esc(h.file)}${h.line ? ':' + esc(h.line) : ''}</div>
    <p class="text-sm text-slate-300 mt-1.5 leading-relaxed">${esc(h.explanation)}</p>${radius}
  </div>`;
}

/** Centre column (Gemma 4 audit) + right column patch. */
export function renderAudit(audit) {
  $('auditSummary').textContent = audit.summary || (audit.error ? '' : 'No summary returned.');
  $('auditError').classList.toggle('hidden', !audit.error);
  $('auditError').textContent = audit.error || '';

  const hotspots = audit.security_hotspots || [];
  $('hotspotCount').textContent = hotspots.length ? `${hotspots.length} found` : '';
  $('hotspots').innerHTML = hotspots.length ? hotspots.map(hotspotCard).join('') : empty('No security hotspots reported.');

  const cycles = audit.circular_dependencies || [];
  $('auditCycles').innerHTML = cycles.length ? cycles.map((c) => `
    <div class="rounded-lg bg-slate-900/70 ring-1 ring-slate-800 p-3">
      <div class="font-mono text-xs text-rose-200 break-all">${(Array.isArray(c.cycle) ? c.cycle : [c.cycle]).map(esc).join(' → ')}</div>
      ${c.impact ? `<p class="text-sm text-slate-300 mt-1.5"><span class="text-slate-500">Impact:</span> ${esc(c.impact)}</p>` : ''}
      ${c.fix ? `<p class="text-sm text-emerald-300/90 mt-1"><span class="text-slate-500">Fix:</span> ${esc(c.fix)}</p>` : ''}
    </div>`).join('') : empty('Gemma confirmed no circular dependencies.');

  const dead = audit.dead_code || [];
  $('deadCode').innerHTML = dead.length ? dead.map((x) => `
    <div class="flex gap-3 items-start text-sm border-b border-slate-800/80 pb-2 last:border-0">
      <span class="font-mono text-xs text-slate-100 shrink-0">${esc(x.symbol)}</span>
      <div class="min-w-0"><div class="font-mono text-[11px] text-slate-500 truncate">${esc(x.file)} <span class="${CONFIDENCE_CLASSES[x.confidence] || 'text-slate-400'}">· ${esc(x.confidence || '?')} confidence</span></div><div class="text-xs text-slate-400">${esc(x.reason)}</div></div>
    </div>`).join('') : empty('No dead code reported.');

  const fixes = audit.prioritized_fixes || [];
  $('fixes').innerHTML = fixes.length ? fixes.map((f) => `
    <li class="flex gap-3 text-sm"><span class="w-6 h-6 shrink-0 rounded-full bg-violet-500/20 text-violet-300 grid place-items-center text-xs font-semibold">${esc(f.rank)}</span>
    <div><div class="text-slate-100">${esc(f.title)} <span class="font-mono text-[11px] text-slate-500">${esc(f.file)}</span></div><div class="text-xs text-slate-400">${esc(f.reason)}</div></div></li>`).join('') : empty('No fixes ranked.');

  renderPatch(audit.git_diff_patch || '');
}

/** Render a full scan result. */
export function renderScan(scan, roundTripMs) {
  $('emptyState').classList.add('hidden');
  $('results').classList.remove('hidden');
  const audit = scan.audit || {};
  renderMeta(scan, roundTripMs);
  renderTopology(scan.graph_summary || {}, audit, scan.report_md);
  renderAudit(audit);
  $('visionResult').innerHTML = '';
}
