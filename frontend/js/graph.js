// Interactive SVG node-link view of the file-level dependency graph.
// Layout: a small Fruchterman-Reingold-style force simulation (no dependencies).
// Nodes/edges that belong to an import cycle are drawn in red.

import { $, esc } from './dom.js';

const ITERATIONS = 300;

function layout(nodes, edges, byId, width, height) {
  const k = Math.sqrt((width * height) / nodes.length) * 0.55;
  for (let it = 0; it < ITERATIONS; it++) {
    const temp = 1 - it / ITERATIONS;
    for (const a of nodes) {
      for (const b of nodes) {
        if (a === b) continue;
        const dx = a.x - b.x, dy = a.y - b.y, d2 = dx * dx + dy * dy + 0.01, f = (k * k) / d2;
        a.vx += dx * f * 0.02;
        a.vy += dy * f * 0.02;
      }
    }
    for (const e of edges) {
      const a = byId[e.source], b = byId[e.target];
      const dx = b.x - a.x, dy = b.y - a.y, d = Math.hypot(dx, dy) + 0.01, f = (d - k) * 0.02;
      a.vx += (dx / d) * f; a.vy += (dy / d) * f;
      b.vx -= (dx / d) * f; b.vy -= (dy / d) * f;
    }
    for (const n of nodes) {
      n.vx += (width / 2 - n.x) * 0.004;
      n.vy += (height / 2 - n.y) * 0.004;
      n.x += Math.max(-10, Math.min(10, n.vx)) * temp;
      n.y += Math.max(-10, Math.min(10, n.vy)) * temp;
      n.vx *= 0.5; n.vy *= 0.5;
      n.x = Math.max(24, Math.min(width - 24, n.x));
      n.y = Math.max(18, Math.min(height - 18, n.y));
    }
  }
}

const radius = (n) => 5 + Math.min(9, n.degree * 1.4);
const shortName = (path) => path.split('/').pop();

function edgePath(e, byId) {
  const a = byId[e.source], b = byId[e.target], d = Math.hypot(b.x - a.x, b.y - a.y) || 1;
  const ex = b.x - ((b.x - a.x) / d) * (radius(b) + 2);
  const ey = b.y - ((b.y - a.y) / d) * (radius(b) + 2);
  // Slight curve so a->b and b->a edges don't overlap.
  const mx = (a.x + ex) / 2 + (ey - a.y) * 0.12, my = (a.y + ey) / 2 - (ex - a.x) * 0.12;
  const color = e.in_cycle ? '#f43f5e' : '#334155';
  return `<path class="edge" data-s="${esc(e.source)}" data-t="${esc(e.target)}" d="M${a.x},${a.y} Q${mx},${my} ${ex},${ey}"
    fill="none" stroke="${color}" stroke-width="${e.in_cycle ? 2 : 1.2}" marker-end="url(#${e.in_cycle ? 'arrR' : 'arr'})"/>`;
}

function nodeGroup(n, showLabel) {
  const r = radius(n);
  return `<g class="node" data-id="${esc(n.id)}">
    <circle cx="${n.x}" cy="${n.y}" r="${r}" fill="${n.in_cycle ? '#f43f5e' : '#8b5cf6'}" fill-opacity=".85"
      stroke="${n.in_cycle ? '#fecdd3' : '#c4b5fd'}" stroke-width="1"/>
    ${showLabel ? `<text x="${n.x}" y="${n.y - r - 4}" text-anchor="middle" font-size="10" font-family="JetBrains Mono" fill="#cbd5e1">${esc(shortName(n.id))}</text>` : ''}
  </g>`;
}

function bindInteractions(svg, edges, byId, width, height) {
  const tip = $('graphTip');
  let selected = null;
  svg.querySelectorAll('.node').forEach((el) => {
    const id = el.dataset.id, n = byId[id];
    el.addEventListener('mouseenter', () => {
      tip.textContent = `${id} · ${n.degree} links${n.in_cycle ? ' · IN CYCLE' : ''}`;
      tip.style.left = `${(n.x / width) * svg.clientWidth + 10}px`;
      tip.style.top = `${(n.y / height) * svg.clientHeight - 28}px`;
      tip.classList.remove('hidden');
    });
    el.addEventListener('mouseleave', () => tip.classList.add('hidden'));
    el.addEventListener('click', () => {
      selected = selected === id ? null : id;
      const neighbours = new Set([id]);
      edges.forEach((e) => {
        if (e.source === id) neighbours.add(e.target);
        if (e.target === id) neighbours.add(e.source);
      });
      svg.querySelectorAll('.node').forEach((x) => x.classList.toggle('dim', !!selected && !neighbours.has(x.dataset.id)));
      svg.querySelectorAll('.edge').forEach((x) => x.classList.toggle('dim', !!selected && x.dataset.s !== id && x.dataset.t !== id));
    });
  });
}

/** Draw `fileGraph` ({nodes, edges} from graph_summary.file_graph) into #graphSvg. */
export function drawGraph(fileGraph) {
  const svg = $('graphSvg');
  const width = svg.clientWidth || 500, height = svg.clientHeight || 320;
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
  const fg = fileGraph || { nodes: [], edges: [] };
  if (!fg.nodes.length) {
    svg.innerHTML = `<text x="${width / 2}" y="${height / 2}" text-anchor="middle" fill="#64748b" font-size="12">No cross-file dependencies found</text>`;
    return;
  }

  const nodes = fg.nodes.map((n, i) => ({
    ...n,
    x: width / 2 + Math.cos(i * 2.4) * (40 + i * 6),
    y: height / 2 + Math.sin(i * 2.4) * (40 + i * 6),
    vx: 0, vy: 0,
  }));
  const byId = Object.fromEntries(nodes.map((n) => [n.id, n]));
  const edges = fg.edges.filter((e) => byId[e.source] && byId[e.target]);
  layout(nodes, edges, byId, width, height);

  svg.innerHTML = `
    <defs>
      <marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0,0L10,5L0,10z" fill="#475569"/></marker>
      <marker id="arrR" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0,0L10,5L0,10z" fill="#f43f5e"/></marker>
    </defs>
    ${edges.map((e) => edgePath(e, byId)).join('')}
    ${nodes.map((n) => nodeGroup(n, nodes.length <= 18)).join('')}`;
  bindInteractions(svg, edges, byId, width, height);
}
