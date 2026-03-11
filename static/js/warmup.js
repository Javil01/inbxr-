/* ══════════════════════════════════════════════════════
   INBXR — Warm-up Tracker Page
   ══════════════════════════════════════════════════════ */

'use strict';

const $ = (sel, ctx = document) => ctx.querySelector(sel);
const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

// ── State ────────────────────────────────────────────
let campaigns = [];
let currentCampaignId = null;

// ══════════════════════════════════════════════════════
//  INIT
// ══════════════════════════════════════════════════════
(async function init() {
  await loadCampaigns();
})();

// ══════════════════════════════════════════════════════
//  CREATE CAMPAIGN
// ══════════════════════════════════════════════════════
$('#warmupCreateForm').addEventListener('submit', async e => {
  e.preventDefault();

  const domain = $('#warmupDomain').value.trim();
  const esp = $('#warmupEsp').value;
  const dailyTarget = $('#warmupTarget').value || 500;

  if (!domain) {
    $('#warmupDomain').focus();
    $('#warmupDomain').style.borderColor = 'var(--color-red)';
    return;
  }
  $('#warmupDomain').style.borderColor = '';

  const btn = $('#warmupCreateBtn');
  btn.disabled = true;
  $('.btn-text', btn).textContent = 'Creating...';
  $('.btn-spinner', btn).classList.remove('hidden');

  try {
    const res = await fetch('/warmup/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ domain, esp, daily_target: parseInt(dailyTarget) }),
    });
    const data = await res.json();

    if (!data.ok) {
      alert(data.error || 'Failed to create campaign.');
    } else {
      $('#warmupDomain').value = '';
      $('#warmupEsp').value = '';
      $('#warmupTarget').value = '500';
      await loadCampaigns();
    }
  } catch (err) {
    alert('Network error. Please try again.');
  } finally {
    btn.disabled = false;
    $('.btn-text', btn).textContent = 'Start Warm-up';
    $('.btn-spinner', btn).classList.add('hidden');
  }
});

// ══════════════════════════════════════════════════════
//  LOAD CAMPAIGNS
// ══════════════════════════════════════════════════════
async function loadCampaigns() {
  try {
    const res = await fetch('/warmup/campaigns');
    campaigns = await res.json();
  } catch {
    campaigns = [];
  }
  renderCampaignList();
}

function renderCampaignList() {
  const container = $('#warmupCampaignList');
  const wrapper = $('#warmupCampaigns');

  if (campaigns.length === 0) {
    wrapper.classList.add('hidden');
    return;
  }

  wrapper.classList.remove('hidden');
  container.innerHTML = campaigns.map(c => {
    const statusClass = c.status === 'active' ? 'warmup-status--active' :
                        c.status === 'paused' ? 'warmup-status--paused' : 'warmup-status--completed';
    const trendArrow = c.total_days >= 2 ? getTrendIndicator(c) : '';

    return `
      <div class="warmup-campaign-card" data-id="${c.id}">
        <div class="warmup-campaign-card__main">
          <div class="warmup-campaign-card__info">
            <span class="warmup-campaign-card__domain">${escH(c.domain)}</span>
            <span class="warmup-campaign-card__esp">${escH(c.esp || 'Unknown ESP')}</span>
          </div>
          <div class="warmup-campaign-card__stats">
            <span class="warmup-status ${statusClass}">${c.status}</span>
            <span class="warmup-campaign-card__metric">Day ${c.last_day || 0}</span>
            <span class="warmup-campaign-card__metric">${(c.total_sent || 0).toLocaleString()} sent</span>
            ${trendArrow}
          </div>
        </div>
        <div class="warmup-campaign-card__actions">
          <button type="button" class="blm-btn blm-btn--detail" data-action="view" data-id="${c.id}">View</button>
          ${c.status === 'active'
            ? `<button type="button" class="blm-btn blm-btn--scan" data-action="pause" data-id="${c.id}">Pause</button>`
            : c.status === 'paused'
            ? `<button type="button" class="blm-btn blm-btn--scan" data-action="resume" data-id="${c.id}">Resume</button>`
            : ''}
          <button type="button" class="blm-btn blm-btn--remove" data-action="delete" data-id="${c.id}">Delete</button>
        </div>
      </div>
    `;
  }).join('');

  // Attach listeners
  $$('[data-action="view"]', container).forEach(btn => {
    btn.addEventListener('click', () => showCampaignDetail(parseInt(btn.dataset.id)));
  });
  $$('[data-action="pause"]', container).forEach(btn => {
    btn.addEventListener('click', () => updateStatus(parseInt(btn.dataset.id), 'paused'));
  });
  $$('[data-action="resume"]', container).forEach(btn => {
    btn.addEventListener('click', () => updateStatus(parseInt(btn.dataset.id), 'active'));
  });
  $$('[data-action="delete"]', container).forEach(btn => {
    btn.addEventListener('click', () => deleteCampaign(parseInt(btn.dataset.id)));
  });
}

