// Entry point: health badge, scan bar and presets; owns the current scan state.

import { $ } from './dom.js';
import { getHealth, scanRepo } from './api.js';
import { renderScan } from './render.js';
import { drawGraph } from './graph.js';
import { initPatchCopy } from './patch.js';
import { initUpload } from './upload.js';

let currentScan = null;

async function showHealth() {
  const el = $('healthBadge');
  try {
    const h = await getHealth();
    const n = h.disk_cache.cached_scans;
    el.className = `px-2.5 py-1 rounded-full ring-1 ${h.ready
      ? 'bg-emerald-500/10 text-emerald-300 ring-emerald-500/30'
      : 'bg-amber-500/10 text-amber-300 ring-amber-500/30'}`;
    el.textContent = `API ${h.status} · ${n} cached scan${n === 1 ? '' : 's'}${h.checks.gemini_api_key ? '' : ' · no API key'}`;
  } catch {
    el.textContent = 'API offline';
  }
}

function setBusy(busy, message = '') {
  $('scanBtn').disabled = busy;
  $('scanSpin').classList.toggle('hidden', !busy);
  if (busy) $('scanMeta').innerHTML = `<span class="text-slate-400">${message}</span>`;
}

async function runScan(repo) {
  const force = $('forceRefresh').checked;
  $('scanError').classList.add('hidden');
  setBusy(true, force ? 'Running Graphify + live Gemma 4 audit…' : 'Scanning…');
  const t0 = performance.now();
  try {
    const scan = await scanRepo(repo, force);
    currentScan = scan;
    renderScan(scan, Math.round(performance.now() - t0));
  } catch (err) {
    $('scanError').textContent = `Scan failed: ${err.message}`;
    $('scanError').classList.remove('hidden');
    $('scanMeta').innerHTML = '';
  } finally {
    setBusy(false);
  }
}

function init() {
  showHealth();
  $('scanForm').addEventListener('submit', (e) => {
    e.preventDefault();
    runScan($('repoInput').value.trim() || '.');
  });
  document.querySelectorAll('.preset').forEach((button) =>
    button.addEventListener('click', () => {
      $('repoInput').value = button.dataset.preset;
      runScan(button.dataset.preset);
    }),
  );
  initPatchCopy();
  initUpload(() => currentScan);
  window.addEventListener('resize', () => currentScan && drawGraph(currentScan.graph_summary?.file_graph));
}

init();
