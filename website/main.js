/* ─── Rough.js sketchy borders on all [data-rough] elements ─── */

function drawRoughBorders() {
  document.querySelectorAll('[data-rough]').forEach(el => {
    // Remove old canvas if resizing
    const old = el.querySelector('canvas.rough-border');
    if (old) old.remove();

    const canvas = document.createElement('canvas');
    canvas.className = 'rough-border';
    canvas.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:-1';
    canvas.width = el.offsetWidth;
    canvas.height = el.offsetHeight;
    el.appendChild(canvas);

    const rc = rough.canvas(canvas);

    // Pick a color based on context
    const isCode = el.classList.contains('code-block');
    const isToken = el.classList.contains('token-card');
    const strokeColor = isCode ? '#e8e2d6' : isToken ? '#c49a3c' : '#2d2a24';

    rc.rectangle(4, 4, canvas.width - 8, canvas.height - 8, {
      stroke: strokeColor,
      strokeWidth: 2.5,
      roughness: 1.8,
      bowing: 1.5,
      fill: 'none',
      seed: hashCode(el.textContent || '') // deterministic so it doesn't jitter on resize
    });
  });
}

/* Simple string hash for deterministic rough seeds */
function hashCode(str) {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = ((hash << 5) - hash + str.charCodeAt(i)) | 0;
  }
  return Math.abs(hash);
}

/* ─── Hero background doodles ─── */

function drawHeroDoodles() {
  const canvas = document.getElementById('hero-canvas');
  if (!canvas) return;

  canvas.width = canvas.offsetWidth;
  canvas.height = canvas.offsetHeight;

  const rc = rough.canvas(canvas);
  const w = canvas.width;
  const h = canvas.height;
  const color = 'rgba(58, 107, 53, 0.08)';

  // Scattered hand-drawn circles, lines, squiggles
  const seed = 42;
  const shapes = [
    // top-left area
    () => rc.circle(w * 0.08, h * 0.2, 60, { stroke: color, roughness: 2.5, seed }),
    () => rc.line(w * 0.05, h * 0.35, w * 0.15, h * 0.32, { stroke: color, roughness: 2, seed: seed + 1 }),

    // top-right
    () => rc.rectangle(w * 0.82, h * 0.12, 50, 50, { stroke: color, roughness: 2.5, seed: seed + 2 }),
    () => rc.line(w * 0.9, h * 0.25, w * 0.95, h * 0.35, { stroke: color, roughness: 2, seed: seed + 3 }),

    // bottom-left
    () => rc.ellipse(w * 0.12, h * 0.78, 80, 40, { stroke: color, roughness: 2.5, seed: seed + 4 }),

    // bottom-right
    () => rc.circle(w * 0.88, h * 0.75, 45, { stroke: color, roughness: 2.5, seed: seed + 5 }),
    () => rc.line(w * 0.8, h * 0.85, w * 0.92, h * 0.82, { stroke: color, roughness: 2, seed: seed + 6 }),

    // middle sides
    () => rc.line(w * 0.02, h * 0.55, w * 0.08, h * 0.58, { stroke: color, roughness: 2, seed: seed + 7 }),
    () => rc.line(w * 0.93, h * 0.5, w * 0.98, h * 0.53, { stroke: color, roughness: 2, seed: seed + 8 }),

    // a few dots / small circles scattered
    () => rc.circle(w * 0.2, h * 0.15, 12, { stroke: color, fill: color, fillStyle: 'solid', roughness: 1, seed: seed + 9 }),
    () => rc.circle(w * 0.75, h * 0.88, 10, { stroke: color, fill: color, fillStyle: 'solid', roughness: 1, seed: seed + 10 }),
    () => rc.circle(w * 0.6, h * 0.1, 8, { stroke: color, fill: color, fillStyle: 'solid', roughness: 1, seed: seed + 11 }),
  ];

  shapes.forEach(fn => fn());
}

/* ─── Copy agent instructions ─── */

const AGENT_INSTRUCTIONS = `I want you to improve the quality of this codebase. To do this, install and run desloppify.
Run ALL of the following (requires Python 3.11+):

pip install --upgrade "desloppify[full]"
desloppify update-skill claude    # installs the full workflow guide — pick yours: claude, cursor, codex, copilot, windsurf, gemini

Before scanning, check for directories that should be excluded (vendor, build output,
generated code, worktrees, etc.) and exclude obvious ones with \`desloppify exclude <path>\`.
Share any questionable candidates with me before excluding.

desloppify scan --path .
desloppify next

--path is the directory to scan (use "." for the whole project, or "src/" etc).

Your goal is to get the strict score as high as possible. The scoring resists gaming — the
only way to improve it is to actually make the code better.

THE LOOP: run \`next\`. It is the execution queue from the living plan, not the whole backlog.
It tells you what to fix now, which file, and the resolve command to run when done.
Fix it, resolve it, run \`next\` again. Over and over. This is your main job.

Use \`desloppify backlog\` only when you need to inspect broader open work that is not currently
driving execution.

Don't be lazy. Large refactors and small detailed fixes — do both with equal energy. No task
is too big or too small. Fix things properly, not minimally.

Use \`plan\` / \`plan queue\` to reorder priorities or cluster related issues. Rescan periodically.
The scan output includes agent instructions — follow them, don't substitute your own analysis.`;