function getTrendIndicator(c) {
  // Simple trend: compare last_day volume to total average
  if (!c.total_days || !c.total_sent) return '';
  const avg = Math.round(c.total_sent / c.total_days);
  return `<span class="warmup-campaign-card__trend" title="Avg ${avg}/day">~${avg}/day</span>`;
}

// ══════════════════════════════════════════════════════
//  CAMPAIGN DETAIL
// ══════════════════════════════════════════════════════
async function showCampaignDetail(id) {
  currentCampaignId = id;

  // Show detail, hide list
  $('#warmupListView').classList.add('hidden');
  $('#warmupDetailView').classList.remove('hidden');

  try {
    const [campaignRes, statsRes] = await Promise.all([
      fetch(`/warmup/campaign/${id}`),
      fetch(`/warmup/campaign/${id}`),  // stats computed in the backend
    ]);
    const campaign = await campaignRes.json();

    if (!campaign) {
      alert('Campaign not found.');
      backToList();
      return;
    }

    renderCampaignDetail(campaign);
  } catch (err) {
    alert('Failed to load campaign.');
    backToList();
  }
}

function renderCampaignDetail(campaign) {
  // Header
  const header = $('#warmupDetailHeader');
  const statusClass = campaign.status === 'active' ? 'warmup-status--active' :
                      campaign.status === 'paused' ? 'warmup-status--paused' : 'warmup-status--completed';
  header.innerHTML = `
    <div class="warmup-detail-header__top">
      <h2 class="sender-section__title">${escH(campaign.domain)}</h2>
      <span class="warmup-status ${statusClass}">${campaign.status}</span>
    </div>
    <div class="warmup-detail-header__meta">
      <span>ESP: ${escH(campaign.esp)}</span>
      <span>Target: ${campaign.daily_target}/day</span>
      <span>Started: ${formatDate(campaign.started_at)}</span>
    </div>
  `;

  // Health indicator
  renderHealth(campaign);

  // Chart
  renderChart(campaign.days || []);

  // History table
  renderHistoryTable(campaign.days || []);

  // Highlight current schedule bracket
  highlightSchedule(campaign.days?.length || 0);
}

function renderHealth(campaign) {
  const container = $('#warmupHealth');
  const days = campaign.days || [];
  const dayCount = days.length;

  if (dayCount === 0) {
    container.innerHTML = `
      <div class="warmup-health-badge warmup-health--neutral">
        <span class="warmup-health__label">Not Started</span>
        <span class="warmup-health__sub">Log your first day to see health status</span>
      </div>
    `;
    return;
  }

  const lastSent = days[days.length - 1]?.sent_count || 0;
  const currentDay = days[days.length - 1]?.day_number || 1;

  // Find recommended volume for current day
  let recommended = campaign.daily_target;
  const schedule = [
    { start: 1, end: 3, vol: 20 },
    { start: 4, end: 7, vol: 50 },
    { start: 8, end: 14, vol: 100 },
    { start: 15, end: 21, vol: 250 },
    { start: 22, end: 30, vol: 500 },
  ];
  for (const b of schedule) {
    if (currentDay >= b.start && currentDay <= b.end) {
      recommended = b.vol;
      break;
    }
  }

  let health, label, cls;
  if (lastSent >= recommended * 1.3) {
    health = 'Ahead of Schedule';
    label = `Sent ${lastSent} (recommended: ${recommended})`;
    cls = 'warmup-health--ahead';
  } else if (lastSent >= recommended * 0.9) {
    health = 'On Track';
    label = `Sent ${lastSent} (recommended: ${recommended})`;
    cls = 'warmup-health--good';
  } else if (lastSent >= recommended * 0.5) {
    health = 'Slightly Behind';
    label = `Sent ${lastSent} (recommended: ${recommended})`;
    cls = 'warmup-health--warning';
  } else {
    health = 'Behind Schedule';
    label = `Sent ${lastSent} (recommended: ${recommended})`;
    cls = 'warmup-health--behind';
  }

  container.innerHTML = `
    <div class="warmup-health-badge ${cls}">
      <span class="warmup-health__label">${health}</span>
      <span class="warmup-health__sub">Day ${currentDay}: ${label}</span>
    </div>
  `;
}

