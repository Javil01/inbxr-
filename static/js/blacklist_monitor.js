/* ══════════════════════════════════════════════════════
   InbXr — Blacklist Monitor Page
   ══════════════════════════════════════════════════════ */

'use strict';

const $ = (sel, ctx = document) => ctx.querySelector(sel);
const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

// ── State ────────────────────────────────────────────
let domains = [];
let currentDomain = null;

// ══════════════════════════════════════════════════════
//  INIT — Load domains on page load
// ══════════════════════════════════════════════════════
(async function init() {
  await loadDomains();
})();

// ══════════════════════════════════════════════════════
//  ADD DOMAIN
// ══════════════════════════════════════════════════════
$('#blmAddForm').addEventListener('submit', async e => {
  e.preventDefault();

  const domain = $('#blmDomain').value.trim();
  const ip = $('#blmIp').value.trim();

  if (!domain) {
    $('#blmDomain').focus();
    $('#blmDomain').style.borderColor = 'var(--color-red)';
    return;
  }
  $('#blmDomain').style.borderColor = '';

  const btn = $('#blmAddBtn');
  btn.disabled = true;
  $('.btn-text', btn).textContent = 'Adding...';
  $('.btn-spinner', btn).classList.remove('hidden');

  try {
    const res = await fetch('/blacklist-monitor/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ domain, ip: ip || null }),
    });
    const data = await res.json();

    if (!data.ok) {
      showToast(data.error || 'Failed to add domain.', 'error');
    } else {
      $('#blmDomain').value = '';
      $('#blmIp').value = '';
      await loadDomains();
    }
  } catch (err) {
    showToast('Network error. Please try again.', 'error');
  } finally {
    btn.disabled = false;
    $('.btn-text', btn).textContent = 'Add Domain';
    $('.btn-spinner', btn).classList.add('hidden');
  }
});

// ══════════════════════════════════════════════════════
//  LOAD DOMAINS
// ══════════════════════════════════════════════════════
async function loadDomains() {
  try {
    const res = await fetch('/blacklist-monitor/domains');
    domains = await res.json();
  } catch {
    domains = [];
  }

  updateDomainCount();
  renderDomainList();
}

function updateDomainCount() {
  const countEl = $('#blmDomainCount');
  const textEl = $('#blmCountText');
  textEl.textContent = `${domains.length} / 5 domains monitored`;
  countEl.classList.remove('hidden');
}

function renderDomainList() {
  const container = $('#blmDomainList');
  const wrapper = $('#blmDomains');

  if (domains.length === 0) {
    wrapper.classList.add('hidden');
    return;
  }

  wrapper.classList.remove('hidden');
  container.innerHTML = domains.map(d => {
    const scan = d.last_scan;
    const statusClass = scan ? (scan.clean ? 'blm-status--clean' : 'blm-status--listed') : 'blm-status--pending';
    const statusText = scan ? (scan.clean ? 'Clean' : `Listed on ${scan.listed_count}`) : 'Not scanned';
    const listsText = scan ? `${scan.total_lists} lists checked` : '';
    const lastChecked = d.last_checked_at ? formatDate(d.last_checked_at) : 'Never';

    return `
      <div class="blm-domain-card" data-domain="${d.domain}">
        <div class="blm-domain-card__main">
          <div class="blm-domain-card__info">
            <span class="blm-domain-card__name">${escH(d.domain)}</span>
            ${d.ip ? `<span class="blm-domain-card__ip">${escH(d.ip)}</span>` : ''}
          </div>
          <div class="blm-domain-card__status">
            <span class="blm-status ${statusClass}">${statusText}</span>
            <span class="blm-domain-card__lists">${listsText}</span>
            <span class="blm-domain-card__date">Last: ${lastChecked}</span>
          </div>
        </div>
        <div class="blm-domain-card__actions">
          <button type="button" class="blm-btn blm-btn--scan" data-action="scan" data-domain="${d.domain}">Scan Now</button>
          <button type="button" class="blm-btn blm-btn--detail" data-action="detail" data-domain="${d.domain}">Details</button>
          <button type="button" class="blm-btn blm-btn--remove" data-action="remove" data-domain="${d.domain}">Remove</button>
        </div>
      </div>
    `;
  }).join('');

  // Attach event listeners
  $$('[data-action="scan"]', container).forEach(btn => {
    btn.addEventListener('click', () => scanSingle(btn.dataset.domain, btn));
  });
  $$('[data-action="detail"]', container).forEach(btn => {
    btn.addEventListener('click', () => showDetail(btn.dataset.domain));
  });
  $$('[data-action="remove"]', container).forEach(btn => {
    btn.addEventListener('click', () => removeDomain(btn.dataset.domain));
  });
}

// ══════════════════════════════════════════════════════
//  SCAN SINGLE DOMAIN
// ══════════════════════════════════════════════════════
async function scanSingle(domain, btn) {
  if (btn) {
    btn.disabled = true;
    btn.textContent = 'Scanning...';
  }

  $('#blmLoading').classList.remove('hidden');

  try {
    const res = await fetch('/blacklist-monitor/scan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ domain }),
    });
    const data = await res.json();

    if (!data.ok) {
      showToast(data.error || 'Scan failed.', 'error');
    }

    await loadDomains();

    // If we're viewing this domain's detail, refresh it
    if (currentDomain === domain) {
      showDetail(domain);
    }
  } catch (err) {
    showToast('Network error during scan.', 'error');
  } finally {
    $('#blmLoading').classList.add('hidden');
    if (btn) {
      btn.disabled = false;
      btn.textContent = 'Scan Now';
    }
  }
}

