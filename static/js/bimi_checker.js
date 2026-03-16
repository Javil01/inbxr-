/* ══════════════════════════════════════════════════════
   INBXR — BIMI Checker
   ══════════════════════════════════════════════════════ */

'use strict';

const $ = (sel, ctx = document) => ctx.querySelector(sel);
const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

// ── Copy-to-clipboard ────────────────────────────────
function initCopyButtons() {
  $$('.dns-copy-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const targetId = btn.dataset.target;
      const el = document.getElementById(targetId);
      if (!el) return;
      const text = el.textContent.trim();
      navigator.clipboard.writeText(text).then(() => {
        const orig = btn.textContent;
        btn.textContent = 'Copied!';
        btn.classList.add('dns-copy-btn--ok');
        setTimeout(() => {
          btn.textContent = orig;
          btn.classList.remove('dns-copy-btn--ok');
        }, 1500);
      });
    });
  });
}

// ── Status color map ─────────────────────────────────
const STATUS_COLORS = {
  pass:    'var(--color-green)',
  partial: 'var(--color-yellow)',
  invalid: 'var(--color-orange)',
  missing: 'var(--color-red)',
  error:   'var(--color-red)',
};

const STATUS_LABELS = {
  pass:    'Pass',
  partial: 'Partial',
  invalid: 'Invalid',
  missing: 'Missing',
  error:   'Error',
};

// ══════════════════════════════════════════════════════
//  BIMI CHECK FORM
// ══════════════════════════════════════════════════════
$('#bimiForm').addEventListener('submit', async e => {
  e.preventDefault();

  const domain = $('#bimiDomain').value.trim();
  if (!domain) {
    $('#bimiDomain').focus();
    $('#bimiDomain').style.borderColor = 'var(--color-red)';
    return;
  }
  $('#bimiDomain').style.borderColor = '';

  const selector = $('#bimiSelector').value.trim() || 'default';

  // Show spinner
  const btn = $('#bimiSubmitBtn');
  const btnText = btn.querySelector('.btn-text');
  const btnSpinner = btn.querySelector('.btn-spinner');
  btn.disabled = true;
  btnText.classList.add('hidden');
  btnSpinner.classList.remove('hidden');

  // Show loading
  $('#bimiFormCard').classList.add('hidden');
  $('#bimiLoading').classList.remove('hidden');

  try {
    const resp = await fetch('/validate-bimi', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ domain, selector }),
    });

    const data = await resp.json();
    if (!resp.ok) {
      showToast(data.error || 'BIMI check failed.', 'error');
      $('#bimiLoading').classList.add('hidden');
      $('#bimiFormCard').classList.remove('hidden');
      return;
    }

    renderBimiResults(data, domain, selector);
  } catch (err) {
    showToast('Request failed: ' + err.message, 'error');
    $('#bimiLoading').classList.add('hidden');
    $('#bimiFormCard').classList.remove('hidden');
  } finally {
    btn.disabled = false;
    btnText.classList.remove('hidden');
    btnSpinner.classList.add('hidden');
  }
});

