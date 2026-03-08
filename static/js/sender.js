/* ══════════════════════════════════════════════════════
   INBXR — Sender Reputation Page
   ══════════════════════════════════════════════════════ */

'use strict';

const $ = (sel, ctx = document) => ctx.querySelector(sel);
const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

// ── Loading message rotation ──────────────────────────
const LOADING_MSGS = [
  'Checking authentication records…',
  'Looking up SPF, DKIM, and DMARC…',
  'Scanning IP against blocklists…',
  'Checking domain reputation lists…',
  'Verifying reverse DNS and FCrDNS…',
  'Building your report…',
];
let loadingInterval = null;

function startLoading() {
  let idx = 0;
  const msgEl = $('#loadingMsg');
  msgEl.textContent = LOADING_MSGS[0];
  loadingInterval = setInterval(() => {
    idx = (idx + 1) % LOADING_MSGS.length;
    msgEl.textContent = LOADING_MSGS[idx];
  }, 2200);
}
function stopLoading() {
  clearInterval(loadingInterval);
}

// ── Color map ─────────────────────────────────────────
const COLOR_VAR = {
  green:  'var(--color-green)',
  blue:   'var(--color-blue)',
  yellow: 'var(--color-yellow)',
  orange: 'var(--color-orange)',
  red:    'var(--color-red)',
};

// ══════════════════════════════════════════════════════
//  FORM SUBMIT
// ══════════════════════════════════════════════════════
$('#senderForm').addEventListener('submit', async e => {
  e.preventDefault();

  const domain   = $('#domain').value.trim();
  const ip       = $('#sender_ip').value.trim();
  const selector = $('#dkim_selector').value.trim();

  if (!domain) {
    $('#domain').focus();
    $('#domain').style.borderColor = 'var(--color-red)';
    return;
  }
  $('#domain').style.borderColor = '';

  const submitBtn = $('#submitBtn');
  submitBtn.disabled = true;
  $('.btn-text', submitBtn).textContent = 'Checking…';
  $('.btn-spinner', submitBtn).classList.remove('hidden');

  // Show loading, hide everything else
  $('#senderResults').classList.add('hidden');
  $('#senderLoading').classList.remove('hidden');
  startLoading();

  try {
    const res  = await fetch('/check-reputation', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ domain, sender_ip: ip || null, dkim_selector: selector || null }),
    });
    const data = await res.json();

    stopLoading();
    $('#senderLoading').classList.add('hidden');

    if (!res.ok || data.error) {
      showError(data.error || 'Check failed. Please try again.');
      return;
    }

    renderResults(data);
  } catch (err) {
    stopLoading();
    $('#senderLoading').classList.add('hidden');
    showError('Network error. Check your connection and try again.');
  } finally {
    submitBtn.disabled = false;
    $('.btn-text', submitBtn).textContent = 'Run Reputation Check';
    $('.btn-spinner', submitBtn).classList.add('hidden');
  }
});

$('#runAgainBtn').addEventListener('click', () => {
  $('#senderResults').classList.add('hidden');
  $('#domain').focus();
});

