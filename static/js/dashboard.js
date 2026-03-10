/* ══════════════════════════════════════════════════════
   INBXR — Dashboard (Score History & Trends)
   ══════════════════════════════════════════════════════ */

'use strict';

const $ = (sel, ctx = document) => ctx.querySelector(sel);
const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

const STORAGE_KEY = 'inbxr_history';
const MAX_HISTORY = 50;

// ══════════════════════════════════════════════════════
//  STORAGE
// ══════════════════════════════════════════════════════
function loadHistory() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch { return []; }
}

function clearHistory() {
  localStorage.removeItem(STORAGE_KEY);
}

// ══════════════════════════════════════════════════════
//  INIT
// ══════════════════════════════════════════════════════
function init() {
  const history = loadHistory();

  if (!history.length) {
    $('#dbEmpty').classList.remove('hidden');
    $('#dbContent').classList.add('hidden');
    return;
  }

  $('#dbEmpty').classList.add('hidden');
  $('#dbContent').classList.remove('hidden');

  renderStats(history);
  renderChart(history);
  renderStreak(history);
  renderRecent(history);
}

// ══════════════════════════════════════════════════════
//  STATS ROW
// ══════════════════════════════════════════════════════
function renderStats(history) {
  const total = history.length;
  const spamScores = history.map(h => h.spam_score).filter(s => s != null);
  const copyScores = history.map(h => h.copy_score).filter(s => s != null);

  const avgSpam = spamScores.length ? Math.round(spamScores.reduce((a, b) => a + b, 0) / spamScores.length) : 0;
  const avgCopy = copyScores.length ? Math.round(copyScores.reduce((a, b) => a + b, 0) / copyScores.length) : 0;

  // Improvement: compare last 5 vs first 5
  let spamTrend = '';
  let copyTrend = '';
  if (spamScores.length >= 4) {
    const recent = spamScores.slice(-3);
    const early = spamScores.slice(0, 3);
    const recentAvg = recent.reduce((a, b) => a + b, 0) / recent.length;
    const earlyAvg = early.reduce((a, b) => a + b, 0) / early.length;
    const diff = Math.round(earlyAvg - recentAvg); // lower spam = better
    if (diff > 3) spamTrend = `<span class="db-trend db-trend--good">&#9660; ${diff} pts</span>`;
    else if (diff < -3) spamTrend = `<span class="db-trend db-trend--bad">&#9650; ${Math.abs(diff)} pts</span>`;
  }
  if (copyScores.length >= 4) {
    const recent = copyScores.slice(-3);
    const early = copyScores.slice(0, 3);
    const recentAvg = recent.reduce((a, b) => a + b, 0) / recent.length;
    const earlyAvg = early.reduce((a, b) => a + b, 0) / early.length;
    const diff = Math.round(recentAvg - earlyAvg); // higher copy = better
    if (diff > 3) copyTrend = `<span class="db-trend db-trend--good">&#9650; ${diff} pts</span>`;
    else if (diff < -3) copyTrend = `<span class="db-trend db-trend--bad">&#9660; ${Math.abs(diff)} pts</span>`;
  }

  // Best audit verdict
  const verdicts = history.filter(h => h.verdict).map(h => h.verdict);
  const verdictOrder = ['ready', 'mostly_ready', 'review', 'fix_needed', 'not_ready'];
  let bestVerdict = 'N/A';
  for (const v of verdictOrder) {
    if (verdicts.includes(v)) { bestVerdict = v.replace('_', ' '); break; }
  }

  $('#dbStats').innerHTML = `
    <div class="db-stat-card">
      <span class="db-stat__num">${total}</span>
      <span class="db-stat__label">Total Analyses</span>
    </div>
    <div class="db-stat-card">
      <span class="db-stat__num">${avgSpam}</span>
      <span class="db-stat__label">Avg Spam Risk ${spamTrend}</span>
    </div>
    <div class="db-stat-card">
      <span class="db-stat__num">${avgCopy}</span>
      <span class="db-stat__label">Avg Copy Score ${copyTrend}</span>
    </div>
    <div class="db-stat-card">
      <span class="db-stat__num db-stat__num--small">${esc(bestVerdict)}</span>
      <span class="db-stat__label">Best Audit Verdict</span>
    </div>
  `;
}

