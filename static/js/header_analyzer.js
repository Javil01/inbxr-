/* ==============================================================
   InbXr — Email Header Analyzer Page
   ============================================================== */

'use strict';

const $ = (sel, ctx = document) => ctx.querySelector(sel);
const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

// ── Loading message rotation ──────────────────────────
const LOADING_MSGS = [
  'Parsing email headers...',
  'Extracting authentication results...',
  'Tracing routing path...',
  'Analyzing DKIM signature...',
  'Checking TLS encryption...',
  'Building your report...',
];
let loadingInterval = null;

function startLoading() {
  let idx = 0;
  const msgEl = $('#loadingMsg');
  msgEl.textContent = LOADING_MSGS[0];
  loadingInterval = setInterval(() => {
    idx = (idx + 1) % LOADING_MSGS.length;
    msgEl.textContent = LOADING_MSGS[idx];
  }, 1800);
}
function stopLoading() {
  clearInterval(loadingInterval);
}

// ── Status helpers ────────────────────────────────────
const STATUS_ICON = { pass: '\u2713', warning: '\u26A0', fail: '\u2717', missing: '\u2717', info: '\u2139', unknown: '?' };

// ══════════════════════════════════════════════════════
//  FORM SUBMIT
// ══════════════════════════════════════════════════════
$('#headerForm').addEventListener('submit', async e => {
  e.preventDefault();

  const headers = $('#rawHeaders').value.trim();
  if (!headers) {
    $('#rawHeaders').focus();
    $('#rawHeaders').style.borderColor = 'var(--color-red)';
    return;
  }
  $('#rawHeaders').style.borderColor = '';

  const submitBtn = $('#submitBtn');
  submitBtn.disabled = true;
  $('.btn-text', submitBtn).textContent = 'Analyzing...';
  $('.btn-spinner', submitBtn).classList.remove('hidden');

  $('#haResults').classList.add('hidden');
  $('#haLoading').classList.remove('hidden');
  startLoading();

  try {
    const res = await fetch('/analyze-headers', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ headers }),
    });
    const data = await res.json();

    stopLoading();
    $('#haLoading').classList.add('hidden');

    if (!res.ok || data.error) {
      showError(data.error || 'Analysis failed. Please try again.');
      return;
    }

    renderResults(data);
  } catch (err) {
    stopLoading();
    $('#haLoading').classList.add('hidden');
    showError('Network error. Check your connection and try again.');
  } finally {
    submitBtn.disabled = false;
    $('.btn-text', submitBtn).textContent = 'Analyze Headers';
    $('.btn-spinner', submitBtn).classList.add('hidden');
  }
});

$('#runAgainBtn').addEventListener('click', () => {
  $('#haResults').classList.add('hidden');
  $('#rawHeaders').focus();
});

// ── Raw headers toggle ────────────────────────────────
$('#rawToggle').addEventListener('click', () => {
  const section = $('#rawParsedSection');
  const open = section.classList.toggle('hidden') === false;
  const arrow = $('.accordion-arrow', $('#rawToggle'));
  if (arrow) arrow.style.transform = open ? 'rotate(180deg)' : '';
});