// ══════════════════════════════════════════════════════
//  RENDER BIMI RESULTS
// ══════════════════════════════════════════════════════
function renderBimiResults(data, domain, selector) {
  // Status badge
  const status = (data.status || 'missing').toLowerCase();
  const badge = $('#bimiStatusBadge');
  badge.textContent = STATUS_LABELS[status] || status;
  badge.style.background = STATUS_COLORS[status] || 'var(--color-muted)';
  badge.style.color = '#fff';

  // Score
  const score = data.score != null ? data.score : 0;
  $('#bimiScore').querySelector('.bimi-score__num').textContent = score;

  // Logo preview
  const preview = $('#bimiLogoPreview');
  const logoUrl = data.logo_url || data.svg_url || '';
  if (logoUrl) {
    preview.innerHTML = `<img src="${escAttr(logoUrl)}" alt="BIMI Logo" class="bimi-logo-preview__img" onerror="this.outerHTML='<span class=\\'bimi-logo-preview__placeholder\\'>Logo could not be loaded</span>'" />`;
  } else {
    preview.innerHTML = '<span class="bimi-logo-preview__placeholder">No logo found</span>';
  }

  // Check details
  const checks = $('#bimiChecks');
  checks.innerHTML = '';
  const checkItems = [
    { label: 'BIMI DNS Record', ok: data.record_found || data.dns_found, detail: data.raw_record || '—' },
    { label: 'SVG Logo', ok: !!logoUrl, detail: logoUrl || 'Not found' },
    { label: 'VMC Certificate', ok: data.vmc_valid || data.has_vmc, detail: data.vmc_url || (data.vmc_valid ? 'Valid' : 'Not found') },
    { label: 'DMARC (p=quarantine or reject)', ok: data.dmarc_ok || data.dmarc_pass, detail: data.dmarc_policy ? `p=${data.dmarc_policy}` : '—' },
  ];

  checkItems.forEach(item => {
    const row = document.createElement('div');
    row.className = 'bimi-check-row';
    const icon = item.ok ? '<span class="bimi-check-icon bimi-check-icon--pass">&#10003;</span>' : '<span class="bimi-check-icon bimi-check-icon--fail">&#10007;</span>';
    row.innerHTML = `
      ${icon}
      <span class="bimi-check-label">${escHtml(item.label)}</span>
      <span class="bimi-check-detail">${escHtml(typeof item.detail === 'string' ? item.detail : JSON.stringify(item.detail))}</span>`;
    checks.appendChild(row);
  });

  // Issues
  const issues = data.issues || [];
  const issuesSec = $('#bimiIssuesSection');
  const issuesList = $('#bimiIssues');
  issuesList.innerHTML = '';
  if (issues.length) {
    issuesSec.classList.remove('hidden');
    issues.forEach(issue => {
      const div = document.createElement('div');
      div.className = 'bimi-issue';
      div.innerHTML = `<span class="bimi-issue__icon">&#9888;</span><span>${escHtml(issue)}</span>`;
      issuesList.appendChild(div);
    });
  } else {
    issuesSec.classList.add('hidden');
  }

  // Recommendations
  const recs = data.recommendations || [];
  const recsSec = $('#bimiRecsSection');
  const recsList = $('#bimiRecs');
  recsList.innerHTML = '';
  if (recs.length) {
    recsSec.classList.remove('hidden');
    recs.forEach(rec => {
      const div = document.createElement('div');
      div.className = 'rec-item';
      div.innerHTML = `<span class="rec-item__text">${escHtml(rec)}</span>`;
      recsList.appendChild(div);
    });
  } else {
    recsSec.classList.add('hidden');
  }

  // DNS Record display
  const recordHost = `${selector}._bimi.${domain}`;
  $('#bimiRecordHost').textContent = recordHost;
  const rawRecord = data.raw_record || data.record || '';
  if (rawRecord) {
    $('#bimiRecordValue').textContent = rawRecord;
    $('#bimiRecordSection').classList.remove('hidden');
  } else {
    $('#bimiRecordSection').classList.add('hidden');
  }

  // Pre-fill generate form domain
  // Store domain for generate form
  $('#bimiGenerateForm').dataset.domain = domain;
  $('#bimiGenerateForm').dataset.selector = selector;

  // Show results, hide loading
  $('#bimiLoading').classList.add('hidden');
  $('#bimiResults').classList.remove('hidden');

  initCopyButtons();
  $('#bimiResults').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ══════════════════════════════════════════════════════
//  GENERATE BIMI RECORD FORM
// ══════════════════════════════════════════════════════
$('#bimiGenerateForm').addEventListener('submit', async e => {
  e.preventDefault();

  const domain = e.target.dataset.domain || $('#bimiDomain').value.trim();
  const selector = e.target.dataset.selector || 'default';
  const logoUrl = $('#bimiLogoUrl').value.trim();
  const vmcUrl = $('#bimiVmcUrl').value.trim();

  if (!logoUrl) {
    $('#bimiLogoUrl').focus();
    $('#bimiLogoUrl').style.borderColor = 'var(--color-red)';
    return;
  }
  $('#bimiLogoUrl').style.borderColor = '';

  if (!domain) {
    showToast('Please run a BIMI check first, or enter a domain above.', 'warning');
    return;
  }

  const btn = $('#bimiGenBtn');
  const btnText = btn.querySelector('.btn-text');
  const btnSpinner = btn.querySelector('.btn-spinner');
  btn.disabled = true;
  btnText.classList.add('hidden');
  btnSpinner.classList.remove('hidden');

  try {
    const resp = await fetch('/generate-bimi', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ domain, logo_url: logoUrl, vmc_url: vmcUrl, selector }),
    });

    const data = await resp.json();
    if (!resp.ok) {
      showToast(data.error || 'Generation failed.', 'error');
      return;
    }

    // Show generated record
    const host = data.host || `${selector}._bimi.${domain}`;
    $('#bimiGenHost').textContent = host;
    $('#bimiGenValue').textContent = data.value || data.record || '';
    $('#bimiGenResult').classList.remove('hidden');

    initCopyButtons();
    $('#bimiGenResult').scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (err) {
    showToast('Request failed: ' + err.message, 'error');
  } finally {
    btn.disabled = false;
    btnText.classList.remove('hidden');
    btnSpinner.classList.add('hidden');
  }
});

// ── Run Again ────────────────────────────────────────
$('#bimiRunAgainBtn').addEventListener('click', () => {
  $('#bimiResults').classList.add('hidden');
  $('#bimiGenResult').classList.add('hidden');
  $('#bimiFormCard').classList.remove('hidden');
  $('#bimiFormCard').scrollIntoView({ behavior: 'smooth', block: 'start' });
});

// ── Helpers ──────────────────────────────────────────
function escHtml(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function escAttr(s) {
  return s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/'/g, '&#39;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