// ══════════════════════════════════════════════════════
//  RENDER RESULTS
// ══════════════════════════════════════════════════════
function renderResults(data) {
  const { auth, reputation, combined, recommendations, meta } = data;

  // ── Combined card ──
  const combinedColor = COLOR_VAR[combined.color] || 'var(--color-blue)';
  const combinedCard  = $('#combinedCard');
  combinedCard.style.borderTopColor = combinedColor;

  $('#combinedMeta').innerHTML = [
    meta.domain            ? `<span class="meta-chip"><strong>${escHtml(meta.domain)}</strong></span>` : '',
    meta.sender_ip         ? `<span class="meta-chip"><strong>${escHtml(meta.sender_ip)}</strong> IP</span>` : '',
    meta.dkim_selector     ? `<span class="meta-chip">DKIM: <strong>${escHtml(meta.dkim_selector)}</strong></span>` : '',
    meta.checks_run        ? `<span class="meta-chip">${meta.checks_run} checks</span>` : '',
    meta.elapsed_ms        ? `<span class="meta-chip">${(meta.elapsed_ms / 1000).toFixed(1)}s</span>` : '',
  ].filter(Boolean).join('');

  const badge = $('#combinedBadge');
  badge.textContent  = combined.label;
  badge.className    = `combined-badge badge--${combined.color}`;
  badge.style.borderColor = combinedColor;

  $('#combinedSummary').textContent = buildCombinedSummary(auth, reputation);

  // Auth gauge
  animateGauge('authGaugeFill', 'authGaugeNum', auth.score, COLOR_VAR[auth.color]);
  const authLabelEl = $('#authLabel');
  authLabelEl.textContent  = auth.label;
  authLabelEl.className    = `mini-gauge-badge badge--${auth.color}`;

  // Reputation gauge
  animateGauge('repGaugeFill', 'repGaugeNum', reputation.score, COLOR_VAR[reputation.color]);
  const repLabelEl = $('#repLabel');
  repLabelEl.textContent = reputation.label;
  repLabelEl.className   = `mini-gauge-badge badge--${reputation.color}`;

  // ── Auth grid ──
  renderAuthGrid(auth.categories);

  // ── DNSBL table ──
  renderDnsblTable(reputation.dnsbl, reputation.listed_count);

  // ── Reputation signals ──
  renderRepSignals(reputation, meta);

  // ── Recommendations ──
  renderRecommendations(recommendations);

  $('#senderResults').classList.remove('hidden');
  $('#senderResults').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ── Combined summary text ─────────────────────────────
function buildCombinedSummary(auth, rep) {
  const parts = [];
  const cats  = auth.categories || [];

  const spf   = cats.find(c => c.label === 'SPF');
  const dkim  = cats.find(c => c.label === 'DKIM');
  const dmarc = cats.find(c => c.label === 'DMARC');
  const bimi  = cats.find(c => c.label === 'BIMI');

  const missing = [spf, dkim, dmarc].filter(c => c && c.status === 'missing').map(c => c.label);
  if (missing.length) parts.push(`Missing: ${missing.join(', ')}.`);

  const dmarc_policy = dmarc?.policy;
  if (dmarc_policy === 'none')        parts.push('DMARC is monitoring-only (p=none).');
  else if (dmarc_policy === 'quarantine') parts.push('DMARC policy: quarantine.');
  else if (dmarc_policy === 'reject')     parts.push('DMARC policy: reject (optimal).');

  if (rep.listed_count > 0) {
    parts.push(`Listed on ${rep.listed_count} blocklist${rep.listed_count !== 1 ? 's' : ''}.`);
  } else {
    parts.push('IP and domain are clean across all checked blocklists.');
  }

  if (rep.ptr?.found && rep.fcrdns?.valid) {
    parts.push('PTR and FCrDNS verified.');
  } else if (!rep.ptr?.found && rep.ptr?.checked) {
    parts.push('No PTR record — impacts reputation with some providers.');
  }

  return parts.join(' ') || 'Authentication and reputation check complete.';
}

// ── Authentication grid ───────────────────────────────
const STATUS_ICON = { pass: '✓', warning: '⚠', fail: '✗', missing: '✗', info: 'ℹ' };
const STATUS_LABEL = { pass: 'Configured', warning: 'Needs Work', fail: 'Failed', missing: 'Not Found', info: 'Info' };

function renderAuthGrid(categories) {
  const grid = $('#authGrid');
  if (!categories?.length) { grid.innerHTML = ''; return; }

  grid.innerHTML = categories.map(cat => {
    const st   = cat.status || 'missing';
    const icon = STATUS_ICON[st]  || '?';
    const lbl  = STATUS_LABEL[st] || st;

    const issues = (cat.issues || []).filter(i => i);
    const record = cat.record;

    const detailsId = `auth-detail-${cat.label}`;

    return `
      <div class="auth-card auth-card--${st}">
        <div class="auth-card__header">
          <span class="auth-status-icon auth-status-icon--${st}">${icon}</span>
          <div class="auth-card__titles">
            <span class="auth-card__name">${escHtml(cat.label)}</span>
            <span class="auth-card__status">${lbl}</span>
          </div>
          <span class="auth-card__score">${cat.score}/${cat.max}</span>
        </div>

        ${record ? `
          <button class="auth-detail-toggle" data-target="${detailsId}">
            Show record <span class="accordion-arrow">▼</span>
          </button>
          <div class="auth-detail hidden" id="${detailsId}">
            <code class="auth-record-code">${escHtml(record)}</code>
            ${cat.selector ? `<span class="auth-selector-note">Selector: ${escHtml(cat.selector)}</span>` : ''}
            ${cat.policy   ? `<span class="auth-selector-note">Policy: p=${escHtml(cat.policy)}${cat.pct != null ? ` · pct=${cat.pct}%` : ''}</span>` : ''}
          </div>` : ''}

        ${issues.length ? `
          <ul class="auth-issues">
            ${issues.map(i => `<li>${escHtml(i)}</li>`).join('')}
          </ul>` : ''}

        ${!record && cat.label === 'BIMI' ? `
          <p class="auth-bimi-note">Requires p=quarantine or p=reject DMARC policy. Optional but shows your logo in supported inboxes (Gmail, Yahoo, Apple Mail).</p>` : ''}
      </div>`;
  }).join('');

  // Accordion toggles within auth cards
  $$('.auth-detail-toggle').forEach(btn => {
    btn.addEventListener('click', () => {
      const detail = $(`#${btn.dataset.target}`);
      if (!detail) return;
      const open = detail.classList.toggle('hidden') === false;
      const arrow = $('.accordion-arrow', btn);
      if (arrow) arrow.style.transform = open ? 'rotate(180deg)' : '';
    });
  });
}

// ── DNSBL table ───────────────────────────────────────
const WEIGHT_LABEL = { critical: 'Critical', major: 'High', moderate: 'Medium', minor: 'Low' };

function renderDnsblTable(dnsbl, listedCount) {
  const summary = $('#dnsblSummary');
  const body    = $('#dnsblBody');

  if (!dnsbl?.length) {
    summary.textContent = '(no IP provided — domain lists only)';
    body.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--text-hint);padding:16px">No blocklist data available.</td></tr>';
    return;
  }

  if (listedCount === 0) {
    summary.innerHTML = '<span class="dnsbl-clean-badge">✓ Clean on all lists</span>';
  } else {
    summary.innerHTML = `<span class="dnsbl-listed-badge">⚠ Listed on ${listedCount} list${listedCount !== 1 ? 's' : ''}</span>`;
  }

  body.innerHTML = dnsbl.map(row => {
    const listed = row.listed;
    const statusCls = listed ? 'dnsbl-status--listed' : 'dnsbl-status--clean';
    const statusTxt = listed ? '✗ Listed'             : '✓ Clean';
    const reason    = listed && row.reason ? `<br><small class="dnsbl-reason">${escHtml(row.reason.slice(0, 120))}</small>` : '';
    const errNote   = row.error ? `<small class="dnsbl-error">lookup error</small>` : '';
    const wlabel    = WEIGHT_LABEL[row.weight] || row.weight;

    return `
      <tr class="${listed ? 'dnsbl-row--listed' : ''}">
        <td><span class="dnsbl-status ${statusCls}">${statusTxt}</span>${reason}${errNote}</td>
        <td>
          <span class="dnsbl-name">${escHtml(row.name)}</span>
          <small class="dnsbl-zone">${escHtml(row.zone)}</small>
        </td>
        <td><span class="type-pill">${row.type === 'ip' ? 'IP' : 'Domain'}</span></td>
        <td><span class="weight-pill weight-pill--${row.weight}">${wlabel}</span></td>
        <td class="dnsbl-info-cell">${escHtml(row.info || '')}</td>
      </tr>`;
  }).join('');
}

