/* ==============================================================
   INBXR — Full Domain Audit Page
   One domain → every check → prioritized fixes with copy-paste DNS records
   ============================================================== */

'use strict';

const $ = (sel, ctx = document) => ctx.querySelector(sel);
const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

// ── Loading message rotation ──────────────────────────
const LOADING_MSGS = [
  'Starting full domain audit...',
  'Looking up MX records...',
  'Detecting email service provider...',
  'Checking SPF, DKIM, and DMARC...',
  'Scanning 60+ blocklists...',
  'Validating BIMI configuration...',
  'Checking MTA-STS and TLS-RPT...',
  'Verifying SSL certificate...',
  'Checking reverse DNS and FCrDNS...',
  'Generating fix records...',
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

// ── Status helpers ────────────────────────────────────
const STATUS_ICON  = { pass: '\u2713', warning: '\u26A0', fail: '\u2717', missing: '\u2717', info: '\u2139' };
const STATUS_LABEL = { pass: 'Configured', warning: 'Needs Work', fail: 'Failed', missing: 'Not Found', info: 'Info' };
const WEIGHT_LABEL = { critical: 'Critical', major: 'High', moderate: 'Medium', minor: 'Low' };

// Track last domain for re-check
let lastAuditDomain = '';
let lastAuditSelector = '';

// ══════════════════════════════════════════════════════
//  FORM SUBMIT
// ══════════════════════════════════════════════════════
$('#fullAuditForm').addEventListener('submit', async e => {
  e.preventDefault();

  const domain   = $('#faDomain').value.trim();
  const selector = $('#faSelector').value.trim();

  if (!domain) {
    $('#faDomain').focus();
    $('#faDomain').style.borderColor = 'var(--color-red)';
    return;
  }
  $('#faDomain').style.borderColor = '';

  lastAuditDomain = domain;
  lastAuditSelector = selector;
  await runAudit(domain, selector);
});

async function runAudit(domain, selector) {
  const submitBtn = $('#submitBtn');
  submitBtn.disabled = true;
  $('.btn-text', submitBtn).textContent = 'Auditing...';
  $('.btn-spinner', submitBtn).classList.remove('hidden');

  $('#faResults').classList.add('hidden');
  $('#faLoading').classList.remove('hidden');
  startLoading();

  try {
    const res = await fetch('/api/full-audit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ domain, dkim_selector: selector || null }),
    });
    const data = await res.json();

    stopLoading();
    $('#faLoading').classList.add('hidden');

    if (!res.ok || data.error) {
      showError(data.error || 'Audit failed. Please try again.');
      return;
    }

    renderResults(data, domain);
  } catch (err) {
    stopLoading();
    $('#faLoading').classList.add('hidden');
    showError('Network error. Check your connection and try again.');
  } finally {
    submitBtn.disabled = false;
    $('.btn-text', submitBtn).textContent = 'Run Full Audit';
    $('.btn-spinner', submitBtn).classList.add('hidden');
  }
}

// Run again & re-check buttons
$('#runAgainBtn').addEventListener('click', () => {
  $('#faResults').classList.add('hidden');
  $('#faDomain').focus();
});

$('#recheckBtn').addEventListener('click', () => {
  if (lastAuditDomain) {
    runAudit(lastAuditDomain, lastAuditSelector);
  }
});

