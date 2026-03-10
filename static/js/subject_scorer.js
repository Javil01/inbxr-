/* ══════════════════════════════════════════════════════
   INBXR — Subject Line A/B Scorer
   ══════════════════════════════════════════════════════ */

'use strict';

const $ = (sel, ctx = document) => ctx.querySelector(sel);
const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

const LABELS = ['A', 'B', 'C', 'D', 'E'];
const MAX_INPUTS = 5;

// ══════════════════════════════════════════════════════
//  INPUT MANAGEMENT
// ══════════════════════════════════════════════════════

// Character counters
document.addEventListener('input', e => {
  if (!e.target.classList.contains('ss-input')) return;
  const counter = e.target.closest('.ss-input-row')?.querySelector('.ss-char-count');
  if (counter) {
    const len = e.target.value.length;
    counter.textContent = len;
    counter.style.color =
      len >= 30 && len <= 55 ? 'var(--green)' :
      len > 55 && len <= 70 ? 'var(--yellow)' :
      len > 70 ? 'var(--red)' : 'var(--text-3)';
  }
});

// Add another input
$('#ssAddBtn').addEventListener('click', () => {
  const inputs = $$('.ss-input-row', $('#ssInputs'));
  if (inputs.length >= MAX_INPUTS) return;

  const idx = inputs.length;
  const row = document.createElement('div');
  row.className = 'ss-input-row ss-input-row--new';
  row.innerHTML = `
    <span class="ss-input-label">${LABELS[idx]}</span>
    <input type="text" class="ss-input" placeholder="Another variation..." maxlength="200" />
    <span class="ss-char-count">0</span>
    <button type="button" class="ss-remove-btn" title="Remove">&times;</button>
  `;
  $('#ssInputs').appendChild(row);

  // Focus the new input
  row.querySelector('.ss-input').focus();

  // Hide add button at max
  if (idx + 1 >= MAX_INPUTS) {
    $('#ssAddBtn').style.display = 'none';
  }
});

// Remove input
document.addEventListener('click', e => {
  const btn = e.target.closest('.ss-remove-btn');
  if (!btn) return;
  const row = btn.closest('.ss-input-row');
  if (row) {
    row.remove();
    _relabelInputs();
    $('#ssAddBtn').style.display = '';
  }
});

function _relabelInputs() {
  $$('.ss-input-row').forEach((row, i) => {
    const label = row.querySelector('.ss-input-label');
    if (label) label.textContent = LABELS[i] || String.fromCharCode(65 + i);
  });
}

// ══════════════════════════════════════════════════════
//  SCORE & COMPARE
// ══════════════════════════════════════════════════════
$('#ssScoreBtn').addEventListener('click', async () => {
  const inputs = $$('.ss-input');
  const subjects = inputs.map(i => i.value.trim()).filter(Boolean);

  if (subjects.length < 2) {
    _shakeBtn();
    inputs[subjects.length === 0 ? 0 : 1].focus();
    return;
  }

  const btn = $('#ssScoreBtn');
  btn.disabled = true;
  $('.btn-text', btn).textContent = 'Scoring...';
  $('.btn-spinner', btn).classList.remove('hidden');

  try {
    const res = await fetch('/score-subjects', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        subjects,
        industry: $('#ssIndustry').value,
      }),
    });
    const data = await res.json();

    if (!res.ok || data.error) {
      alert(data.error || 'Scoring failed.');
      return;
    }

    renderResults(data);
  } catch (err) {
    alert('Network error. Please try again.');
  } finally {
    btn.disabled = false;
    $('.btn-text', btn).textContent = 'Score & Compare';
    $('.btn-spinner', btn).classList.add('hidden');
  }
});

function _shakeBtn() {
  const btn = $('#ssScoreBtn');
  btn.classList.add('ss-shake');
  setTimeout(() => btn.classList.remove('ss-shake'), 500);
}