// ── Reputation signals ────────────────────────────────
function renderRepSignals(reputation, meta) {
  const container = $('#repSignals');
  const rows = [];

  if (meta.sender_ip) {
    // PTR
    const ptr = reputation.ptr || {};
    if (ptr.checked) {
      rows.push({
        label: 'Reverse DNS (PTR)',
        status: ptr.found ? 'pass' : 'fail',
        value: ptr.found ? ptr.hostname : 'No PTR record found',
        note: ptr.found ? null : 'Contact your hosting provider or ISP to set a PTR record for this IP.',
      });
    }
    // FCrDNS
    const fcr = reputation.fcrdns || {};
    if (fcr.checked) {
      rows.push({
        label: 'FCrDNS (forward-confirmed)',
        status: fcr.valid ? 'pass' : (reputation.ptr?.found ? 'fail' : 'info'),
        value: fcr.valid
          ? `Verified — PTR resolves back to ${meta.sender_ip}`
          : (fcr.resolved?.length ? `Mismatch — PTR resolves to: ${fcr.resolved.join(', ')}` : 'Could not verify'),
        note: fcr.valid ? null : 'PTR hostname must resolve back to the same IP. Fix the A record of your mail hostname.',
      });
    }
  } else {
    rows.push({
      label: 'Reverse DNS (PTR)',
      status: 'info',
      value: 'Enter a sending IP to check PTR and FCrDNS',
      note: null,
    });
  }

  // MX records
  const mx = reputation.mx || {};
  rows.push({
    label: 'MX Records',
    status: mx.found ? 'pass' : 'warning',
    value: mx.found
      ? mx.records.slice(0, 3).map(r => r[1]).join(', ')
      : 'No MX records found',
    note: mx.found ? null : 'No MX records found for this domain. This may affect deliverability if recipients try to verify your domain.',
  });

  container.innerHTML = rows.map(r => `
    <div class="rep-signal-row">
      <span class="rep-signal-icon auth-status-icon--${r.status}">${STATUS_ICON[r.status] || 'ℹ'}</span>
      <div class="rep-signal-body">
        <span class="rep-signal-label">${escHtml(r.label)}</span>
        <span class="rep-signal-value">${escHtml(r.value)}</span>
        ${r.note ? `<span class="rep-signal-note">${escHtml(r.note)}</span>` : ''}
      </div>
    </div>`).join('');
}

