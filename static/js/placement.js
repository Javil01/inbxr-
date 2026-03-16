/* ══════════════════════════════════════════════════════
   INBXR — Inbox Placement Tester
   ══════════════════════════════════════════════════════ */

'use strict';

const $ = (sel, ctx = document) => ctx.querySelector(sel);
const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

let currentToken = '';
let autoRecheckTimer = null;
let autoRecheckSeconds = 0;

// ── Provider icons (inline SVG) ─────────────────────
const PROVIDER_ICON = {
  gmail:   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="4" width="20" height="16" rx="2"/><path d="M22 7l-10 7L2 7"/></svg>',
  outlook: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="4" width="20" height="16" rx="2"/><path d="M22 7l-10 7L2 7"/></svg>',
  yahoo:   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="4" width="20" height="16" rx="2"/><path d="M22 7l-10 7L2 7"/></svg>',
  default: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="4" width="20" height="16" rx="2"/><path d="M22 7l-10 7L2 7"/></svg>',
};

// ── Placement display config ────────────────────────
const PLACEMENT_CONFIG = {
  inbox:     { icon: '\u2713', label: 'Inbox',     cls: 'inbox',     desc: 'Delivered to inbox' },
  spam:      { icon: '\u2717', label: 'Spam',      cls: 'spam',      desc: 'Landed in spam/junk folder' },
  trash:     { icon: '\u2717', label: 'Trash',     cls: 'trash',     desc: 'Found in trash' },
  not_found: { icon: '?',     label: 'Not Found', cls: 'notfound',  desc: 'Email not detected yet' },
};

const TAB_LABELS = {
  primary:    'Primary',
  promotions: 'Promotions',
  social:     'Social',
  updates:    'Updates',
  forums:     'Forums',
};

