// "Multimodal Architecture Drift Check" dropzone -> POST /api/multimodal-audit.

import { $, esc, md, empty } from './dom.js';
import { auditDiagram } from './api.js';

const ALLOWED_TYPES = ['image/png', 'image/jpeg', 'image/webp'];
const MAX_BYTES = 5 * 1024 * 1024;

async function upload(file, getScan) {
  const scan = getScan();
  const result = $('visionResult');
  if (!scan) { result.innerHTML = empty('Run a scan first, then upload a diagram.'); return; }
  // Client-side checks mirror the server's, for instant feedback.
  if (!ALLOWED_TYPES.includes(file.type)) { result.innerHTML = empty('Use a PNG, JPEG or WebP image.'); return; }
  if (file.size > MAX_BYTES) { result.innerHTML = empty('Image must be 5 MB or smaller.'); return; }

  const preview = $('imagePreview');
  preview.src = URL.createObjectURL(file);
  preview.classList.remove('hidden');
  result.innerHTML = '';
  $('visionStatus').classList.remove('hidden');
  const t0 = performance.now();
  try {
    const data = await auditDiagram(scan.scan_id, file);
    const ms = Math.round(performance.now() - t0).toLocaleString();
    result.innerHTML = `<div class="text-[11px] text-slate-500 mb-2">Gemma 4 vision · ${ms} ms</div>` + md(data.analysis_markdown);
  } catch (err) {
    result.innerHTML = `<div class="text-sm text-rose-300">Vision audit failed: ${esc(err.message)}</div>`;
  } finally {
    $('visionStatus').classList.add('hidden');
  }
}

/** Wire up drag-and-drop + file picker. `getScan` returns the current scan or null. */
export function initUpload(getScan) {
  const zone = $('dropzone');
  ['dragenter', 'dragover'].forEach((ev) => zone.addEventListener(ev, (e) => { e.preventDefault(); zone.classList.add('border-violet-500'); }));
  ['dragleave', 'drop'].forEach((ev) => zone.addEventListener(ev, (e) => { e.preventDefault(); zone.classList.remove('border-violet-500'); }));
  zone.addEventListener('drop', (e) => { const f = e.dataTransfer.files[0]; if (f) upload(f, getScan); });
  $('imageInput').addEventListener('change', (e) => {
    const f = e.target.files[0];
    if (f) upload(f, getScan);
    e.target.value = '';
  });
}