// ══════════════════════════════════════════════════════
//  RENDER RESULTS
// ══════════════════════════════════════════════════════
function renderResults(data) {
  const { authentication_results, received_chain, tls_info, dkim_signature, envelope, x_headers, summary, all_headers } = data;

  // ── Summary card ──
  renderSummary(summary, tls_info);

  // ── Envelope ──
  renderEnvelope(envelope);

  // ── Authentication Results ──
  renderAuthResults(authentication_results);

  // ── DKIM Signature ──
  renderDkimDetails(dkim_signature);

  // ── Routing Path ──
  renderRoutingPath(received_chain);

  // ── X-Headers ──
  renderXHeaders(x_headers);

  // ── Raw Parsed Headers ──
  renderRawHeaders(all_headers);

  $('#haResults').classList.remove('hidden');
  $('#haResults').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ── Summary card ──────────────────────────────────────
function renderSummary(summary, tls_info) {
  const card = $('#summaryCard');
  const allEncrypted = summary.all_encrypted;
  const authPasses = summary.auth_pass_count || 0;
  const authFails = summary.auth_fail_count || 0;

  let color = 'green';
  let label = 'Healthy';
  if (authFails > 0 && authPasses === 0) { color = 'red'; label = 'Critical Issues'; }
  else if (authFails > 0) { color = 'yellow'; label = 'Some Failures'; }
  else if (!allEncrypted) { color = 'yellow'; label = 'Encryption Gap'; }

  card.style.borderTopColor = `var(--color-${color})`;

  $('#summaryMeta').innerHTML = [
    `<span class="meta-chip">${summary.total_hops} hop${summary.total_hops !== 1 ? 's' : ''}</span>`,
    `<span class="meta-chip">${allEncrypted ? 'All Encrypted' : 'Unencrypted Hops'}</span>`,
    summary.total_delay_seconds != null ? `<span class="meta-chip">${formatDelay(summary.total_delay_seconds)} total delay</span>` : '',
    `<span class="meta-chip">${authPasses} auth pass${authPasses !== 1 ? 'es' : ''}</span>`,
    authFails > 0 ? `<span class="meta-chip">${authFails} auth fail${authFails !== 1 ? 's' : ''}</span>` : '',
  ].filter(Boolean).join('');

  const badge = $('#summaryBadge');
  badge.textContent = label;
  badge.className = `combined-badge badge--${color}`;
  badge.style.borderColor = `var(--color-${color})`;

  const parts = [];
  parts.push(`Email traversed ${summary.total_hops} hop${summary.total_hops !== 1 ? 's' : ''}.`);
  if (allEncrypted) parts.push('All hops used TLS encryption.');
  else parts.push('Some hops were not encrypted in transit.');
  if (authPasses > 0) parts.push(`${authPasses} authentication check${authPasses !== 1 ? 's' : ''} passed.`);
  if (authFails > 0) parts.push(`${authFails} authentication check${authFails !== 1 ? 's' : ''} failed.`);
  $('#summarySummary').textContent = parts.join(' ');
}

// ── Envelope ──────────────────────────────────────────
function renderEnvelope(envelope) {
  const container = $('#envelopeInfo');
  if (!envelope) { container.innerHTML = ''; return; }

  const fields = [
    { label: 'From', value: envelope.from },
    { label: 'To', value: envelope.to },
    { label: 'Subject', value: envelope.subject },
    { label: 'Date', value: envelope.date },
    { label: 'Message-ID', value: envelope.message_id },
    { label: 'Reply-To', value: envelope.reply_to },
  ].filter(f => f.value);

  container.innerHTML = fields.map(f => `
    <div class="rep-signal-row">
      <span class="rep-signal-icon auth-status-icon--info">${STATUS_ICON.info}</span>
      <div class="rep-signal-body">
        <span class="rep-signal-label">${escHtml(f.label)}</span>
        <span class="rep-signal-value">${escHtml(f.value)}</span>
      </div>
    </div>`).join('');
}

// ── Authentication Results ────────────────────────────
function renderAuthResults(authResults) {
  const grid = $('#authResults');
  if (!authResults || (!authResults.spf && !authResults.dkim && !authResults.dmarc)) {
    grid.innerHTML = '<p style="font-size:0.85rem;color:var(--text-hint);padding:8px 0">No Authentication-Results header found in these headers.</p>';
    return;
  }

  const checks = [
    { label: 'SPF', result: authResults.spf },
    { label: 'DKIM', result: authResults.dkim },
    { label: 'DMARC', result: authResults.dmarc },
  ];

  grid.innerHTML = checks.map(c => {
    const verdict = c.result || 'not found';
    const st = verdict === 'pass' ? 'pass' : (verdict === 'not found' ? 'missing' : 'fail');
    const icon = STATUS_ICON[st] || '?';
    const statusLabel = verdict === 'pass' ? 'Pass' : (verdict === 'not found' ? 'Not Found' : verdict.charAt(0).toUpperCase() + verdict.slice(1));

    return `
      <div class="auth-card auth-card--${st}">
        <div class="auth-card__header">
          <span class="auth-status-icon auth-status-icon--${st}">${icon}</span>
          <div class="auth-card__titles">
            <span class="auth-card__name">${escHtml(c.label)}</span>
            <span class="auth-card__status">${escHtml(statusLabel)}</span>
          </div>
        </div>
      </div>`;
  }).join('');
}

// ── DKIM Signature Details ────────────────────────────
function renderDkimDetails(dkim) {
  const section = $('#dkimSection');
  const container = $('#dkimDetails');

  if (!dkim || !dkim.domain) {
    section.classList.add('hidden');
    return;
  }

  section.classList.remove('hidden');
  const rows = [
    { label: 'Signing Domain (d=)', value: dkim.domain },
    { label: 'Selector (s=)', value: dkim.selector },
    { label: 'Algorithm (a=)', value: dkim.algorithm },
    { label: 'Header Fields (h=)', value: dkim.header_fields },
    { label: 'Body Hash (bh=)', value: dkim.body_hash },
  ].filter(r => r.value);

  container.innerHTML = rows.map(r => `
    <div class="rep-signal-row">
      <span class="rep-signal-icon auth-status-icon--info">${STATUS_ICON.info}</span>
      <div class="rep-signal-body">
        <span class="rep-signal-label">${escHtml(r.label)}</span>
        <span class="rep-signal-value" style="font-family:'SF Mono','Fira Code',monospace;font-size:0.8rem;word-break:break-all">${escHtml(r.value)}</span>
      </div>
    </div>`).join('');
}

// ── Routing Path ──────────────────────────────────────
function renderRoutingPath(chain) {
  const container = $('#routingPath');
  if (!chain || !chain.length) {
    container.innerHTML = '<p style="font-size:0.85rem;color:var(--text-hint);padding:8px 0">No Received headers found.</p>';
    return;
  }

  container.innerHTML = chain.map((hop, i) => {
    const encrypted = hop.encrypted;
    const encClass = encrypted ? 'et-hop__encrypted--yes' : 'et-hop__encrypted--no';
    const encLabel = encrypted ? 'TLS' : 'PLAIN';

    const fromServer = hop.from_server || 'unknown';
    const byServer = hop.by_server || 'unknown';
    const protocol = hop.protocol || '';
    const timestamp = hop.timestamp || '';
    const delay = hop.delay_seconds;

    let detail = `${escHtml(fromServer)} → ${escHtml(byServer)}`;
    if (protocol) detail += ` (${escHtml(protocol)})`;
    if (timestamp) detail += ` at ${escHtml(timestamp)}`;

    let delayStr = '';
    if (delay != null && delay > 0) {
      delayStr = `<span class="et-hop__ip">+${formatDelay(delay)} delay</span>`;
    }

    return `
      <div class="et-hop">
        <span class="et-hop__num">${i + 1}</span>
        <span class="et-hop__encrypted ${encClass}">${encLabel}</span>
        <span class="et-hop__detail">${detail}</span>
        ${delayStr}
      </div>`;
  }).join('');
}

// ── X-Headers ─────────────────────────────────────────
function renderXHeaders(xHeaders) {
  const section = $('#xHeadersSection');
  const body = $('#xHeadersBody');

  if (!xHeaders || !Object.keys(xHeaders).length) {
    section.classList.add('hidden');
    return;
  }

  section.classList.remove('hidden');
  body.innerHTML = Object.entries(xHeaders).map(([key, value]) => `
    <tr>
      <td><span class="dnsbl-name" style="font-family:'SF Mono','Fira Code',monospace;font-size:0.78rem">${escHtml(key)}</span></td>
      <td style="font-size:0.78rem;word-break:break-all;max-width:500px">${escHtml(String(value).slice(0, 500))}</td>
    </tr>`).join('');
}

// ── Raw Parsed Headers ────────────────────────────────
function renderRawHeaders(allHeaders) {
  const body = $('#rawHeadersBody');
  if (!allHeaders || !allHeaders.length) {
    body.innerHTML = '<tr><td colspan="2" style="text-align:center;color:var(--text-hint);padding:16px">No headers parsed.</td></tr>';
    return;
  }

  body.innerHTML = allHeaders.map(h => `
    <tr>
      <td><span class="dnsbl-name" style="font-family:'SF Mono','Fira Code',monospace;font-size:0.78rem">${escHtml(h[0])}</span></td>
      <td style="font-size:0.78rem;word-break:break-all;max-width:500px">${escHtml(String(h[1]).slice(0, 1000))}</td>
    </tr>`).join('');
}

// ── Helpers ───────────────────────────────────────────
function formatDelay(seconds) {
  if (seconds == null) return '0s';
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ${Math.round(seconds % 60)}s`;
  const h = Math.floor(seconds / 3600);
  const m = Math.round((seconds % 3600) / 60);
  return `${h}h ${m}m`;
}

function showError(msg) {
  const el = document.createElement('div');
  el.className = 'sender-error';
  el.innerHTML = `<strong>Error:</strong> ${escHtml(msg)}`;
  const existing = $('.sender-error');
  if (existing) existing.remove();
  $('#formCard').after(el);
  setTimeout(() => el.remove(), 8000);
}

function escHtml(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