// ══════════════════════════════════════════════════════
//  SCAN ALL
// ══════════════════════════════════════════════════════
$('#blmScanAll').addEventListener('click', async () => {
  const btn = $('#blmScanAll');
  btn.disabled = true;
  $('.btn-text', btn).textContent = 'Scanning All...';
  $('.btn-spinner', btn).classList.remove('hidden');
  $('#blmLoading').classList.remove('hidden');

  try {
    // Scan each domain sequentially to avoid overwhelming DNS
    for (const d of domains) {
      $('#blmLoadingMsg').textContent = `Scanning ${d.domain}...`;
      await fetch('/blacklist-monitor/scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ domain: d.domain }),
      });
    }
    await loadDomains();
  } catch (err) {
    showToast('Error during scan.', 'error');
  } finally {
    $('#blmLoading').classList.add('hidden');
    btn.disabled = false;
    $('.btn-text', btn).textContent = 'Scan All';
    $('.btn-spinner', btn).classList.add('hidden');
  }
});

// ══════════════════════════════════════════════════════
//  REMOVE DOMAIN
// ══════════════════════════════════════════════════════
async function removeDomain(domain) {
  if (!confirm(`Remove ${domain} from monitoring?`)) return;

  try {
    const res = await fetch('/blacklist-monitor/remove', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ domain }),
    });
    const data = await res.json();
    if (!data.ok) showToast(data.error || 'Failed to remove.', 'error');
    await loadDomains();
  } catch {
    showToast('Network error.', 'error');
  }
}

// ══════════════════════════════════════════════════════
//  DETAIL VIEW
// ══════════════════════════════════════════════════════
async function showDetail(domain) {
  currentDomain = domain;

  // Hide list, show detail
  $('#blmDomains').classList.add('hidden');
  $('#blmFormCard').classList.add('hidden');
  $('#blmDomainCount').classList.add('hidden');
  $('#blmDetail').classList.remove('hidden');

  $('#blmDetailTitle').textContent = domain;

  // Find domain data
  const d = domains.find(x => x.domain === domain);
  const scan = d?.last_scan;

  // Summary
  const summaryEl = $('#blmDetailSummary');
  if (scan) {
    const statusClass = scan.clean ? 'blm-status--clean' : 'blm-status--listed';
    const statusText = scan.clean ? 'Clean — Not listed on any blocklist' : `Listed on ${scan.listed_count} blocklist${scan.listed_count > 1 ? 's' : ''}`;
    summaryEl.innerHTML = `
      <span class="blm-status ${statusClass}" style="font-size:1.1rem;padding:8px 18px">${statusText}</span>
      <span class="blm-detail__meta">${scan.total_lists} blocklists checked &middot; Last scan: ${d.last_checked_at ? formatDate(d.last_checked_at) : 'N/A'}</span>
    `;
  } else {
    summaryEl.innerHTML = '<span class="blm-status blm-status--pending" style="font-size:1.1rem;padding:8px 18px">Not yet scanned</span>';
  }

  // Load latest scan results (do a fresh scan to get detailed results)
  // Actually, scan results with full detail are returned from the scan endpoint
  // For the detail table, we show the listed_on data from the latest scan
  const tbody = $('#blmResultsBody');
  if (scan && scan.listed_on && scan.listed_on.length > 0) {
    tbody.innerHTML = scan.listed_on.map(r => `
      <tr class="dnsbl-row--listed">
        <td><span class="dnsbl-badge dnsbl-badge--listed">LISTED</span></td>
        <td>${escH(r.name)}</td>
        <td>${escH(r.type || '')}</td>
        <td><span class="dnsbl-weight dnsbl-weight--${r.weight}">${r.weight}</span></td>
        <td>${escH(r.reason || r.zone || '')}</td>
      </tr>
    `).join('');
  } else if (scan) {
    tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:24px;opacity:.6">No blocklist listings found. Your domain is clean.</td></tr>';
  } else {
    tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:24px;opacity:.6">Run a scan to see results.</td></tr>';
  }

  // Load history
  try {
    const res = await fetch(`/blacklist-monitor/history/${encodeURIComponent(domain)}`);
    const history = await res.json();
    renderHistory(history);
  } catch {
    $('#blmHistory').innerHTML = '<p style="opacity:.6">Could not load history.</p>';
  }
}

function renderHistory(history) {
  const container = $('#blmHistory');
  if (!history || history.length === 0) {
    container.innerHTML = '<p style="opacity:.6;text-align:center;padding:16px">No scan history yet. Run your first scan.</p>';
    return;
  }

  // Reverse so oldest is first (left to right)
  const ordered = [...history].reverse();
  container.innerHTML = `
    <div class="blm-history-dots">
      ${ordered.map((s, i) => {
        const cls = s.clean ? 'blm-dot--clean' : 'blm-dot--listed';
        const title = `${formatDate(s.checked_at)}: ${s.clean ? 'Clean' : `Listed on ${s.listed_count}`}`;
        return `<span class="blm-dot ${cls}" title="${escH(title)}"></span>`;
      }).join('')}
    </div>
  `;
}

// ── Back button ──────────────────────────────────────
$('#blmDetailBack').addEventListener('click', () => {
  currentDomain = null;
  $('#blmDetail').classList.add('hidden');
  $('#blmFormCard').classList.remove('hidden');
  $('#blmDomainCount').classList.remove('hidden');
  $('#blmDomains').classList.remove('hidden');
});

// ══════════════════════════════════════════════════════
//  HELPERS
// ══════════════════════════════════════════════════════
function escH(s) {
  const d = document.createElement('div');
  d.textContent = s || '';
  return d.innerHTML;
}

function formatDate(dateStr) {
  if (!dateStr) return 'N/A';
  try {
    const d = new Date(dateStr + (dateStr.includes('T') ? '' : 'T00:00:00Z'));
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  } catch {
    return dateStr;
  }
}