function copyAgentInstructions() {
  const btn = document.getElementById('copy-instructions');
  const originalText = btn.textContent;

  function showSuccess() {
    btn.textContent = 'Copied!';
    btn.classList.add('btn-success');
    setTimeout(() => {
      btn.textContent = originalText;
      btn.classList.remove('btn-success');
    }, 2000);
  }

  navigator.clipboard.writeText(AGENT_INSTRUCTIONS).then(showSuccess).catch(() => {
    const ta = document.createElement('textarea');
    ta.value = AGENT_INSTRUCTIONS;
    ta.style.cssText = 'position:fixed;left:-9999px';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    showSuccess();
  });
}

/* ─── GitHub Releases ─── */

async function loadReleases() {
  const container = document.getElementById('releases-list');
  try {
    const resp = await fetch('https://api.github.com/repos/peteromallet/desloppify/releases?per_page=8');
    if (!resp.ok) throw new Error(`GitHub API returned ${resp.status}`);
    const releases = await resp.json();

    if (!releases.length) {
      container.innerHTML = '<p class="releases-error">No releases found yet.</p>';
      return;
    }

    container.innerHTML = releases.map(r => {
      // Strip HTML image blocks (mascot etc.) from release notes
      const body = (r.body || 'No release notes.').replace(/<p[^>]*>[\s\S]*?<img[^>]*>[\s\S]*?<\/p>/gi, '').trim();
      const fullHtml = renderMarkdownLight(body);
      const preview = getFirstParagraph(body);
      const previewHtml = renderMarkdownLight(preview);
      const hasMore = (r.body || '').trim().length > preview.length + 10;

      return `
      <div class="release-item sketchy-border">
        <div class="release-header">
          <a href="${r.html_url}" target="_blank" class="release-tag">${escapeHtml(r.tag_name)}</a>
          <span class="release-date">${formatDate(r.published_at)}</span>
        </div>
        <div class="release-body">
          <div class="release-preview">${previewHtml}</div>
          ${hasMore ? `<div class="release-full" hidden>${fullHtml}</div>
          <button class="release-toggle" onclick="toggleRelease(this)">Show more</button>` : ''}
        </div>
      </div>`;
    }).join('');

  } catch (err) {
    container.innerHTML = `<p class="releases-error">Could not load releases. <a href="https://github.com/peteromallet/desloppify/releases" target="_blank">View on GitHub</a></p>`;
  }
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function formatDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
}

function getFirstParagraph(md) {
  if (!md) return '';
  // Split on double newline, take the first non-empty chunk
  const chunks = md.split(/\n\n/).filter(c => c.trim());
  return chunks[0] || '';
}

function toggleRelease(btn) {
  const body = btn.parentElement;
  const preview = body.querySelector('.release-preview');
  const full = body.querySelector('.release-full');
  const isExpanded = !full.hidden;

  if (isExpanded) {
    full.hidden = true;
    preview.hidden = false;
    btn.textContent = 'Show more';
  } else {
    full.hidden = false;
    preview.hidden = true;
    btn.textContent = 'Show less';
  }
}

/* Very lightweight markdown → HTML (handles lists, bold, headers, links) */
function renderMarkdownLight(md) {
  if (!md) return '';
  let html = escapeHtml(md);

  // Headers
  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');

  // Bold
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

  // Inline code
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

  // Unordered list items
  html = html.replace(/^[*-] (.+)$/gm, '<li>$1</li>');
  // Wrap consecutive <li> in <ul>
  html = html.replace(/((?:<li>.*<\/li>\n?)+)/g, '<ul>$1</ul>');

  // Links [text](url)
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');

  // Paragraphs (double newline)
  html = html.replace(/\n\n/g, '</p><p>');
  html = '<p>' + html + '</p>';

  // Clean up empty paragraphs
  html = html.replace(/<p>\s*<\/p>/g, '');
  html = html.replace(/<p>\s*(<[hul])/g, '$1');
  html = html.replace(/(<\/[hul]\w*>)\s*<\/p>/g, '$1');

  return html;
}

/* ─── Init ─── */

window.addEventListener('load', () => {
  drawRoughBorders();
  drawHeroDoodles();
  loadReleases();
});

let resizeTimer;
window.addEventListener('resize', () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => {
    drawRoughBorders();
    drawHeroDoodles();
  }, 200);
});