// ── ESP / CRM Configuration ─────────────────────────
const ESP_CONFIG = {
  mailchimp: {
    name: 'Mailchimp',
    separator: ', ',
    steps: [
      'Open your campaign and click <strong>Preview and Test</strong>',
      'Click <strong>Send a Test Email</strong>',
      'Paste the seed addresses into the <strong>Send test to</strong> field',
      'Make sure your subject line includes the test token above',
      'Click <strong>Send Test</strong>'
    ]
  },
  klaviyo: {
    name: 'Klaviyo',
    separator: ', ',
    steps: [
      'Open your campaign or flow email',
      'Click <strong>Preview & Test</strong> in the top-right',
      'Click <strong>Send Test Email</strong>',
      'Paste the seed addresses (comma-separated)',
      'Ensure the subject line contains the test token',
      'Click <strong>Send Test</strong>'
    ]
  },
  activecampaign: {
    name: 'ActiveCampaign',
    separator: ', ',
    steps: [
      'In the campaign editor, click <strong>Send a Test Email</strong>',
      'Paste the seed addresses into the recipient field',
      'Make sure your subject line includes the test token',
      'Click <strong>Send Test</strong>'
    ]
  },
  convertkit: {
    name: 'Kit (ConvertKit)',
    separator: ', ',
    steps: [
      'Open your broadcast or sequence email',
      'Click <strong>Preview</strong> then <strong>Send Test Email</strong>',
      'Enter the seed addresses separated by commas',
      'Ensure the subject includes the test token',
      'Click <strong>Send Test</strong>'
    ]
  },
  hubspot: {
    name: 'HubSpot',
    separator: ', ',
    steps: [
      'In the email editor, click <strong>Actions</strong> > <strong>Send test email</strong>',
      'Enter the seed addresses (comma-separated)',
      'Make sure the subject line contains your test token',
      'Click <strong>Send test email</strong>'
    ]
  },
  sendgrid: {
    name: 'SendGrid',
    separator: ', ',
    steps: [
      'In Marketing > Single Sends, open your email',
      'Click <strong>Send Test</strong> in the top-right',
      'Paste the seed addresses into the test recipients field',
      'Verify the subject line includes the test token',
      'Click <strong>Send Test</strong>'
    ]
  },
  constantcontact: {
    name: 'Constant Contact',
    separator: ', ',
    steps: [
      'Open your email campaign in the editor',
      'Click <strong>Preview & Test</strong>',
      'Click <strong>Send a Test</strong>',
      'Paste the seed addresses separated by commas',
      'Click <strong>Send Test</strong>'
    ]
  },
  mailerlite: {
    name: 'MailerLite',
    separator: ', ',
    steps: [
      'In the campaign editor, click <strong>Preview and test</strong>',
      'Click <strong>Send test email</strong>',
      'Enter the seed addresses (comma-separated)',
      'Make sure the subject includes the test token',
      'Click <strong>Send</strong>'
    ]
  },
  brevo: {
    name: 'Brevo (Sendinblue)',
    separator: ', ',
    steps: [
      'Open your campaign and click <strong>Preview & Test</strong>',
      'Click <strong>Send a test</strong>',
      'Paste the seed addresses separated by commas',
      'Ensure the subject contains the test token',
      'Click <strong>Send test</strong>'
    ]
  },
  aweber: {
    name: 'AWeber',
    separator: ', ',
    steps: [
      'In the message editor, click <strong>Send a Test</strong>',
      'Enter the seed email addresses',
      'Make sure the subject line includes the test token',
      'Click <strong>Send Test Message</strong>'
    ]
  },
  getresponse: {
    name: 'GetResponse',
    separator: ', ',
    steps: [
      'Open your newsletter or autoresponder',
      'Click the <strong>Test</strong> button',
      'Enter the seed addresses separated by commas',
      'Verify the subject includes the test token',
      'Click <strong>Send Test Message</strong>'
    ]
  },
  drip: {
    name: 'Drip',
    separator: ', ',
    steps: [
      'In the email editor, click <strong>Send a Test Email</strong>',
      'Paste the seed addresses',
      'Make sure the subject line includes the test token',
      'Click <strong>Send Test</strong>'
    ]
  },
  beehiiv: {
    name: 'Beehiiv',
    separator: ', ',
    steps: [
      'In the post editor, click <strong>Send Test</strong>',
      'Enter the seed email addresses',
      'Ensure the subject includes the test token',
      'Click <strong>Send</strong>'
    ]
  },
  campaignmonitor: {
    name: 'Campaign Monitor',
    separator: ', ',
    steps: [
      'Open your campaign and click <strong>Preview and Test</strong>',
      'Click <strong>Send a test email</strong>',
      'Paste the seed addresses (comma-separated)',
      'Make sure the subject includes the test token',
      'Click <strong>Send Test</strong>'
    ]
  },
  flodesk: {
    name: 'Flodesk',
    separator: ', ',
    steps: [
      'Open your email in the editor',
      'Click <strong>Send Test</strong> at the top',
      'Enter the seed addresses',
      'Verify the subject line contains the test token',
      'Click <strong>Send</strong>'
    ]
  },
  gohighlevel: {
    name: 'GoHighLevel',
    separator: ', ',
    steps: [
      'Open your email campaign or workflow email',
      'Click <strong>Send Test Email</strong>',
      'Paste the seed addresses into the test field',
      'Make sure the subject includes the test token',
      'Click <strong>Send</strong>'
    ]
  },
  gmail: {
    name: 'Gmail / Google Workspace',
    separator: ', ',
    steps: [
      'Compose a new email in Gmail',
      'Paste the seed addresses into the <strong>To</strong> or <strong>BCC</strong> field',
      'Set your subject line to include the test token',
      'Write your email body, then click <strong>Send</strong>'
    ]
  },
  outlook: {
    name: 'Outlook / Microsoft 365',
    separator: '; ',
    steps: [
      'Compose a new email in Outlook',
      'Paste the seed addresses into the <strong>To</strong> or <strong>BCC</strong> field',
      'Set your subject line to include the test token',
      'Write your email body, then click <strong>Send</strong>'
    ]
  },
  other: {
    name: 'Other Platform',
    separator: ', ',
    steps: [
      'Open the <strong>Send Test</strong> or <strong>Preview</strong> feature in your platform',
      'Paste all the seed addresses below into the test recipients field',
      'Make sure the subject line includes the test token',
      'Send the test email and wait 30-60 seconds before checking'
    ]
  },
};