// ── Recommendations ───────────────────────────────────
function renderRecommendations(recs) {
  const container = $('#senderRecList');
  if (!recs?.length) {
    container.innerHTML = '<p style="font-size:0.85rem;color:var(--color-green);padding:8px 0">✓ No issues found. Your sender configuration looks healthy.</p>';
    return;
  }
  container.innerHTML = recs.map(rec => `
    <div class="rec-item">
      <div class="rec-item__header">
        <span class="rec-item__cat">${escHtml(rec.category)}</span>
        <button class="copy-btn" data-copy="${escAttr(rec.recommendation)}">Copy</button>
      </div>
      <div class="rec-item__issue">${escHtml(rec.item)}</div>
      <div class="rec-item__text">${escHtml(rec.recommendation)}</div>
    </div>`).join('');
}

// ── Gauge animator ────────────────────────────────────
function animateGauge(fillId, numId, score, color) {
  const ARC  = 173;
  const fill = $(`#${fillId}`);
  const num  = $(`#${numId}`);
  if (!fill || !num) return;

  fill.style.stroke = color;

  let current = 0;
  const step = () => {
    current = Math.min(current + Math.ceil(score / 28), score);
    num.textContent = current;
    if (current < score) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
  setTimeout(() => { fill.style.strokeDasharray = `${(score / 100) * ARC} ${ARC}`; }, 80);
}

// ── Copy-to-clipboard ─────────────────────────────────
document.addEventListener('click', e => {
  const btn = e.target.closest('.copy-btn');
  if (!btn) return;
  const text = btn.dataset.copy || '';
  navigator.clipboard.writeText(text).then(() => {
    const orig = btn.textContent;
    btn.textContent = 'Copied!';
    setTimeout(() => { btn.textContent = orig; }, 1500);
  }).catch(() => {});
});

// ── Error display ─────────────────────────────────────
function showError(msg) {
  const el = document.createElement('div');
  el.className = 'sender-error';
  el.innerHTML = `<strong>Error:</strong> ${escHtml(msg)}`;
  const existing = $('.sender-error');
  if (existing) existing.remove();
  $('#formCard').after(el);
  setTimeout(() => el.remove(), 8000);
}

// ── Sanitization ──────────────────────────────────────
function escHtml(str) {
  return String(str ?? '')
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}
function escAttr(str) {
  return String(str ?? '').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}