// ══════════════════════════════════════════════════════
//  SCORE TREND CHART (pure CSS bars)
// ══════════════════════════════════════════════════════
function renderChart(history) {
  const container = $('#dbChart');
  const items = history.slice(-20); // last 20

  if (items.length < 2) {
    container.innerHTML = '<p style="text-align:center;color:var(--text-3);font-size:0.82rem;padding:24px">Need at least 2 analyses to show trends</p>';
    return;
  }

  const maxScore = 100;

  container.innerHTML = `
    <div class="db-chart__bars">
      ${items.map((item, i) => {
        const spamH = (item.spam_score / maxScore) * 100;
        const copyH = (item.copy_score / maxScore) * 100;
        const date = _shortDate(item.date);
        return `
          <div class="db-chart__group" style="animation-delay:${i * 40}ms" title="${esc(item.subject || 'Untitled')} — Spam: ${item.spam_score}, Copy: ${item.copy_score}">
            <div class="db-chart__bar-pair">
              <div class="db-chart__bar db-chart__bar--spam" style="height:${spamH}%"></div>
              <div class="db-chart__bar db-chart__bar--copy" style="height:${copyH}%"></div>
            </div>
            <span class="db-chart__date">${date}</span>
          </div>`;
      }).join('')}
    </div>
    <div class="db-chart__yaxis">
      <span>100</span><span>75</span><span>50</span><span>25</span><span>0</span>
    </div>
  `;
}

function _shortDate(dateStr) {
  try {
    const d = new Date(dateStr);
    return `${d.getMonth() + 1}/${d.getDate()}`;
  } catch { return ''; }
}

// ══════════════════════════════════════════════════════
//  STREAK
// ══════════════════════════════════════════════════════
function renderStreak(history) {
  const el = $('#dbStreak');
  if (history.length < 2) { el.classList.add('hidden'); return; }

  // Count consecutive analyses where spam < 30 (good score)
  let streak = 0;
  for (let i = history.length - 1; i >= 0; i--) {
    if (history[i].spam_score != null && history[i].spam_score < 30) {
      streak++;
    } else break;
  }

  if (streak >= 2) {
    el.classList.remove('hidden');
    const level = streak >= 10 ? 'master' : streak >= 5 ? 'pro' : 'good';
    const labels = { good: 'On a Roll', pro: 'Inbox Pro', master: 'Deliverability Master' };
    const icons = { good: '&#9889;', pro: '&#11088;', master: '&#128081;' };

    el.innerHTML = `
      <div class="db-streak-card db-streak-card--${level}">
        <span class="db-streak__icon">${icons[level]}</span>
        <div class="db-streak__text">
          <span class="db-streak__label">${labels[level]}</span>
          <span class="db-streak__detail">${streak} consecutive emails with low spam risk (&lt;30)</span>
        </div>
      </div>
    `;
  } else {
    el.classList.add('hidden');
  }
}

// ══════════════════════════════════════════════════════
//  RECENT ANALYSES LIST
// ══════════════════════════════════════════════════════
function renderRecent(history) {
  const container = $('#dbRecentList');
  const items = [...history].reverse().slice(0, 20); // newest first

  container.innerHTML = items.map((item, i) => {
    const spamColor = item.spam_score <= 25 ? 'green' : item.spam_score <= 50 ? 'yellow' : 'red';
    const copyColor = item.copy_score >= 70 ? 'green' : item.copy_score >= 40 ? 'blue' : 'red';
    const date = _formatDate(item.date);
    const verdictBadge = item.verdict
      ? `<span class="db-verdict db-verdict--${item.verdict}">${esc(item.verdict_label || item.verdict)}</span>`
      : '';

    return `
      <div class="db-recent-item" style="animation-delay:${i * 30}ms">
        <div class="db-recent-item__main">
          <span class="db-recent-item__subject">${esc(item.subject || 'Untitled')}</span>
          <span class="db-recent-item__meta">${esc(item.sender || '')} &middot; ${esc(item.industry || '')} &middot; ${date}</span>
        </div>
        <div class="db-recent-item__scores">
          <span class="db-recent-score db-recent-score--${spamColor}" title="Spam Risk">
            <small>Spam</small>${item.spam_score ?? '—'}
          </span>
          <span class="db-recent-score db-recent-score--${copyColor}" title="Copy Score">
            <small>Copy</small>${item.copy_score ?? '—'}
          </span>
          ${verdictBadge}
        </div>
        <a class="db-recent-item__rerun" href="/?subject=${encodeURIComponent(item.subject || '')}&sender=${encodeURIComponent(item.sender || '')}" title="Re-analyze">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 105.13-11.23L1 10"/></svg>
        </a>
      </div>`;
  }).join('');
}

function _formatDate(dateStr) {
  try {
    const d = new Date(dateStr);
    const now = new Date();
    const diff = now - d;
    if (diff < 60000) return 'Just now';
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
    if (diff < 604800000) return `${Math.floor(diff / 86400000)}d ago`;
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  } catch { return ''; }
}

// ══════════════════════════════════════════════════════
//  CLEAR HISTORY
// ══════════════════════════════════════════════════════
$('#dbClearBtn').addEventListener('click', () => {
  if (!confirm('Clear all analysis history? This cannot be undone.')) return;
  clearHistory();
  init();
});

// ══════════════════════════════════════════════════════
//  SANITIZATION
// ══════════════════════════════════════════════════════
function esc(str) {
  return String(str ?? '')
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

// ── Boot ──
init();