// ══════════════════════════════════════════════════════
//  RENDER RESULTS
// ══════════════════════════════════════════════════════
function renderResults(data) {
  const container = $('#ssResults');
  container.classList.remove('hidden');
  container.scrollIntoView({ behavior: 'smooth', block: 'start' });

  // Winner banner
  const winner = data.results[0];
  const winnerBanner = $('#ssWinnerBanner');
  winnerBanner.innerHTML = `
    <div class="ss-winner-crown">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="28" height="28">
        <path d="M2 20h20"/>
        <path d="M4 20V10l4 4 4-8 4 8 4-4v10"/>
      </svg>
    </div>
    <div class="ss-winner-text">
      <span class="ss-winner-label">Winner — ${escHtml(winner.grade)} Grade (${winner.percentage}%)</span>
      <span class="ss-winner-subject">${escHtml(winner.subject)}</span>
    </div>
    <button type="button" class="ss-winner-copy" data-copy="${escAttr(winner.subject)}">Copy</button>
  `;

  // Cards
  const cards = $('#ssCards');
  cards.innerHTML = data.results.map((r, i) => {
    const letter = LABELS[i] || String.fromCharCode(65 + i);
    const isWinner = r.rank === 1;

    // Dimension bars
    const dims = Object.values(r.dimensions);
    const barsHTML = dims.map(d => {
      const pct = d.max > 0 ? (d.score / d.max) * 100 : 0;
      const barColor = pct >= 70 ? 'var(--green)' : pct >= 40 ? 'var(--yellow)' : 'var(--red)';
      return `
        <div class="ss-dim">
          <div class="ss-dim__header">
            <span class="ss-dim__label">${escHtml(d.label)}</span>
            <span class="ss-dim__score">${d.score}/${d.max}</span>
          </div>
          <div class="ss-dim__bar-track">
            <div class="ss-dim__bar-fill" style="width:${pct}%;background:${barColor}"></div>
          </div>
          <span class="ss-dim__detail">${escHtml(d.detail)}</span>
        </div>`;
    }).join('');

    // Tips
    const tipsHTML = r.tips.length ? `
      <div class="ss-tips">
        <span class="ss-tips__title">Tips to improve:</span>
        ${r.tips.map(t => `<div class="ss-tip">${escHtml(t)}</div>`).join('')}
      </div>` : '';

    return `
      <div class="ss-card ${isWinner ? 'ss-card--winner' : ''}" style="animation-delay:${i * 80}ms">
        <div class="ss-card__header">
          <div class="ss-card__rank">
            <span class="ss-card__letter">${letter}</span>
            ${r.badge ? `<span class="ss-card__badge ss-card__badge--${r.color}">${escHtml(r.badge)}</span>` : ''}
          </div>
          <div class="ss-card__score-ring ss-card__score-ring--${r.color}">
            <span class="ss-card__score-num">${r.percentage}</span>
          </div>
        </div>
        <div class="ss-card__subject">${escHtml(r.subject)}</div>
        <div class="ss-card__grade">
          <span class="ss-grade ss-grade--${r.color}">${r.grade}</span>
          <span class="ss-card__total">${r.total_score}/${r.max_score} points</span>
        </div>
        <div class="ss-dims">${barsHTML}</div>
        ${tipsHTML}
        <div class="ss-card__actions">
          <button type="button" class="ss-copy-btn" data-copy="${escAttr(r.subject)}">Copy Subject</button>
        </div>
      </div>`;
  }).join('');

  // Use winner button
  const useWinner = $('#ssUseWinner');
  useWinner.classList.remove('hidden');
  const useBtn = $('#ssUseBtn');
  useBtn.href = `/?subject=${encodeURIComponent(winner.subject)}`;
}

// ══════════════════════════════════════════════════════
//  COPY HANDLER
// ══════════════════════════════════════════════════════
document.addEventListener('click', e => {
  const btn = e.target.closest('.ss-winner-copy, .ss-copy-btn');
  if (!btn) return;
  const text = btn.dataset.copy || btn.textContent.trim();
  navigator.clipboard.writeText(text).then(() => {
    const orig = btn.textContent;
    btn.textContent = 'Copied!';
    setTimeout(() => { btn.textContent = orig; }, 1500);
  }).catch(() => {});
});

// ══════════════════════════════════════════════════════
//  SANITIZATION
// ══════════════════════════════════════════════════════
function escHtml(str) {
  return String(str ?? '')
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}
function escAttr(str) {
  return String(str ?? '').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}