function renderChart(days) {
  const container = $('#warmupChart');
  if (!days || days.length === 0) {
    container.innerHTML = '<p style="opacity:.6;text-align:center;padding:24px">No data yet. Log your first day.</p>';
    return;
  }

  const maxSent = Math.max(...days.map(d => d.sent_count), 1);

  container.innerHTML = `
    <div class="warmup-bar-chart">
      ${days.map(d => {
        const pct = Math.max((d.sent_count / maxSent) * 100, 2);
        return `
          <div class="warmup-bar-col" title="Day ${d.day_number}: ${d.sent_count} sent">
            <div class="warmup-bar" style="height:${pct}%"></div>
            <span class="warmup-bar-label">${d.day_number}</span>
          </div>
        `;
      }).join('')}
    </div>
  `;
}

function renderHistoryTable(days) {
  const tbody = $('#warmupHistoryBody');
  if (!days || days.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:24px;opacity:.6">No days logged yet.</td></tr>';
    return;
  }

  let cumulative = 0;
  tbody.innerHTML = days.map(d => {
    cumulative += d.sent_count;
    const placement = d.placement_result
      ? `Inbox: ${d.placement_result.inbox || 0}, Spam: ${d.placement_result.spam || 0}`
      : '—';
    return `
      <tr>
        <td>${d.day_number}</td>
        <td>${formatDate(d.date)}</td>
        <td>${d.sent_count.toLocaleString()}</td>
        <td>${cumulative.toLocaleString()}</td>
        <td>${placement}</td>
        <td>${escH(d.notes || '')}</td>
      </tr>
    `;
  }).join('');
}

function highlightSchedule(dayCount) {
  const currentDay = dayCount + 1; // Next day to log
  const rows = $$('.warmup-schedule__row');
  const brackets = [
    { start: 1, end: 3 },
    { start: 4, end: 7 },
    { start: 8, end: 14 },
    { start: 15, end: 21 },
    { start: 22, end: 30 },
    { start: 31, end: 9999 },
  ];
  rows.forEach((row, i) => {
    row.classList.remove('warmup-schedule__row--active');
    if (brackets[i] && currentDay >= brackets[i].start && currentDay <= brackets[i].end) {
      row.classList.add('warmup-schedule__row--active');
    }
  });
}

// ══════════════════════════════════════════════════════
//  LOG DAY
// ══════════════════════════════════════════════════════
$('#warmupLogForm').addEventListener('submit', async e => {
  e.preventDefault();

  if (!currentCampaignId) return;

  const sentCount = parseInt($('#warmupSentCount').value) || 0;
  const notes = $('#warmupNotes').value.trim();

  if (sentCount <= 0) {
    $('#warmupSentCount').focus();
    $('#warmupSentCount').style.borderColor = 'var(--color-red)';
    return;
  }
  $('#warmupSentCount').style.borderColor = '';

  const btn = $('#warmupLogBtn');
  btn.disabled = true;
  $('.btn-text', btn).textContent = 'Logging...';
  $('.btn-spinner', btn).classList.remove('hidden');

  try {
    const res = await fetch('/warmup/log', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        campaign_id: currentCampaignId,
        sent_count: sentCount,
        notes: notes || null,
      }),
    });
    const data = await res.json();

    if (!data.ok) {
      alert(data.error || 'Failed to log day.');
    } else {
      $('#warmupSentCount').value = '';
      $('#warmupNotes').value = '';
      // Refresh detail
      await showCampaignDetail(currentCampaignId);
    }
  } catch (err) {
    alert('Network error.');
  } finally {
    btn.disabled = false;
    $('.btn-text', btn).textContent = 'Log Day';
    $('.btn-spinner', btn).classList.add('hidden');
  }
});

// ══════════════════════════════════════════════════════
//  UPDATE STATUS
// ══════════════════════════════════════════════════════
async function updateStatus(id, status) {
  try {
    const res = await fetch('/warmup/status', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ campaign_id: id, status }),
    });
    const data = await res.json();
    if (!data.ok) alert(data.error || 'Failed.');
    await loadCampaigns();
  } catch {
    alert('Network error.');
  }
}

// ══════════════════════════════════════════════════════
//  DELETE CAMPAIGN
// ══════════════════════════════════════════════════════
async function deleteCampaign(id) {
  if (!confirm('Delete this campaign and all its data?')) return;

  try {
    const res = await fetch(`/warmup/campaign/${id}`, {
      method: 'DELETE',
    });
    const data = await res.json();
    if (!data.ok) alert(data.error || 'Failed.');
    await loadCampaigns();
  } catch {
    alert('Network error.');
  }
}

// ── Back button ──────────────────────────────────────
$('#warmupBack').addEventListener('click', backToList);

function backToList() {
  currentCampaignId = null;
  $('#warmupDetailView').classList.add('hidden');
  $('#warmupListView').classList.remove('hidden');
  loadCampaigns();
}

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
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  } catch {
    return dateStr;
  }
}