let currentEsp = '';
let currentSeeds = [];

// ── Loading messages (rotated during check) ─────────
const LOADING_MSGS = [
  'Connecting to seed mailboxes...',
  'Searching Gmail inbox and spam folders...',
  'Checking Yahoo mail placement...',
  'Detecting Gmail tab categorization...',
  'Compiling placement results...',
];

// ══════════════════════════════════════════════════════
//  STEP NAVIGATION
// ══════════════════════════════════════════════════════
function goToStep(n) {
  clearAutoRecheck();
  [1, 2, 3].forEach(i => {
    $(`#step${i}`).classList.toggle('hidden', i !== n);
    const ind = $(`#stepIndicator${i}`);
    ind.classList.toggle('active', i <= n);
    ind.classList.toggle('completed', i < n);
  });
}

// ══════════════════════════════════════════════════════
//  STEP 1: START TEST
// ══════════════════════════════════════════════════════
$('#startTestBtn').addEventListener('click', async () => {
  const btn = $('#startTestBtn');
  btn.disabled = true;
  $('.btn-text', btn).textContent = 'Generating...';
  $('.btn-spinner', btn).classList.remove('hidden');

  try {
    const res = await fetch('/placement/start', { method: 'POST' });
    const data = await res.json();

    if (!res.ok || data.error) {
      showStepError(1, data.error || 'Failed to start test.');
      return;
    }

    currentToken = data.token;
    currentSeeds = data.seeds;
    $('#tokenDisplay').textContent = data.token;

    // Reset ESP selector
    $('#espSelect').value = '';
    $('#espInstructions').classList.add('hidden');

    // Render seed addresses with default format
    renderSeedList(currentSeeds, ', ');

    goToStep(2);
  } catch (err) {
    showStepError(1, 'Network error. Please try again.');
  } finally {
    btn.disabled = false;
    $('.btn-text', btn).textContent = 'Generate Test Token';
    $('.btn-spinner', btn).classList.add('hidden');
  }
});

// ══════════════════════════════════════════════════════
//  ESP SELECTOR & SEED LIST RENDERING
// ══════════════════════════════════════════════════════
$('#espSelect').addEventListener('change', e => {
  const esp = e.target.value;
  currentEsp = esp;
  const config = ESP_CONFIG[esp];
  const instrEl = $('#espInstructions');

  if (!config) {
    instrEl.classList.add('hidden');
    renderSeedList(currentSeeds, ', ');
    return;
  }

  // Show ESP instructions
  instrEl.classList.remove('hidden');
  $('#espName').textContent = config.name;
  $('#espSteps').innerHTML = config.steps.map((step, i) =>
    `<div class="esp-step">
      <span class="esp-step__num">${i + 1}</span>
      <span class="esp-step__text">${step}</span>
    </div>`
  ).join('');

  // Re-render seed list with ESP-specific separator
  renderSeedList(currentSeeds, config.separator);
});

function renderSeedList(seeds, separator) {
  const seedList = $('#seedList');

  // Individual seeds
  seedList.innerHTML = seeds.map(s => `
    <div class="placement-seed">
      <div class="placement-seed__provider">
        <span class="placement-seed__icon">${PROVIDER_ICON[s.provider] || PROVIDER_ICON.default}</span>
        <span class="placement-seed__label">${escHtml(s.label)}</span>
      </div>
      <div class="placement-seed__email">
        <code>${escHtml(s.email)}</code>
        <button type="button" class="placement-seed__copy" data-email="${escAttr(s.email)}">Copy</button>
      </div>
    </div>`).join('');

  // Copy-all block — primary button uses ESP separator, secondary is the other format
  const allEmails = seeds.map(s => s.email).join(separator);
  const espName = currentEsp ? (ESP_CONFIG[currentEsp]?.name || '') : '';
  const primaryLabel = espName
    ? `Copy All for ${escHtml(espName)}`
    : 'Copy All';

  seedList.innerHTML += `
    <div class="placement-seed placement-seed--all">
      <div class="placement-seed--all__header">
        <span class="placement-seed--all__label">All seed addresses</span>
        <span class="placement-seed--all__count">${seeds.length} addresses</span>
      </div>
      <div class="placement-seed--all__preview">
        <code class="placement-seed--all__text" id="seedPreviewText">${escHtml(allEmails)}</code>
      </div>
      <div class="placement-seed__copy-group">
        <button type="button" class="placement-seed__copy placement-seed__copy--primary" data-email="${escAttr(allEmails)}">${primaryLabel}</button>
      </div>
    </div>`;
}

