// Colour-coded unified-diff viewer + clipboard copy for Gemma's fix patch.

import { $, esc, empty } from './dom.js';

let currentPatch = '';

function lineClass(line) {
  if (line.startsWith('+++') || line.startsWith('---')) return 'text-slate-200 font-semibold';
  if (line.startsWith('@@')) return 'text-cyan-300 bg-cyan-500/5';
  if (line.startsWith('+')) return 'text-emerald-300 bg-emerald-500/10';
  if (line.startsWith('-')) return 'text-rose-300 bg-rose-500/10';
  if (line.startsWith('diff ') || line.startsWith('index ')) return 'text-slate-500';
  return 'text-slate-400';
}

/** Render a git_diff_patch string into #patchView. */
export function renderPatch(patch) {
  currentPatch = patch || '';
  const view = $('patchView');
  if (!currentPatch.trim()) {
    view.innerHTML = `<div class="px-4 py-3">${empty('No patch generated.')}</div>`;
    return;
  }
  view.innerHTML = currentPatch
    .split('\n')
    .map((l) => `<div class="diff-line ${lineClass(l)}">${esc(l) || ' '}</div>`)
    .join('');
}

async function copyToClipboard(text) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    // Fallback for non-secure contexts (plain http on a LAN IP).
    const ta = Object.assign(document.createElement('textarea'), { value: text });
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    ta.remove();
  }
}

/** Wire up the "Copy Patch" button. */
export function initPatchCopy() {
  const button = $('copyPatch');
  button.addEventListener('click', async () => {
    if (!currentPatch) return;
    await copyToClipboard(currentPatch);
    button.textContent = 'Copied ✓';
    setTimeout(() => (button.textContent = 'Copy Patch'), 1500);
  });
}
