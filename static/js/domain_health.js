/* ==============================================================
   InbXr — Domain Health Report Page
   ============================================================== */

'use strict';

const $ = (sel, ctx = document) => ctx.querySelector(sel);
const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

// ── Loading message rotation ──────────────────────────
const LOADING_MSGS = [
  'Running domain health checks...',
  'Checking authentication records...',
  'Scanning blocklists...',
  'Validating BIMI configuration...',
  'Looking up MX records...',
  'Checking SSL and transport security...',
  'Computing overall grade...',
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

// ── Color/status maps ─────────────────────────────────
const COLOR_VAR = {
  green:  'var(--color-green)',
  blue:   'var(--color-blue)',
  yellow: 'var(--color-yellow)',
  orange: 'var(--color-orange)',
  red:    'var(--color-red)',
};

const STATUS_ICON  = { pass: '\u2713', warning: '\u26A0', fail: '\u2717', missing: '\u2717', info: '\u2139' };
const STATUS_LABEL = { pass: 'Configured', warning: 'Needs Work', fail: 'Failed', missing: 'Not Found', info: 'Info' };
const WEIGHT_LABEL = { critical: 'Critical', major: 'High', moderate: 'Medium', minor: 'Low' };

// ══════════════════════════════════════════════════════
//  FORM SUBMIT
// ══════════════════════════════════════════════════════
$('#domainHealthForm').addEventListener('submit', async e => {
  e.preventDefault();

  const domain   = $('#dhDomain').value.trim();
  const selector = $('#dhSelector').value.trim();

  if (!domain) {
    $('#dhDomain').focus();
    $('#dhDomain').style.borderColor = 'var(--color-red)';
    return;
  }
  $('#dhDomain').style.borderColor = '';

  const submitBtn = $('#submitBtn');
  submitBtn.disabled = true;
  $('.btn-text', submitBtn).textContent = 'Checking...';
  $('.btn-spinner', submitBtn).classList.remove('hidden');

  $('#dhResults').classList.add('hidden');
  $('#dhLoading').classList.remove('hidden');
  startLoading();

  try {
    const res = await fetch('/domain-health-check', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ domain, dkim_selector: selector || null }),
    });
    const data = await res.json();

    stopLoading();
    $('#dhLoading').classList.add('hidden');

    if (!res.ok || data.error) {
      showError(data.error || 'Health check failed. Please try again.');
      return;
    }

    renderResults(data, domain);
  } catch (err) {
    stopLoading();
    $('#dhLoading').classList.add('hidden');
    showError('Network error. Check your connection and try again.');
  } finally {
    submitBtn.disabled = false;
    $('.btn-text', submitBtn).textContent = 'Run Health Check';
    $('.btn-spinner', submitBtn).classList.add('hidden');
  }
});

$('#runAgainBtn').addEventListener('click', () => {
  $('#dhResults').classList.add('hidden');
  $('#dhDomain').focus();
});