// ══════════════════════════════════════════════════════
//  STEP 2: CHECK RESULTS
// ══════════════════════════════════════════════════════
$('#checkResultsBtn').addEventListener('click', () => runCheck($('#checkResultsBtn')));
$('#recheckBtn').addEventListener('click', () => {
  clearAutoRecheck();
  runCheck($('#recheckBtn'));
});

let loadingMsgInterval = null;

function startLoadingMsgs(btn) {
  let idx = 0;
  const textEl = $('.btn-text', btn);
  textEl.textContent = LOADING_MSGS[0];
  loadingMsgInterval = setInterval(() => {
    idx = (idx + 1) % LOADING_MSGS.length;
    textEl.textContent = LOADING_MSGS[idx];
  }, 1800);
}

function stopLoadingMsgs() {
  clearInterval(loadingMsgInterval);
  loadingMsgInterval = null;
}

async function runCheck(btn) {
  if (!currentToken) return;

  btn.disabled = true;
  $('.btn-spinner', btn).classList.remove('hidden');
  startLoadingMsgs(btn);

  try {
    const res = await fetch('/placement/check', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token: currentToken }),
    });
    const data = await res.json();

    stopLoadingMsgs();

    if (!res.ok || data.error) {
      showStepError(3, data.error || 'Check failed.');
      goToStep(3);
      return;
    }

    renderResults(data);
    goToStep(3);

    // If all not_found, start auto-recheck countdown
    if (data.summary.not_found === data.summary.total) {
      startAutoRecheck();
    }
  } catch (err) {
    stopLoadingMsgs();
    showStepError(3, 'Network error. Please try again.');
    goToStep(3);
  } finally {
    btn.disabled = false;
    const isRecheck = btn.id === 'recheckBtn';
    $('.btn-text', btn).textContent = isRecheck
      ? 'Re-check (email may still be arriving)'
      : 'Check Results';
    $('.btn-spinner', btn).classList.add('hidden');
  }
}

// ══════════════════════════════════════════════════════
//  AUTO-RECHECK COUNTDOWN
// ══════════════════════════════════════════════════════
function startAutoRecheck() {
  clearAutoRecheck();
  autoRecheckSeconds = 45;

  const recheckBtn = $('#recheckBtn');
  const textEl = $('.btn-text', recheckBtn);

  autoRecheckTimer = setInterval(() => {
    autoRecheckSeconds--;
    if (autoRecheckSeconds <= 0) {
      clearAutoRecheck();
      textEl.textContent = 'Re-check (email may still be arriving)';
      runCheck(recheckBtn);
    } else {
      textEl.textContent = `Auto re-check in ${autoRecheckSeconds}s...`;
    }
  }, 1000);
}

function clearAutoRecheck() {
  if (autoRecheckTimer) {
    clearInterval(autoRecheckTimer);
    autoRecheckTimer = null;
  }
  autoRecheckSeconds = 0;
  const recheckBtn = $('#recheckBtn');
  if (recheckBtn) {
    $('.btn-text', recheckBtn).textContent = 'Re-check (email may still be arriving)';
  }
}