// ══════════════════════════════════════════════════════
//  RENDER RESULTS
// ══════════════════════════════════════════════════════
function renderResults(data, domain) {
  // Severity summary bar
  renderSeverityBar(data.severity_summary);

  // Overall grade
  renderOverallGrade(data.grade, data.score, data.category_scores);

  // ESP badge
  renderESPBadge(data.esp);

  // Category cards
  renderCategoryCards(data.category_scores);

  // Auth details
  renderAuthDetails(data.reputation);

  // Blocklist scan
  renderBlocklists(data.reputation);

  // DNS records
  renderDnsRecords(data.reputation, data.mx, data.bimi);

  // BIMI details
  renderBimiDetails(data.bimi);

  // Fix records (the differentiator)
  renderFixRecords(data.fix_records, data.esp);

  // Recommendations
  renderRecommendations(data.recommendations);

  // Show re-check button if there are fixes
  const recheckBtn = $('#recheckBtn');
  if (data.fix_records && data.fix_records.length > 0) {
    recheckBtn.style.display = '';
  } else {
    recheckBtn.style.display = 'none';
  }

  $('#faResults').classList.remove('hidden');
  $('#faResults').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ── Severity summary bar ─────────────────────────────
function renderSeverityBar(summary) {
  const bar = $('#severityBar');
  if (!summary) { bar.innerHTML = ''; return; }

  const items = [];
  if (summary.critical > 0)
    items.push(`<span class="fa-sev fa-sev--critical">${summary.critical} Critical</span>`);
  if (summary.warning > 0)
    items.push(`<span class="fa-sev fa-sev--warning">${summary.warning} Warning${summary.warning !== 1 ? 's' : ''}</span>`);
  if (summary.pass > 0)
    items.push(`<span class="fa-sev fa-sev--pass">${summary.pass} Passing</span>`);
  if (summary.info > 0)
    items.push(`<span class="fa-sev fa-sev--info">${summary.info} Info</span>`);

  bar.innerHTML = items.join('');
}

// ── ESP badge ────────────────────────────────────────
function renderESPBadge(esp) {
  const badge = $('#espBadge');
  if (!esp || !esp.detected) {
    badge.classList.add('hidden');
    return;
  }
  badge.classList.remove('hidden');
  badge.innerHTML = `
    <span class="fa-esp-icon">&#9993;</span>
    <span class="fa-esp-text">
      <strong>Detected ESP:</strong> ${escHtml(esp.esp_name)}
      <small>via ${escHtml(esp.mx_host)}</small>
    </span>`;
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
    const detailsId = `fa-auth-detail-${cat.label}`;

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

  const authCats = reputation?.auth?.categories || [];
  const spfCat = authCats.find(c => c.label === 'SPF');
  if (spfCat && spfCat.record) {
    rows.push({ label: 'SPF Record', status: spfCat.status === 'pass' ? 'pass' : 'warning', value: spfCat.record });
  } else {
    rows.push({ label: 'SPF Record', status: 'missing', value: 'Not found' });
  }

  const dkimCat = authCats.find(c => c.label === 'DKIM');
  if (dkimCat && dkimCat.record) {
    rows.push({ label: 'DKIM Record', status: dkimCat.status === 'pass' ? 'pass' : 'warning', value: dkimCat.record.slice(0, 120) + (dkimCat.record.length > 120 ? '...' : '') });
  } else {
    rows.push({ label: 'DKIM Record', status: 'missing', value: 'Not found' });
  }

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

// ══════════════════════════════════════════════════════
//  FIX RECORDS — THE DIFFERENTIATOR
// ══════════════════════════════════════════════════════
function renderFixRecords(fixRecords, esp) {
  const container = $('#fixRecords');
  const section = $('#fixSection');

  if (!fixRecords || !fixRecords.length) {
    section.classList.add('hidden');
    return;
  }

  section.classList.remove('hidden');

  container.innerHTML = fixRecords.map((fix, i) => {
    const actionColors = { create: 'red', fix: 'orange', upgrade: 'yellow' };
    const actionColor = actionColors[fix.action] || 'blue';
    const actionLabel = (fix.action || 'create').charAt(0).toUpperCase() + (fix.action || 'create').slice(1);

    let html = `
      <div class="fa-fix-card" style="animation-delay:${i * 80}ms">
        <div class="fa-fix-header">
          <span class="fa-fix-action fa-fix-action--${actionColor}">${actionLabel}</span>
          <h3 class="fa-fix-title">${escHtml(fix.title)}</h3>
          ${fix.esp_detected ? `<span class="fa-fix-esp">${escHtml(fix.esp_detected)}</span>` : ''}
        </div>
        <p class="fa-fix-desc">${escHtml(fix.description)}</p>`;

    // DNS record block
    if (fix.record && fix.host) {
      html += `
        <div class="fa-fix-record">
          <div class="fa-fix-record-meta">
            <span class="fa-fix-label">Host:</span>
            <code class="fa-fix-host">${escHtml(fix.host)}</code>
            <span class="fa-fix-label">Type:</span>
            <code class="fa-fix-type">${escHtml(fix.dns_type || 'TXT')}</code>
          </div>
          <div class="fa-fix-record-value">
            <pre class="fa-fix-code"><code>${escHtml(fix.record)}</code></pre>
            <button class="fa-copy-btn" data-copy="${escAttr(fix.record)}" title="Copy to clipboard">Copy</button>
          </div>
        </div>`;
    }

    // Setup instructions (DKIM, MTA-STS)
    if (fix.instructions && fix.instructions.length) {
      html += `
        <div class="fa-fix-instructions">
          <strong>Setup Steps:</strong>
          <ol>${fix.instructions.map(step => `<li>${escHtml(step)}</li>`).join('')}</ol>
        </div>`;
    }

    // MTA-STS policy file
    if (fix.policy_text) {
      html += `
        <div class="fa-fix-record" style="margin-top:12px">
          <div class="fa-fix-record-meta">
            <span class="fa-fix-label">Policy File URL:</span>
            <code class="fa-fix-host">${escHtml(fix.policy_url || '')}</code>
          </div>
          <div class="fa-fix-record-value">
            <pre class="fa-fix-code"><code>${escHtml(fix.policy_text)}</code></pre>
            <button class="fa-copy-btn" data-copy="${escAttr(fix.policy_text)}" title="Copy to clipboard">Copy</button>
          </div>
        </div>`;

      if (fix.setup_steps && fix.setup_steps.length) {
        html += `
          <div class="fa-fix-instructions">
            <strong>How to deploy:</strong>
            <ol>${fix.setup_steps.map(step => `<li>${escHtml(step)}</li>`).join('')}</ol>
          </div>`;
      }
    }

    // Warnings
    if (fix.warnings && fix.warnings.length) {
      html += `
        <div class="fa-fix-warnings">
          ${fix.warnings.map(w => `<p class="fa-fix-warning">\u26A0 ${escHtml(w)}</p>`).join('')}
        </div>`;
    }

    html += '</div>';
    return html;
  }).join('');

  // Copy button handlers
  $$('.fa-copy-btn', container).forEach(btn => {
    btn.addEventListener('click', () => {
      const text = btn.dataset.copy;
      navigator.clipboard.writeText(text).then(() => {
        btn.textContent = 'Copied!';
        btn.classList.add('fa-copy-btn--copied');
        setTimeout(() => {
          btn.textContent = 'Copy';
          btn.classList.remove('fa-copy-btn--copied');
        }, 1500);
      }).catch(() => {
        // Fallback for older browsers
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        btn.textContent = 'Copied!';
        setTimeout(() => { btn.textContent = 'Copy'; }, 1500);
      });
    });
  });
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

function escAttr(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/'/g, '&#39;')
    .replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// ══════════════════════════════════════════════════════
//  AUTO-RUN FROM URL PARAMS (linked from Email Test)
// ══════════════════════════════════════════════════════
(function autoRunFromParams() {
  const params = new URLSearchParams(window.location.search);
  const domain = params.get('domain');
  if (domain) {
    $('#faDomain').value = domain;
    const selector = params.get('dkim_selector') || params.get('selector') || '';
    if (selector) $('#faSelector').value = selector;
    // Auto-run the audit
    setTimeout(() => runAudit(domain, selector), 300);
  }
})();