// ══════════════════════════════════════════════════════
//  RENDER RESULTS
// ══════════════════════════════════════════════════════
function renderResults(data, domain) {
  // ── Overall Grade ──
  renderOverallGrade(data.grade, data.score, data.category_scores);

  // ── Category Cards ──
  renderCategoryCards(data.category_scores);

  // ── Auth Details ──
  renderAuthDetails(data.reputation);

  // ── Blocklist Scan ──
  renderBlocklists(data.reputation);

  // ── DNS Records ──
  renderDnsRecords(data.reputation, data.mx, data.bimi);

  // ── BIMI Details ──
  renderBimiDetails(data.bimi);

  // ── Recommendations ──
  renderRecommendations(data.recommendations);

  // ── Fix Records link ──
  const fixBtn = $('#generateFixBtn');
  if (fixBtn) {
    fixBtn.href = `/sender?domain=${encodeURIComponent(domain)}`;
  }

  $('#dhResults').classList.remove('hidden');
  $('#dhResults').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ── Overall grade card ────────────────────────────────
function renderOverallGrade(grade, score, categories) {
  const gradeEl = $('#overallGrade');
  const color = gradeColor(grade);
  gradeEl.style.borderLeftColor = `var(--color-${color})`;

  const letter = $('#gradeLetter');
  letter.textContent = grade;
  letter.style.color = `var(--color-${color})`;

  $('#gradeLabel').textContent = `Domain Health Score: ${score}/100`;

  const counts = $('#gradeCounts');
  if (categories) {
    counts.innerHTML = Object.entries(categories).map(([key, val]) => {
      const catColor = val.score >= val.max * 0.8 ? 'green' : (val.score >= val.max * 0.5 ? 'yellow' : 'red');
      return `<span class="et-count" style="background:rgba(var(--color-${catColor}-rgb, 99,102,241),0.1);color:var(--color-${catColor})">${escHtml(val.label)}: ${val.score}/${val.max}</span>`;
    }).join('');
  }
}

// ── Category cards ────────────────────────────────────
function renderCategoryCards(categories) {
  const grid = $('#categoryCards');
  if (!categories) { grid.innerHTML = ''; return; }

  grid.innerHTML = Object.entries(categories).map(([key, cat]) => {
    const pct = cat.max > 0 ? Math.round((cat.score / cat.max) * 100) : 0;
    const st = pct >= 80 ? 'pass' : (pct >= 50 ? 'warning' : 'fail');
    const icon = STATUS_ICON[st];

    return `
      <div class="auth-card auth-card--${st}">
        <div class="auth-card__header">
          <span class="auth-status-icon auth-status-icon--${st}">${icon}</span>
          <div class="auth-card__titles">
            <span class="auth-card__name">${escHtml(cat.label)}</span>
            <span class="auth-card__status">${pct}%</span>
          </div>
          <span class="auth-card__score">${cat.score}/${cat.max}</span>
        </div>
        ${cat.details ? `<ul class="auth-issues">${cat.details.map(d => `<li>${escHtml(d)}</li>`).join('')}</ul>` : ''}
      </div>`;
  }).join('');
}

// ── Auth Details ──────────────────────────────────────
function renderAuthDetails(reputation) {
  const grid = $('#authDetails');
  if (!reputation || !reputation.auth || !reputation.auth.categories) {
    grid.innerHTML = '<p style="font-size:0.85rem;color:var(--text-hint);padding:8px 0">No authentication data available.</p>';
    return;
  }

  const categories = reputation.auth.categories;
  grid.innerHTML = categories.map(cat => {
    const st = cat.status || 'missing';
    const icon = STATUS_ICON[st] || '?';
    const lbl = STATUS_LABEL[st] || st;
    const issues = (cat.issues || []).filter(i => i);
    const record = cat.record;
    const detailsId = `dh-auth-detail-${cat.label}`;

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
            Show record <span class="accordion-arrow">\u25BC</span>
          </button>
          <div class="auth-detail hidden" id="${detailsId}">
            <code class="auth-record-code">${escHtml(record)}</code>
            ${cat.selector ? `<span class="auth-selector-note">Selector: ${escHtml(cat.selector)}</span>` : ''}
            ${cat.policy ? `<span class="auth-selector-note">Policy: p=${escHtml(cat.policy)}${cat.pct != null ? ' \u00B7 pct=' + cat.pct + '%' : ''}</span>` : ''}
          </div>` : ''}
        ${issues.length ? `<ul class="auth-issues">${issues.map(i => `<li>${escHtml(i)}</li>`).join('')}</ul>` : ''}
      </div>`;
  }).join('');

  // Accordion toggles
  $$('.auth-detail-toggle', grid).forEach(btn => {
    btn.addEventListener('click', () => {
      const detail = $(`#${btn.dataset.target}`);
      if (!detail) return;
      const open = detail.classList.toggle('hidden') === false;
      const arrow = $('.accordion-arrow', btn);
      if (arrow) arrow.style.transform = open ? 'rotate(180deg)' : '';
    });
  });
}

// ── Blocklist table ───────────────────────────────────
function renderBlocklists(reputation) {
  const summary = $('#blocklistSummary');
  const body = $('#blocklistBody');

  const dnsbl = reputation?.reputation?.dnsbl;
  const listedCount = reputation?.reputation?.listed_count || 0;

  if (!dnsbl || !dnsbl.length) {
    summary.textContent = '(domain lists only)';
    body.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--text-hint);padding:16px">No blocklist data available.</td></tr>';
    return;
  }

  if (listedCount === 0) {
    summary.innerHTML = '<span class="dnsbl-clean-badge">\u2713 Clean on all lists</span>';
  } else {
    summary.innerHTML = `<span class="dnsbl-listed-badge">\u26A0 Listed on ${listedCount} list${listedCount !== 1 ? 's' : ''}</span>`;
  }

  body.innerHTML = dnsbl.map(row => {
    const listed = row.listed;
    const statusCls = listed ? 'dnsbl-status--listed' : 'dnsbl-status--clean';
    const statusTxt = listed ? '\u2717 Listed' : '\u2713 Clean';
    const reason = listed && row.reason ? `<br><small class="dnsbl-reason">${escHtml(row.reason.slice(0, 120))}</small>` : '';
    const wlabel = WEIGHT_LABEL[row.weight] || row.weight;

    return `
      <tr class="${listed ? 'dnsbl-row--listed' : ''}">
        <td><span class="dnsbl-status ${statusCls}">${statusTxt}</span>${reason}</td>
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

// ── DNS Records ───────────────────────────────────────
function renderDnsRecords(reputation, mx, bimi) {
  const container = $('#dnsRecords');
  const rows = [];

  // MX records
  if (mx && mx.records && mx.records.length) {
    rows.push({
      label: 'MX Records',
      status: 'pass',
      value: mx.records.map(r => `${r.priority} ${r.host}`).join(', '),
    });
  } else if (reputation?.reputation?.mx?.found) {
    const mxData = reputation.reputation.mx;
    rows.push({
      label: 'MX Records',
      status: 'pass',
      value: mxData.records.slice(0, 5).map(r => `${r[0]} ${r[1]}`).join(', '),
    });
  } else {
    rows.push({ label: 'MX Records', status: 'fail', value: 'No MX records found' });
  }

  // SPF record
  const authCats = reputation?.auth?.categories || [];
  const spfCat = authCats.find(c => c.label === 'SPF');
  if (spfCat && spfCat.record) {
    rows.push({ label: 'SPF Record', status: spfCat.status === 'pass' ? 'pass' : 'warning', value: spfCat.record });
  } else {
    rows.push({ label: 'SPF Record', status: 'missing', value: 'Not found' });
  }

  // DKIM
  const dkimCat = authCats.find(c => c.label === 'DKIM');
  if (dkimCat && dkimCat.record) {
    rows.push({ label: 'DKIM Record', status: dkimCat.status === 'pass' ? 'pass' : 'warning', value: dkimCat.record.slice(0, 120) + (dkimCat.record.length > 120 ? '...' : '') });
  } else {
    rows.push({ label: 'DKIM Record', status: 'missing', value: 'Not found' });
  }

  // DMARC
  const dmarcCat = authCats.find(c => c.label === 'DMARC');
  if (dmarcCat && dmarcCat.record) {
    rows.push({ label: 'DMARC Record', status: dmarcCat.status === 'pass' ? 'pass' : 'warning', value: dmarcCat.record });
  } else {
    rows.push({ label: 'DMARC Record', status: 'missing', value: 'Not found' });
  }

  container.innerHTML = rows.map(r => `
    <div class="rep-signal-row">
      <span class="rep-signal-icon auth-status-icon--${r.status}">${STATUS_ICON[r.status] || '\u2139'}</span>
      <div class="rep-signal-body">
        <span class="rep-signal-label">${escHtml(r.label)}</span>
        <span class="rep-signal-value" style="font-family:'SF Mono','Fira Code',monospace;font-size:0.78rem;word-break:break-all">${escHtml(r.value)}</span>
      </div>
    </div>`).join('');
}

// ── BIMI Details ──────────────────────────────────────
function renderBimiDetails(bimi) {
  const section = $('#bimiSection');
  const container = $('#bimiDetails');

  if (!bimi) {
    section.classList.add('hidden');
    return;
  }

  section.classList.remove('hidden');
  const rows = [];

  rows.push({
    label: 'BIMI Record',
    status: bimi.found ? 'pass' : 'missing',
    value: bimi.found ? (bimi.record || 'Found') : 'Not configured',
  });

  if (bimi.logo_url) {
    rows.push({ label: 'Logo URL', status: 'pass', value: bimi.logo_url });
  }
  if (bimi.vmc_url) {
    rows.push({ label: 'VMC Certificate', status: 'pass', value: bimi.vmc_url });
  }
  if (bimi.issues && bimi.issues.length) {
    bimi.issues.forEach(issue => {
      rows.push({ label: 'Issue', status: 'warning', value: issue });
    });
  }

  container.innerHTML = rows.map(r => `
    <div class="rep-signal-row">
      <span class="rep-signal-icon auth-status-icon--${r.status}">${STATUS_ICON[r.status] || '\u2139'}</span>
      <div class="rep-signal-body">
        <span class="rep-signal-label">${escHtml(r.label)}</span>
        <span class="rep-signal-value">${escHtml(r.value)}</span>
      </div>
    </div>`).join('');
}

// ── Recommendations ───────────────────────────────────
function renderRecommendations(recs) {
  const container = $('#recsList');
  if (!recs || !recs.length) {
    container.innerHTML = '<p style="font-size:0.85rem;color:var(--color-green);padding:8px 0">\u2713 No issues found. Your domain configuration looks healthy.</p>';
    return;
  }
  container.innerHTML = recs.map(rec => `
    <div class="rec-item">
      <div class="rec-item__header">
        <span class="rec-item__cat">${escHtml(rec.category || rec.priority || '')}</span>
      </div>
      <div class="rec-item__issue">${escHtml(rec.item || rec.title || '')}</div>
      <div class="rec-item__text">${escHtml(rec.recommendation || rec.description || '')}</div>
    </div>`).join('');
}

// ── Helpers ───────────────────────────────────────────
function gradeColor(grade) {
  if (!grade) return 'blue';
  const g = grade.charAt(0).toUpperCase();
  if (g === 'A') return 'green';
  if (g === 'B') return 'blue';
  if (g === 'C') return 'yellow';
  if (g === 'D') return 'orange';
  return 'red';
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