// ══════════════════════════════════════════════════════
//  RENDER RESULTS
// ══════════════════════════════════════════════════════
function renderResults(data) {
  const { results, summary } = data;

  // Summary bar
  const summaryEl = $('#resultsSummary');
  const total = summary.total;
  const inboxPct = total > 0 ? Math.round((summary.inbox / total) * 100) : 0;

  let summaryColor = 'var(--color-green)';
  let summaryIcon = '\u2713';
  let summaryText = `${summary.inbox}/${total} delivered to inbox (${inboxPct}%)`;

  if (summary.spam > 0 && summary.inbox > 0) {
    summaryColor = 'var(--color-orange)';
    summaryIcon = '\u26A0';
    summaryText = `${summary.inbox}/${total} inbox, ${summary.spam} spam`;
  } else if (summary.spam > 0 && summary.inbox === 0) {
    summaryColor = 'var(--color-red)';
    summaryIcon = '\u2717';
    summaryText = `All ${summary.spam} emails landed in spam`;
  }
  if (summary.not_found === total) {
    summaryColor = 'var(--color-yellow)';
    summaryIcon = '?';
    summaryText = 'Email not found in any mailbox yet';
  }

  summaryEl.innerHTML = `
    <div class="placement-summary-card" style="border-color:${summaryColor}">
      <span class="placement-summary-icon" style="color:${summaryColor}">${summaryIcon}</span>
      <div class="placement-summary-body">
        <span class="placement-summary-score" style="color:${summaryColor}">${inboxPct}%</span>
        <span class="placement-summary-label">Inbox Rate</span>
        <span class="placement-summary-text">${escHtml(summaryText)}</span>
        <span class="placement-summary-token">Token: ${escHtml(data.token)}</span>
      </div>
    </div>`;

  // Results grid — animate cards in with staggered delay
  const grid = $('#resultsGrid');
  grid.innerHTML = results.map((r, i) => {
    const cfg = PLACEMENT_CONFIG[r.placement] || PLACEMENT_CONFIG.not_found;
    const tabBadge = r.tab && r.tab !== 'primary'
      ? `<span class="placement-tab-badge placement-tab-badge--${r.tab}">${TAB_LABELS[r.tab] || r.tab}</span>`
      : r.tab === 'primary' ? '<span class="placement-tab-badge placement-tab-badge--primary">Primary</span>' : '';
    const timing = r.check_time_ms ? `<span class="placement-result__timing">${r.check_time_ms}ms</span>` : '';

    return `
      <div class="placement-result-card placement-result-card--${cfg.cls} placement-result-card--animate" style="animation-delay:${i * 100}ms">
        <div class="placement-result__header">
          <span class="placement-result__provider-icon">${PROVIDER_ICON[r.provider] || PROVIDER_ICON.default}</span>
          <div class="placement-result__provider-info">
            <span class="placement-result__provider-name">${escHtml(r.label)}</span>
            <span class="placement-result__email">${escHtml(r.email)}</span>
          </div>
          ${timing}
        </div>
        <div class="placement-result__status">
          <span class="placement-result__icon placement-result__icon--${cfg.cls}">${cfg.icon}</span>
          <span class="placement-result__label">${cfg.label}</span>
          ${tabBadge}
        </div>
        ${r.folder ? `<span class="placement-result__folder">Folder: ${escHtml(r.folder)}</span>` : ''}
        ${r.error ? `<span class="placement-result__error">${escHtml(r.error)}</span>` : ''}
      </div>`;
  }).join('');

  // Recommendations
  renderRecommendations(data.recommendations || []);
  renderPlacementUpgradeNudge(data);
}

// ══════════════════════════════════════════════════════
//  RECOMMENDATIONS
// ══════════════════════════════════════════════════════
const SEV_CONFIG = {
  critical: { icon: '\u2717', label: 'Critical',     cls: 'critical' },
  warning:  { icon: '\u26A0', label: 'Warning',      cls: 'warning' },
  info:     { icon: '\u2139', label: 'Suggestion',   cls: 'info' },
  pass:     { icon: '\u2713', label: 'Looking Good',  cls: 'pass' },
};

function renderRecommendations(recs) {
  const container = $('#placementRecs');
  if (!recs?.length) {
    container.innerHTML = '';
    return;
  }

  container.innerHTML = `
    <h3 class="placement-recs__title">Recommendations</h3>
    ${recs.map(rec => {
      const sev = SEV_CONFIG[rec.severity] || SEV_CONFIG.info;
      return `
        <div class="placement-rec placement-rec--${sev.cls}">
          <div class="placement-rec__header">
            <span class="placement-rec__icon placement-rec__icon--${sev.cls}">${sev.icon}</span>
            <div class="placement-rec__titles">
              <span class="placement-rec__severity">${sev.label}</span>
              <span class="placement-rec__title">${escHtml(rec.title)}</span>
            </div>
          </div>
          <p class="placement-rec__text">${escHtml(rec.text)}</p>
          ${rec.actions?.length ? `
            <ul class="placement-rec__actions">
              ${rec.actions.map(a => `<li>${escHtml(a)}</li>`).join('')}
            </ul>` : ''}
        </div>`;
    }).join('')}`;
}

// ══════════════════════════════════════════════════════
//  NAVIGATION BUTTONS
// ══════════════════════════════════════════════════════
$('#backToStep1').addEventListener('click', () => {
  currentToken = '';
  clearAutoRecheck();
  goToStep(1);
});

$('#newTestBtn').addEventListener('click', () => {
  currentToken = '';
  clearAutoRecheck();
  goToStep(1);
});

// ══════════════════════════════════════════════════════
//  COPY HANDLERS
// ══════════════════════════════════════════════════════
$('#copyTokenBtn').addEventListener('click', () => {
  copyText(currentToken, $('#copyTokenBtn'));
});

document.addEventListener('click', e => {
  const btn = e.target.closest('.placement-seed__copy');
  if (!btn) return;
  copyText(btn.dataset.email, btn);
});

function copyText(text, btn) {
  navigator.clipboard.writeText(text).then(() => {
    const orig = btn.textContent;
    btn.textContent = 'Copied!';
    setTimeout(() => { btn.textContent = orig; }, 1500);
  }).catch(() => {});
}

// ══════════════════════════════════════════════════════
//  ACCORDION (reuse pattern from other pages)
// ══════════════════════════════════════════════════════
document.addEventListener('click', e => {
  const trigger = e.target.closest('.accordion-trigger');
  if (!trigger) return;
  const body = $(`#${trigger.dataset.target}`);
  if (!body) return;
  const open = body.classList.toggle('open');
  trigger.classList.toggle('open', open);
});

// ══════════════════════════════════════════════════════
//  ERROR DISPLAY
// ══════════════════════════════════════════════════════
function showStepError(step, msg) {
  $$('.placement-error').forEach(el => el.remove());

  const el = document.createElement('div');
  el.className = 'placement-error';
  el.innerHTML = `<strong>Error:</strong> ${escHtml(msg)}`;

  const panel = $(`#step${step}`);
  if (panel) {
    const card = panel.querySelector('.placement-card') || panel;
    card.prepend(el);
  }
  setTimeout(() => el.remove(), 8000);
}

// ══════════════════════════════════════════════════════
//  UPGRADE NUDGE (Free-to-Paid)
// ══════════════════════════════════════════════════════
function renderPlacementUpgradeNudge(data) {
  const tier = window.__userTier || 'free';
  if (tier !== 'free') return;

  const container = $('#placementRecs');
  if (!container) return;

  const summary = data.summary || {};
  const spamCount = summary.spam || 0;

  let contextLine = 'Get alerted instantly if your inbox placement changes.';
  if (spamCount > 0) {
    contextLine = spamCount + ' email' + (spamCount > 1 ? 's' : '') + ' landed in spam. Pro alerts you when placement changes so you can act fast.';
  }

  container.insertAdjacentHTML('beforeend', `
    <div class="upgrade-nudge" style="margin-top:20px">
      <div class="upgrade-nudge__icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="20" height="20"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><path d="M22 6l-10 7L2 6"/></svg>
      </div>
      <div class="upgrade-nudge__body">
        <h3 class="upgrade-nudge__title">Never Miss a Placement Change</h3>
        <p class="upgrade-nudge__text">${escHtml(contextLine)}</p>
        <p class="upgrade-nudge__text"><strong>&#128196; PDF Reports</strong> — Download placement test results to share with your team.</p>
        <a href="/pricing" class="upgrade-nudge__cta">Upgrade to Pro &rarr;</a>
      </div>
    </div>`);
}

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
