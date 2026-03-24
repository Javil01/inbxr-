/* ══════════════════════════════════════════════════════
   InbXr — Email Test Analyzer
   ══════════════════════════════════════════════════════ */

'use strict';

const $ = (sel, ctx = document) => ctx.querySelector(sel);
const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

let currentToken = '';
let seedAddress = '';
let autoRecheckTimer = null;
let autoRecheckSeconds = 0;
let notFoundCount = 0;
let lastReportData = null;

const LOADING_MSGS = [
  'Connecting to seed mailbox...',
  'Searching for your email...',
  'Fetching raw message headers...',
  'Parsing authentication results...',
  'Analyzing transport security...',
  'Running spam and copy analysis...',
  'Checking sender reputation...',
  'Building your comprehensive report...',
];

const STATUS_ICON = { pass: '\u2713', warning: '\u26A0', fail: '\u2717', missing: '?', info: '\u2139' };
const STATUS_LABEL = { pass: 'Pass', warning: 'Warning', fail: 'Fail', missing: 'Not Found', info: 'Info' };

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
  // Scroll the active step into view so token/seed are visible without scrolling
  requestAnimationFrame(() => {
    const panel = $(`#step${n}`);
    if (panel) panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
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
    const res = await fetch('/email-test/start', { method: 'POST' });
    const data = await res.json();

    if (!res.ok || data.error) {
      showStepError(1, data.error || 'Failed to start test.');
      return;
    }

    currentToken = data.token;
    notFoundCount = 0;
    seedAddress = data.seed_email;
    $('#tokenDisplay').textContent = data.token;
    $('#seedEmail').textContent = data.seed_email;
    $('#exampleSubject').textContent = `Your subject line here ${data.token}`;

    goToStep(2);
  } catch (err) {
    showStepError(1, 'Network error. Please try again.');
  } finally {
    btn.disabled = false;
    $('.btn-text', btn).textContent = 'Start Email Test';
    $('.btn-spinner', btn).classList.add('hidden');
  }
});

// ══════════════════════════════════════════════════════
//  STEP 2: CHECK RESULTS
// ══════════════════════════════════════════════════════
$('#checkResultsBtn').addEventListener('click', () => runCheck($('#checkResultsBtn')));
$('#recheckBtn').addEventListener('click', () => {
  clearAutoRecheck();
  runCheck($('#recheckBtn'));
});

let loadingMsgInterval = null;
let loadingStepIdx = 0;

function startLoadingMsgs(btn) {
  loadingStepIdx = 0;
  const textEl = $('.btn-text', btn);
  textEl.textContent = LOADING_MSGS[0];
  loadingMsgInterval = setInterval(() => {
    loadingStepIdx = (loadingStepIdx + 1) % LOADING_MSGS.length;
    textEl.textContent = LOADING_MSGS[loadingStepIdx];
  }, 2000);

  // Show skeleton loading in step 3
  showSkeletonLoading();
}

function stopLoadingMsgs() {
  clearInterval(loadingMsgInterval);
  loadingMsgInterval = null;
  hideSkeletonLoading();
}

function showSkeletonLoading() {
  const panel = $('#step3');
  if (!panel) return;

  // Hide real content containers
  ['#etHeroSummary', '#etEmailGate', '#etEmailReport', '#espDiagnostic', '#etPlacementSummary', '#etAssessment', '#etHeaderGrades', '#etTransport', '#etIdentity', '#etScores', '#etReadability', '#etReputation', '#etAudit', '#etRawHeaders'].forEach(s => {
    const el = $(s);
    if (el) el.style.display = 'none';
  });
  $('.placement-actions').style.display = 'none';

  // Remove existing skeleton
  const existing = $('#etSkeleton');
  if (existing) existing.remove();

  const skeleton = document.createElement('div');
  skeleton.id = 'etSkeleton';
  skeleton.className = 'et-skeleton';
  skeleton.innerHTML = `
    <div class="et-skeleton-progress">
      <div class="et-skeleton-progress__bar">
        <div class="et-skeleton-progress__fill" id="etSkeletonFill"></div>
      </div>
      <div class="et-skeleton-progress__steps" id="etSkeletonSteps">
        ${LOADING_MSGS.map((msg, i) => `
          <div class="et-skeleton-step ${i === 0 ? 'et-skeleton-step--active' : ''}" data-step="${i}">
            <span class="et-skeleton-step__check">${i === 0 ? '<span class="et-skeleton-spinner"></span>' : ''}</span>
            <span class="et-skeleton-step__text">${msg}</span>
          </div>`).join('')}
      </div>
    </div>
    <div class="et-skeleton-cards">
      <div class="et-skeleton-card et-skeleton-card--wide">
        <div class="et-skeleton-line et-skeleton-line--lg"></div>
        <div class="et-skeleton-line et-skeleton-line--md"></div>
      </div>
      <div class="et-skeleton-grid">
        <div class="et-skeleton-card"><div class="et-skeleton-line et-skeleton-line--sm"></div><div class="et-skeleton-line et-skeleton-line--lg"></div><div class="et-skeleton-line et-skeleton-line--md"></div></div>
        <div class="et-skeleton-card"><div class="et-skeleton-line et-skeleton-line--sm"></div><div class="et-skeleton-line et-skeleton-line--lg"></div><div class="et-skeleton-line et-skeleton-line--md"></div></div>
        <div class="et-skeleton-card"><div class="et-skeleton-line et-skeleton-line--sm"></div><div class="et-skeleton-line et-skeleton-line--lg"></div><div class="et-skeleton-line et-skeleton-line--md"></div></div>
      </div>
    </div>`;

  panel.prepend(skeleton);

  // Animate progress steps
  startSkeletonStepAnimation();
}

let skeletonStepTimer = null;
function startSkeletonStepAnimation() {
  let step = 0;
  skeletonStepTimer = setInterval(() => {
    step++;
    if (step >= LOADING_MSGS.length) { clearInterval(skeletonStepTimer); return; }
    const steps = $$('.et-skeleton-step');
    const fill = $('#etSkeletonFill');
    if (fill) fill.style.width = `${((step + 1) / LOADING_MSGS.length) * 100}%`;
    steps.forEach((el, i) => {
      if (i < step) {
        el.classList.remove('et-skeleton-step--active');
        el.classList.add('et-skeleton-step--done');
        el.querySelector('.et-skeleton-step__check').innerHTML = '\u2713';
      } else if (i === step) {
        el.classList.add('et-skeleton-step--active');
        el.querySelector('.et-skeleton-step__check').innerHTML = '<span class="et-skeleton-spinner"></span>';
      }
    });
  }, 2000);
}

function hideSkeletonLoading() {
  clearInterval(skeletonStepTimer);
  const skeleton = $('#etSkeleton');
  if (skeleton) {
    skeleton.classList.add('et-skeleton--fade');
    setTimeout(() => skeleton.remove(), 300);
  }
  // Restore elements hidden by showSkeletonLoading
  ['#etHeroSummary', '#etEmailReport', '#espDiagnostic', '#etPlacementSummary', '#etAssessment', '#etHeaderGrades', '#etTransport', '#etIdentity', '#etScores', '#etReadability', '#etReputation', '#etAudit', '#etRawHeaders'].forEach(s => {
    const el = $(s);
    if (el) el.style.display = '';
  });
  $('.placement-actions').style.display = '';
}

async function runCheck(btn) {
  if (!currentToken) return;

  btn.disabled = true;
  $('.btn-spinner', btn).classList.remove('hidden');
  startLoadingMsgs(btn);
  goToStep(3);

  try {
    const res = await fetch('/email-test/check', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token: currentToken }),
    });
    const data = await res.json();

    stopLoadingMsgs();

    if (!res.ok || data.error) {
      showStepError(3, data.error || 'Check failed.');
      return;
    }

    if (data.status === 'not_found') {
      notFoundCount++;
      renderNotFound();
      if (notFoundCount < 4) {
        showScanCompleteFlash();
        startAutoRecheck();
      }
      return;
    }

    renderFullReport(data);

  } catch (err) {
    stopLoadingMsgs();
    showStepError(3, 'Network error. Please try again.');
  } finally {
    btn.disabled = false;
    const isRecheck = btn.id === 'recheckBtn';
    $('.btn-text', btn).textContent = isRecheck
      ? 'Re-check (email may still be arriving)'
      : 'Analyze Received Email';
    $('.btn-spinner', btn).classList.add('hidden');
  }
}

// ══════════════════════════════════════════════════════
//  AUTO-RECHECK
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
//  SCAN COMPLETE FLASH — shows user a scan actually ran
// ══════════════════════════════════════════════════════
function showScanCompleteFlash() {
  var existing = document.getElementById('scanFlash');
  if (existing) existing.remove();

  var flash = document.createElement('div');
  flash.id = 'scanFlash';
  flash.className = 'et-scan-flash';
  flash.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg> Scan complete \u2014 email not found yet. Trying again shortly\u2026';

  var summary = $('#etPlacementSummary');
  if (summary) summary.insertBefore(flash, summary.firstChild);

  setTimeout(function() { flash.classList.add('et-scan-flash--visible'); }, 10);
  setTimeout(function() {
    flash.classList.remove('et-scan-flash--visible');
    setTimeout(function() { flash.remove(); }, 400);
  }, 4000);
}

// ══════════════════════════════════════════════════════
//  RENDER: NOT FOUND
// ══════════════════════════════════════════════════════
function renderNotFound() {
  let msg, extra = '';

  if (notFoundCount <= 1) {
    msg = "We scanned the mailbox \u2014 your email hasn\u2019t arrived yet. It may still be in transit. We\u2019ll automatically check again in 45 seconds.";
  } else if (notFoundCount === 2) {
    msg = "Scan #2 complete \u2014 still no email. Some servers take 1\u20132 minutes to deliver. We\u2019ll check once more automatically.";
  } else if (notFoundCount === 3) {
    msg = "Scan #3 complete \u2014 still not found. This is taking longer than usual. We\u2019ll try one more time.";
    extra = `
      <div class="et-nf-tips">
        <strong>Quick checks:</strong>
        <ul>
          <li>Verify the token <code>${escHtml(currentToken)}</code> is in your subject line</li>
          <li>Confirm you sent to <code>${escHtml(seedAddress)}</code></li>
          <li>Check your outbox / sent folder to confirm the email left your system</li>
        </ul>
      </div>`;
  } else {
    msg = "Email not found after multiple checks. This usually means it was blocked, bounced, or filtered before reaching the mailbox. Don\u2019t worry — here\u2019s how to find out what happened.";
    extra = `
      <div class="et-nf-next-steps">
        <h3 class="et-nf-next-steps__title">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="20" height="20"><path d="M9 18l6-6-6-6"/></svg>
          Recommended Next Steps
        </h3>

        <div class="et-nf-recommend et-nf-recommend--primary">
          <div class="et-nf-recommend__icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="24" height="24"><rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8"/><path d="M12 17v4"/></svg>
          </div>
          <div class="et-nf-recommend__body">
            <strong>Run a Free Inbox Placement Test</strong>
            <p>See exactly where your emails land — inbox, spam, or blocked — across Gmail, Outlook, Yahoo, iCloud, and more. This will tell you if the issue is with one provider or all of them.</p>
            <a href="/placement" class="et-nf-recommend__btn">Run Free Placement Test &rarr;</a>
          </div>
        </div>

        <div class="et-nf-recommend-grid">
          <a href="/sender" class="et-nf-recommend-card">
            <div class="et-nf-recommend-card__icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="20" height="20"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
            </div>
            <strong>Check Your Auth Records</strong>
            <span>Verify SPF, DKIM, DMARC are set up correctly — a missing record is the #1 cause of blocked emails.</span>
          </a>
          <a href="/blacklist-monitor" class="et-nf-recommend-card">
            <div class="et-nf-recommend-card__icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="20" height="20"><circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/></svg>
            </div>
            <strong>Scan 110+ Blocklists</strong>
            <span>Check if your domain or IP is listed on a blocklist — one listing can silently kill your deliverability.</span>
          </a>
        </div>

        <div class="et-nf-tips">
          <strong>Also worth checking:</strong>
          <ul>
            <li><strong>Bounce-back emails</strong> — check your sent folder or ESP dashboard for delivery failure notices</li>
            <li><strong>Subject line token</strong> — confirm <code>${escHtml(currentToken)}</code> was in the subject line exactly as shown</li>
            <li><strong>Sending address</strong> — verify you sent to <code>${escHtml(seedAddress)}</code></li>
            <li><strong>ESP sending limits</strong> — new accounts or cold domains often get throttled</li>
          </ul>
        </div>
      </div>`;
  }

  const borderColor = notFoundCount >= 4 ? 'var(--color-red)' : 'var(--color-yellow)';
  const icon = notFoundCount >= 4 ? '\u2717' : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>';
  const title = notFoundCount >= 4 ? 'Delivery Issue Detected' : 'Scan Complete \u2014 Not Found Yet';
  const attemptText = notFoundCount > 1 ? ` &middot; Attempt ${notFoundCount}` : '';

  $('#etPlacementSummary').innerHTML = `
    <div class="placement-summary-card" style="border-color:${borderColor}">
      <span class="placement-summary-icon" style="color:${borderColor}">${icon}</span>
      <div class="placement-summary-body">
        <span class="placement-summary-score" style="color:${borderColor}">${title}</span>
        <span class="placement-summary-text">${msg}</span>
        <span class="placement-summary-token">Token: ${escHtml(currentToken)}${attemptText}</span>
      </div>
    </div>
    ${extra}`;

  // Hide all report sections
  ['#etHeaderGrades', '#etTransport', '#etIdentity', '#etScores', '#etReadability', '#etReputation', '#etAudit', '#etAssessment', '#etRawHeaders'].forEach(s => {
    const el = $(s);
    if (el) el.style.display = 'none';
  });
}

// ══════════════════════════════════════════════════════
//  RENDER: FULL REPORT
// ══════════════════════════════════════════════════════
// ══════════════════════════════════════════════════════
//  HERO SUMMARY CARD — Top-level verdict at a glance
// ══════════════════════════════════════════════════════
function renderHeroSummary(data) {
  const el = $('#etHeroSummary');
  if (!el) return;

  const p = data.placement;
  const spam = data.spam;
  const copy = data.copy;
  const grades = data.header_grades || [];

  // Determine placement status
  const inSpam = p && (p.placement === 'spam' || p.placement === 'trash');
  const inPromo = p && p.placement === 'inbox' && p.tab === 'promotions';
  const inPrimary = p && p.placement === 'inbox' && (!p.tab || p.tab === 'primary');

  // Count auth issues
  const authFails = grades.filter(g => g.status === 'fail').length;
  const authWarns = grades.filter(g => g.status === 'warning').length;
  const authPasses = grades.filter(g => g.status === 'pass').length;

  // Overall verdict
  let verdict, verdictColor, verdictIcon, verdictDesc;
  if (inSpam) {
    verdict = 'Landed in Spam';
    verdictColor = 'var(--color-red)';
    verdictIcon = '\u2717';
    verdictDesc = 'Your email was filtered to spam. Review the critical issues below to fix delivery.';
  } else if (inPromo) {
    verdict = 'Promotions Tab';
    verdictColor = 'var(--color-yellow)';
    verdictIcon = '\u26A0';
    verdictDesc = 'Delivered but sorted into Gmail\'s Promotions tab, which gets 50-70% lower open rates.';
  } else if (inPrimary && authFails === 0 && (!spam || spam.score <= 20)) {
    verdict = 'Looking Good';
    verdictColor = 'var(--color-green)';
    verdictIcon = '\u2713';
    verdictDesc = 'Your email passed key checks and landed in the primary inbox.';
  } else if (inPrimary) {
    verdict = 'Inbox — With Issues';
    verdictColor = 'var(--color-blue)';
    verdictIcon = '\u2139';
    verdictDesc = 'Delivered to inbox, but some issues were found that could affect future sends.';
  } else {
    verdict = 'Results Ready';
    verdictColor = 'var(--color-blue)';
    verdictIcon = '\u2139';
    verdictDesc = 'Your email analysis is complete. Review the findings below.';
  }

  // Build mini-metric pills
  const pills = [];
  if (spam) {
    const sc = spam.score;
    const sColor = sc <= 20 ? 'var(--color-green)' : sc <= 40 ? 'var(--color-yellow)' : 'var(--color-red)';
    pills.push(`<div class="hero-pill"><span class="hero-pill__label">Spam Risk</span><span class="hero-pill__value" style="color:${sColor}">${sc}/100</span></div>`);
  }
  if (copy) {
    const cc = copy.score;
    const cColor = cc >= 70 ? 'var(--color-green)' : cc >= 50 ? 'var(--color-yellow)' : 'var(--color-red)';
    pills.push(`<div class="hero-pill"><span class="hero-pill__label">Copy Score</span><span class="hero-pill__value" style="color:${cColor}">${cc}/100</span></div>`);
  }
  // Auth summary pill
  const authTotal = grades.length;
  if (authTotal > 0) {
    const aColor = authFails > 0 ? 'var(--color-red)' : authWarns > 0 ? 'var(--color-yellow)' : 'var(--color-green)';
    pills.push(`<div class="hero-pill"><span class="hero-pill__label">Auth Checks</span><span class="hero-pill__value" style="color:${aColor}">${authPasses}/${authTotal} pass</span></div>`);
  }

  // Top action item
  let topAction = '';
  if (inSpam && authFails > 0) {
    const failNames = grades.filter(g => g.status === 'fail').map(g => g.label).join(', ');
    topAction = `<div class="hero-action hero-action--critical"><span class="hero-action__icon">\u2717</span><span>Fix first: <strong>${escHtml(failNames)}</strong> — authentication failures are the #1 cause of spam filtering.</span></div>`;
  } else if (inSpam && spam && spam.score > 50) {
    topAction = `<div class="hero-action hero-action--critical"><span class="hero-action__icon">\u26A0</span><span>Fix first: <strong>High spam risk score (${spam.score}/100)</strong> — review flagged content triggers below.</span></div>`;
  } else if (inPromo) {
    topAction = `<div class="hero-action hero-action--warning"><span class="hero-action__icon">\u26A0</span><span>To reach Primary: reduce HTML complexity, limit links to 1-2, and write like a person, not a brand.</span></div>`;
  } else if (authFails > 0) {
    const failNames = grades.filter(g => g.status === 'fail').map(g => g.label).join(', ');
    topAction = `<div class="hero-action hero-action--warning"><span class="hero-action__icon">\u26A0</span><span>Fix first: <strong>${escHtml(failNames)}</strong> — failing authentication hurts deliverability over time.</span></div>`;
  } else if (spam && spam.score > 40) {
    topAction = `<div class="hero-action hero-action--warning"><span class="hero-action__icon">\u26A0</span><span>Your spam risk score is <strong>${spam.score}/100</strong> — review flagged content triggers to reduce filtering risk.</span></div>`;
  }

  // Icon bg color (10% opacity version)
  const iconBgMap = {
    'var(--color-red)': 'rgba(239,68,68,0.1)',
    'var(--color-yellow)': 'rgba(245,158,11,0.1)',
    'var(--color-green)': 'rgba(34,197,94,0.1)',
    'var(--color-blue)': 'rgba(59,130,246,0.1)',
  };
  const iconBg = iconBgMap[verdictColor] || 'rgba(59,130,246,0.1)';

  el.innerHTML = `
    <div class="hero-summary" style="--hero-color:${verdictColor}">
      <div class="hero-summary__top">
        <div class="hero-summary__verdict">
          <span class="hero-summary__icon" style="background:${iconBg}">${verdictIcon}</span>
          <div class="hero-summary__text">
            <span class="hero-summary__title">${escHtml(verdict)}</span>
            <span class="hero-summary__desc">${escHtml(verdictDesc)}</span>
          </div>
        </div>
        <div class="hero-summary__pills">${pills.join('')}</div>
      </div>
      ${topAction}
    </div>`;
  el.style.display = '';
}

function renderFullReport(data) {
  clearAutoRecheck();
  lastReportData = data;

  // ── Hero summary card (top-level verdict) ──
  renderHeroSummary(data);

  // ── Email gate for anonymous users ──
  if (data.gated) {
    renderGatedView(data);
    return;
  }

  // Hide gate if returning user
  const gate = $('#etEmailGate');
  if (gate) gate.style.display = 'none';

  // ── Placement summary ──
  const p = data.placement;
  const placementColors = {
    inbox: 'var(--color-green)', spam: 'var(--color-red)',
    trash: 'var(--color-red)', not_found: 'var(--color-yellow)',
  };
  const placementIcons = { inbox: '\u2713', spam: '\u2717', trash: '\u2717', not_found: '?' };
  const placementLabels = { inbox: 'Inbox', spam: 'Spam', trash: 'Trash', not_found: 'Not Found' };
  const color = placementColors[p.placement] || 'var(--color-blue)';
  const tabBadge = p.tab && p.tab !== 'primary'
    ? `<span class="placement-tab-badge placement-tab-badge--${p.tab}">${escHtml(p.tab.charAt(0).toUpperCase() + p.tab.slice(1))}</span>`
    : p.tab === 'primary' ? '<span class="placement-tab-badge placement-tab-badge--primary">Primary</span>' : '';

  $('#etPlacementSummary').innerHTML = `
    <div class="placement-summary-card" style="border-color:${color}">
      <span class="placement-summary-icon" style="color:${color}">${placementIcons[p.placement] || '?'}</span>
      <div class="placement-summary-body">
        <span class="placement-summary-score" style="color:${color}">${placementLabels[p.placement] || 'Unknown'}</span>
        <span class="placement-summary-label">Delivered to ${escHtml(p.folder || 'unknown')} ${tabBadge}</span>
        <span class="placement-summary-text">
          From: <strong>${escHtml(data.content?.from_header || data.content?.sender_email || '?')}</strong>
          &middot; Subject: <strong>${escHtml(data.content?.clean_subject || data.content?.subject || '?')}</strong>
        </span>
        <span class="placement-summary-token">Token: ${escHtml(currentToken)} &middot; ${escHtml(p.provider)} seed &middot; ${data.meta?.elapsed_ms || 0}ms</span>
      </div>
    </div>`;

  // ── ESP Diagnostic Banner ──
  renderEspDiagnostic(data.esp_diagnostic);

  // ── Header grades ──
  renderHeaderGrades(data.header_grades || []);

  // ── Transport ──
  renderTransport(data.headers?.transport);

  // ── Identity & compliance ──
  renderIdentity(data.headers?.identity, data.headers?.list_unsubscribe, data.headers?.dkim_signature, data.headers?.mime);

  // ── Content scores ──
  renderScores(data.spam, data.copy);

  // ── Readability ──
  renderReadability(data.readability);

  // ── Reputation ──
  renderReputation(data.reputation);

  // ── Audit ──
  renderAudit(data.audit);

  // ── Raw headers ──
  renderRawHeaders(data.headers?.all_headers);

  // ── Assessment summary (runs last so it can reference all data) ──
  renderAssessment(data);

  // ── Full Audit CTA (auto-extract domain from received email) ──
  setupFullAuditCTA(data);
  renderMoveToPrimary(data);
  renderPrimaryOptimizer(data);
  renderSafetyWarning(data);
  renderNextSteps(data);
  renderUpgradeNudges(data);
  renderEmailPreview(data);
  setupEmailReport();

  // Show all sections with staggered reveal
  const revealSections = ['#etHeroSummary', '#etEmailReport', '#espDiagnostic', '#etAssessment', '#etHeaderGrades', '#etTransport', '#etIdentity', '#etScores', '#etReadability', '#etReputation', '#etAudit', '#etFullAuditCta', '#etMoveToPrimary', '#etPrimaryOptimizer', '#etSafetyWarning', '#etNextSteps', '#etUpgradeNudge', '#etEmailPreview', '#etRawHeaders'];
  revealSections.forEach((s, i) => {
    const el = $(s);
    if (el && el.style.display !== 'none') {
      el.classList.add('et-section-reveal');
      el.style.animationDelay = `${i * 100}ms`;
    }
  });
  // Also ensure initially hidden sections that got shown get the class
  ['#etHeaderGrades', '#etTransport', '#etIdentity', '#etRawHeaders'].forEach(s => {
    const el = $(s);
    if (el) el.style.display = '';
  });
}

// ══════════════════════════════════════════════════════
//  GATED VIEW — Summary + Blurred Preview + Email Gate
// ══════════════════════════════════════════════════════
function renderGatedView(data) {
  const gateEl = $('#etEmailGate');
  if (!gateEl) return;

  // Hide all full report sections
  ['#etEmailReport', '#espDiagnostic', '#etPlacementSummary', '#etAssessment',
   '#etHeaderGrades', '#etTransport', '#etIdentity', '#etScores', '#etReadability',
   '#etReputation', '#etAudit', '#etRawHeaders', '#etFullAuditCta', '#etMoveToPrimary',
   '#etPrimaryOptimizer', '#etSafetyWarning', '#etNextSteps', '#etUpgradeNudge',
   '#etEmailPreview'].forEach(s => {
    const el = $(s);
    if (el) el.style.display = 'none';
  });
  $('.placement-actions').style.display = 'none';

  // Build issue summary
  const grades = data.header_grades || [];
  const spam = data.spam || {};
  const copy = data.copy || {};
  const placement = data.placement || {};

  let criticalCount = 0;
  let warningCount = 0;

  grades.forEach(g => {
    if (g.status === 'fail') criticalCount++;
    else if (g.status === 'warning') warningCount++;
  });
  if (placement.placement === 'spam' || placement.placement === 'trash') criticalCount++;
  if (spam.score > 60) criticalCount++;
  else if (spam.score > 40) warningCount++;
  if (placement.tab === 'promotions') warningCount++;

  const summaryEl = $('#etIssueSummary');
  if (summaryEl) {
    const overallScore = Math.round(
      ((100 - (spam.score || 0)) + (copy.score || 50)) / 2
    );
    const scoreColor = overallScore >= 70 ? 'var(--color-green)' : overallScore >= 50 ? 'var(--color-yellow)' : 'var(--color-red)';

    let issuesPills = '';
    if (criticalCount > 0) {
      issuesPills += `<span class="gate-pill gate-pill--critical">${criticalCount} critical</span>`;
    }
    if (warningCount > 0) {
      issuesPills += `<span class="gate-pill gate-pill--warning">${warningCount} warning${warningCount > 1 ? 's' : ''}</span>`;
    }
    if (criticalCount === 0 && warningCount === 0) {
      issuesPills = '<span class="gate-pill gate-pill--good">No issues found</span>';
    }

    summaryEl.innerHTML = `
      <div class="gate-summary">
        <div class="gate-summary__score" style="--score-color:${scoreColor}">
          <span class="gate-summary__number">${overallScore}</span>
          <span class="gate-summary__label">/100</span>
        </div>
        <div class="gate-summary__details">
          <h3 class="gate-summary__title">Your email scores ${overallScore}/100</h3>
          <div class="gate-summary__pills">${issuesPills}</div>
        </div>
      </div>`;
  }

  // Build blurred preview (fake report sections)
  const blurEl = $('#etGatedBlur');
  if (blurEl) {
    blurEl.innerHTML = `
      <div class="et-section" style="opacity:0.6">
        <h3 class="et-section__title">Assessment Summary</h3>
        <div style="display:grid;gap:12px">
          <div style="height:60px;background:var(--bg-2);border-radius:8px;border:1px solid var(--border-1)"></div>
          <div style="height:80px;background:var(--bg-2);border-radius:8px;border:1px solid var(--border-1)"></div>
          <div style="height:45px;background:var(--bg-2);border-radius:8px;border:1px solid var(--border-1)"></div>
        </div>
      </div>
      <div class="et-section" style="opacity:0.5">
        <h3 class="et-section__title">Authentication &amp; Header Analysis</h3>
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:12px">
          <div style="height:90px;background:var(--bg-2);border-radius:8px;border:1px solid var(--border-1)"></div>
          <div style="height:90px;background:var(--bg-2);border-radius:8px;border:1px solid var(--border-1)"></div>
          <div style="height:90px;background:var(--bg-2);border-radius:8px;border:1px solid var(--border-1)"></div>
          <div style="height:90px;background:var(--bg-2);border-radius:8px;border:1px solid var(--border-1)"></div>
        </div>
      </div>
      <div class="et-section" style="opacity:0.4">
        <h3 class="et-section__title">Content Analysis</h3>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
          <div style="height:100px;background:var(--bg-2);border-radius:8px;border:1px solid var(--border-1)"></div>
          <div style="height:100px;background:var(--bg-2);border-radius:8px;border:1px solid var(--border-1)"></div>
        </div>
      </div>`;
  }

  gateEl.style.display = '';
  gateEl.classList.add('et-section-reveal');

  // Wire up gate form
  const gateInput = $('#gateEmailInput');
  const gateBtn = $('#gateEmailBtn');
  const gateStatus = $('#gateEmailStatus');

  gateBtn.onclick = () => submitGateEmail();
  gateInput.onkeydown = (e) => { if (e.key === 'Enter') submitGateEmail(); };
}

async function submitGateEmail() {
  const input = $('#gateEmailInput');
  const btn = $('#gateEmailBtn');
  const status = $('#gateEmailStatus');
  const email = (input.value || '').trim();

  if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    status.textContent = 'Please enter a valid email address.';
    status.className = 'et-gate-card__status et-gate-card__status--error';
    input.focus();
    return;
  }

  btn.disabled = true;
  $('.btn-text', btn).textContent = 'Verifying...';
  $('.btn-spinner', btn).classList.remove('hidden');
  status.textContent = '';

  try {
    const token = lastReportData?._token || currentToken;
    const res = await fetch('/api/unlock-report', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, token }),
    });
    const result = await res.json();

    if (res.ok && result.ok) {
      status.innerHTML = 'Unlocking your report... We also sent a copy to <strong>' + escHtml(email) + '</strong>';
      status.className = 'et-gate-card__status et-gate-card__status--success';
      $('.btn-spinner', btn).classList.add('hidden');
      $('.btn-text', btn).textContent = 'Unlocked!';
      if (result.analysis) lastReportData = result.analysis;
      setTimeout(() => {
        const gate = $('#etEmailGate');
        if (gate) gate.style.display = 'none';
        if (lastReportData) {
          lastReportData.gated = false;
          renderFullReport(lastReportData);
        }
      }, 1500);
    } else {
      status.textContent = result.error || 'Something went wrong. Try again.';
      status.className = 'et-gate-card__status et-gate-card__status--error';
      btn.disabled = false;
      $('.btn-text', btn).textContent = 'Send My Report';
      $('.btn-spinner', btn).classList.add('hidden');
    }
  } catch (err) {
    status.textContent = 'Network error. Please try again.';
    status.className = 'et-gate-card__status et-gate-card__status--error';
    btn.disabled = false;
    $('.btn-text', btn).textContent = 'Send My Report';
    $('.btn-spinner', btn).classList.add('hidden');
  }
}

// ── ESP vs Domain Diagnostic ────────────────────────
function renderEspDiagnostic(diag) {
  var diagEl = $('#espDiagnostic');
  if (!diagEl) return;
  if (!diag || diag.verdict === 'unknown') {
    diagEl.style.display = 'none';
    return;
  }
  var diagColors = {clean:'#22c55e', domain:'#ef4444', content:'#f59e0b', esp:'#ef4444', both:'#ef4444'};
  var diagIcons = {clean:'&#10003;', domain:'&#9888;', content:'&#9888;', esp:'&#9888;', both:'&#10007;'};
  var diagLabels = {clean:'All Clear', domain:'Domain Issue', content:'Content Issue', esp:'ESP Issue', both:'Multiple Issues'};
  var color = diagColors[diag.verdict] || '#64748b';
  diagEl.innerHTML = '<div style="padding:16px;border-radius:12px;border:1px solid ' + color + '30;background:' + color + '08;margin-bottom:20px;">' +
    '<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">' +
      '<span style="font-size:1.2rem;color:' + color + ';">' + (diagIcons[diag.verdict] || '') + '</span>' +
      '<strong style="font-size:0.92rem;">Diagnosis: ' + (diagLabels[diag.verdict] || diag.verdict) + '</strong>' +
    '</div>' +
    '<p style="font-size:0.85rem;color:var(--text-2);margin:0 0 8px;">' + escHtml(diag.message) + '</p>' +
    (diag.details && diag.details.length ? '<ul style="font-size:0.78rem;color:var(--text-3);margin:0;padding-left:18px;">' + diag.details.map(function(d){ return '<li>' + escHtml(d) + '</li>'; }).join('') + '</ul>' : '') +
  '</div>';
  diagEl.style.display = 'block';
}

// ── Assessment summary ─────────────────────────────
function renderAssessment(data) {
  try {
  const section = $('#etAssessment');
  const el = $('#etAssessmentContent');
  if (!section || !el) return;
  section.style.display = '';

  const grades = data.header_grades || [];
  const spam = data.spam;
  const copy = data.copy;
  const readability = data.readability;
  const reputation = data.reputation;
  const audit = data.audit;
  const placement = data.placement;
  const content = data.content;
  const headers = data.headers || {};

  // ── Collect all findings ──
  const critical = [];   // Must fix — blocks delivery
  const warnings = [];   // Should fix — hurts deliverability
  const good = [];       // Passing — no action needed
  const info = [];       // Informational tips

  // 1. Authentication grades
  grades.forEach(g => {
    if (g.status === 'pass') {
      good.push({ label: g.label, text: g.verdict });
    } else if (g.status === 'fail') {
      critical.push({ label: g.label, text: g.verdict, fix: g.detail });
    } else if (g.status === 'warning') {
      warnings.push({ label: g.label, text: g.verdict, fix: g.detail });
    }
  });

  // 2. Placement
  if (placement) {
    if (placement.placement === 'spam') {
      critical.push({
        label: 'Inbox Placement',
        text: 'Your email landed in the spam folder.',
        fix: 'Review authentication failures above and content analysis below. Common causes: failed SPF/DKIM/DMARC, spammy content, poor sender reputation, or missing List-Unsubscribe header.',
      });
    } else if (placement.placement === 'trash') {
      critical.push({
        label: 'Inbox Placement',
        text: 'Your email was sent to trash.',
        fix: 'This is severe — the receiving server actively rejected your email. Check for blocklist listings, authentication failures, and domain reputation issues.',
      });
    } else if (placement.placement === 'inbox') {
      if (placement.tab && placement.tab === 'promotions') {
        warnings.push({
          label: 'Gmail Promotions Tab',
          text: 'Your email landed in Promotions, not Primary. Promotions emails get 50-70% lower open rates.',
          fix: 'How to escape the Promotions tab:\n' +
            '1. Strip heavy HTML — send plain or minimal HTML (like a real person would)\n' +
            '2. Use only 1 link max — multiple links scream "marketing email"\n' +
            '3. Remove all images or keep just 1 — image-heavy = promotional\n' +
            '4. Write like a human — "Hey [name]" not "Dear valued customer"\n' +
            '5. Send from a person\'s name (e.g. "Sarah from Acme") not a brand\n' +
            '6. Drop promotional words — no "buy now", "limited offer", "exclusive deal"\n' +
            '7. Get replies — ask a question, Gmail learns from engagement\n' +
            '8. Ask subscribers to drag your email to Primary (one-time, trains Gmail)\n' +
            '9. Keep your list clean — unengaged subscribers hurt placement\n' +
            '10. Send consistently — erratic volume triggers filters',
        });
      } else if (placement.tab && placement.tab === 'updates') {
        info.push({
          label: 'Gmail Updates Tab',
          text: 'Delivered to inbox but sorted into Updates tab.',
          fix: 'Updates tab is typical for transactional/notification emails. To reach Primary: make the content more personal and conversational, avoid subject lines that look like notifications.',
        });
      } else {
        good.push({ label: 'Inbox Placement', text: `Delivered to ${placement.tab || 'Primary inbox'} — no issues detected.` });
      }
    }
  }

  // 3. Spam score (lower = better, it's a RISK score: 0 = no risk, 100 = max risk)
  if (spam) {
    const spamFlags = spam.top_recommendations || spam.high_risk_elements || [];
    const topFlags = spamFlags.slice(0, 3).map(f => f.item || f.recommendation || '').filter(Boolean);
    const flagHint = topFlags.length ? '\nTop signals: ' + topFlags.join('; ') : '';

    if (spam.score <= 10) {
      good.push({ label: 'Spam Risk Score', text: `${spam.score}/100 — ${spam.label || 'Very Low Risk'}` });
    } else if (spam.score <= 20) {
      info.push({
        label: 'Spam Risk Score',
        text: `${spam.score}/100 — ${spam.label || 'Very Low Risk'}`,
        fix: 'Minimal spam signals detected — unlikely to cause filtering issues, but reviewing flagged items can still improve deliverability.' + flagHint,
      });
    } else if (spam.score <= 40) {
      info.push({
        label: 'Spam Risk Score',
        text: `${spam.score}/100 — ${spam.label || 'Low Risk'}`,
        fix: 'A few spam signals were flagged. While this is unlikely to land you in spam on its own, addressing these items is good practice — especially if combined with weak authentication or low sender reputation.' + flagHint,
      });
    } else if (spam.score <= 60) {
      warnings.push({
        label: 'Spam Risk Score',
        text: `${spam.score}/100 — ${spam.label || 'Moderate Risk'}`,
        fix: 'Meaningful spam signals found. Address flagged items before sending to a large list. Run your copy through the Email Analyzer for specific rewrite suggestions.' + flagHint,
      });
    } else if (spam.score <= 80) {
      critical.push({
        label: 'Spam Risk Score',
        text: `${spam.score}/100 — ${spam.label || 'High Risk'}`,
        fix: 'Your email has significant spam signals. Common issues: excessive capitalization, urgency words (act now, limited time), too many links, suspicious phrases, or heavy HTML formatting. Use the Email Analyzer for a line-by-line breakdown.' + flagHint,
      });
    } else {
      critical.push({
        label: 'Spam Risk Score',
        text: `${spam.score}/100 — ${spam.label || 'Very High Risk'}`,
        fix: 'Your content is flagging heavily as spam. Rewrite your subject line and body to remove aggressive sales language, reduce link density, and improve text-to-image ratio. Run your copy through the Email Analyzer for specific rewrite suggestions.' + flagHint,
      });
    }
  }

  // 4. Copy score
  if (copy) {
    if (copy.score >= 80) {
      good.push({ label: 'Copy Effectiveness', text: `${copy.score}/100 — ${copy.label || 'Strong'}` });
    } else if (copy.score >= 60) {
      info.push({
        label: 'Copy Effectiveness',
        text: `${copy.score}/100 — ${copy.label || 'Average'}`,
        fix: 'Your email copy is functional but could be stronger. Consider improving your subject line clarity, adding a stronger call-to-action, and making the opening line more compelling.',
      });
    } else {
      warnings.push({
        label: 'Copy Effectiveness',
        text: `${copy.score}/100 — ${copy.label || 'Needs work'}`,
        fix: 'Your email copy needs improvement. Focus on: a clear value proposition in the subject line, a strong opening hook, one primary call-to-action, and benefit-driven language. Use the Email Analyzer for AI-powered rewrite suggestions.',
      });
    }
  }

  // 5. Readability
  if (readability) {
    if (readability.score >= 70) {
      good.push({ label: 'Readability', text: `Score ${readability.score}/100 — Grade level: ${readability.grade_level || '?'}` });
    } else if (readability.score >= 50) {
      info.push({
        label: 'Readability',
        text: `Score ${readability.score}/100 — Grade level: ${readability.grade_level || '?'}`,
        fix: 'Your email reads at a higher grade level than ideal for email marketing (aim for grades 5-8). Shorten sentences, use simpler words, and break up long paragraphs.',
      });
    } else {
      warnings.push({
        label: 'Readability',
        text: `Score ${readability.score}/100 — Grade level: ${readability.grade_level || '?'}`,
        fix: 'Your email is difficult to read quickly. Email readers spend ~11 seconds per email. Use short sentences (under 20 words), common vocabulary, bullet points, and clear paragraph breaks.',
      });
    }
  }

  // 6. Reputation / blocklists
  if (reputation) {
    const listed = reputation.reputation?.listed_count || 0;
    const repScore = reputation.combined?.score;
    if (listed > 0) {
      critical.push({
        label: 'Blocklist Status',
        text: `Listed on ${listed} blocklist${listed !== 1 ? 's' : ''}.`,
        fix: 'Blocklist listings cause widespread delivery failures. Steps to delist:\n1. Identify the blocklist(s) in the Reputation section below\n2. Visit each blocklist\'s website for their removal process\n3. Fix the underlying issue (compromised account, purchased list, spam complaints)\n4. For Spamhaus: visit spamhaus.org/lookup — for SpamCop: check spamcop.net/bl.shtml\n5. Monitor with Google Postmaster Tools after delisting.',
      });
    } else if (repScore !== undefined) {
      if (repScore >= 80) {
        good.push({ label: 'DNS Reputation', text: `Score ${repScore}/100 — Clean across all blocklists` });
      } else {
        warnings.push({
          label: 'DNS Reputation',
          text: `Score ${repScore}/100`,
          fix: 'Your DNS reputation score is below optimal. Review the DNS Reputation section below for specific authentication or configuration issues.',
        });
      }
    }
  }

  // 7. Audit checks
  if (audit?.checks) {
    const failedAudits = audit.checks.filter(c => !c.pass);
    if (failedAudits.length === 0) {
      good.push({ label: 'Pre-Send Audit', text: 'All audit checks passed.' });
    } else {
      failedAudits.forEach(c => {
        warnings.push({
          label: c.label || c.check || 'Audit Check',
          text: c.detail || 'Failed',
          fix: c.fix || null,
        });
      });
    }
  }

  // ── Calculate overall grade ──
  const totalChecks = critical.length + warnings.length + good.length + info.length;
  let overallGrade, overallColor, overallLabel;
  if (critical.length === 0 && warnings.length === 0) {
    overallGrade = 'A';
    overallColor = 'var(--color-green)';
    overallLabel = 'Excellent — your email follows all major best practices.';
  } else if (critical.length === 0 && warnings.length <= 2) {
    overallGrade = 'B';
    overallColor = 'var(--color-blue)';
    overallLabel = 'Good — minor improvements recommended below.';
  } else if (critical.length <= 1 && warnings.length <= 3) {
    overallGrade = 'C';
    overallColor = 'var(--color-yellow)';
    overallLabel = 'Fair — several issues may affect deliverability.';
  } else if (critical.length <= 2) {
    overallGrade = 'D';
    overallColor = 'var(--color-orange, #f59e0b)';
    overallLabel = 'Poor — significant issues will hurt inbox placement.';
  } else {
    overallGrade = 'F';
    overallColor = 'var(--color-red)';
    overallLabel = 'Critical — major deliverability problems detected.';
  }

  // ── Render ──
  let html = '';

  // Overall grade card
  html += `
    <div class="et-assessment-grade et-card-reveal" style="border-color:${overallColor}">
      <span class="et-assessment-grade__letter et-grade-pop" style="color:${overallColor}">${overallGrade}</span>
      <div class="et-assessment-grade__body">
        <span class="et-assessment-grade__label">${escHtml(overallLabel)}</span>
        <span class="et-assessment-grade__counts">
          ${critical.length ? `<span class="et-count et-count--critical">${critical.length} critical</span>` : ''}
          ${warnings.length ? `<span class="et-count et-count--warning">${warnings.length} warning${warnings.length !== 1 ? 's' : ''}</span>` : ''}
          ${good.length ? `<span class="et-count et-count--pass">${good.length} passed</span>` : ''}
          ${info.length ? `<span class="et-count et-count--info">${info.length} info</span>` : ''}
        </span>
      </div>
    </div>`;

  // Critical issues
  if (critical.length) {
    html += `<div class="et-assessment-group">
      <h4 class="et-assessment-group__title et-assessment-group__title--critical">Critical — Fix These First</h4>
      ${critical.map(item => _renderAssessmentItem(item, 'critical')).join('')}
    </div>`;
  }

  // Warnings
  if (warnings.length) {
    html += `<div class="et-assessment-group">
      <h4 class="et-assessment-group__title et-assessment-group__title--warning">Recommendations</h4>
      ${warnings.map(item => _renderAssessmentItem(item, 'warning')).join('')}
    </div>`;
  }

  // Info tips
  if (info.length) {
    html += `<div class="et-assessment-group">
      <h4 class="et-assessment-group__title et-assessment-group__title--info">Tips &amp; Suggestions</h4>
      ${info.map(item => _renderAssessmentItem(item, 'info')).join('')}
    </div>`;
  }

  // Passing
  if (good.length) {
    html += `<div class="et-assessment-group">
      <h4 class="et-assessment-group__title et-assessment-group__title--pass">Passing</h4>
      <div class="et-assessment-passing">
        ${good.map(item => `
          <div class="et-assessment-pass-item">
            <span class="et-assessment-pass-icon">\u2713</span>
            <span class="et-assessment-pass-label">${escHtml(item.label)}</span>
            <span class="et-assessment-pass-text">${escHtml(item.text)}</span>
          </div>`).join('')}
      </div>
    </div>`;
  }

  el.innerHTML = html;
  } catch (err) { console.error('[Assessment] Error:', err); }
}

function _renderAssessmentItem(item, severity) {
  const icons = { critical: '\u2717', warning: '\u26A0', info: '\u2139' };
  return `
    <div class="et-assessment-item et-assessment-item--${severity}">
      <span class="et-assessment-item__icon et-assessment-item__icon--${severity}">${icons[severity] || '?'}</span>
      <div class="et-assessment-item__body">
        <div class="et-assessment-item__head">
          <span class="et-assessment-item__label">${escHtml(item.label)}</span>
          <span class="et-assessment-item__text">${escHtml(item.text)}</span>
        </div>
        ${item.fix ? `<div class="et-assessment-item__fix">${escHtml(item.fix).replace(/\n/g, '<br>')}</div>` : ''}
      </div>
    </div>`;
}

// ── Header grades grid ──────────────────────────────
function renderHeaderGrades(grades) {
  window._etHeaderGrades = grades || [];
  const grid = $('#etGradesGrid');
  if (!grades?.length) { grid.innerHTML = ''; return; }

  grid.innerHTML = grades.map((g, i) => `
    <div class="et-grade-card et-grade-card--${g.status} et-card-reveal" style="animation-delay:${i * 80}ms">
      <div class="et-grade-card__head">
        <span class="et-grade-icon et-grade-icon--${g.status}">${STATUS_ICON[g.status] || '?'}</span>
        <span class="et-grade-label">${escHtml(g.label)}</span>
        <span class="et-grade-status">${STATUS_LABEL[g.status] || g.status}</span>
      </div>
      <div class="et-grade-verdict">${escHtml(g.verdict || '')}</div>
      ${g.detail ? `<div class="et-grade-detail">${escHtml(g.detail).replace(/\n/g, '<br>')}</div>` : ''}
    </div>`).join('');
}

// ── Transport & routing ─────────────────────────────
function renderTransport(transport) {
  if (!transport) return;
  const el = $('#etTransportContent');

  const signals = [];

  // Sender IP
  if (transport.sender_ip) {
    signals.push({ label: 'Sender IP', value: transport.sender_ip, status: 'info' });
  }

  // TLS
  signals.push({
    label: 'TLS Encryption',
    value: transport.tls_used
      ? `Encrypted${transport.tls_version ? ' (' + transport.tls_version + ')' : ''}${transport.tls_cipher ? ' — ' + transport.tls_cipher : ''}`
      : 'Not encrypted in transit',
    status: transport.tls_used ? 'pass' : 'fail',
  });

  // Hop count
  signals.push({
    label: 'Routing Hops',
    value: `${transport.hop_count} hop(s) from sender to mailbox`,
    status: transport.hop_count <= 5 ? 'pass' : 'warning',
  });

  el.innerHTML = `
    <div class="et-signals">
      ${signals.map(s => `
        <div class="rep-signal-row">
          <span class="rep-signal-icon auth-status-icon--${s.status}">${STATUS_ICON[s.status] || '\u2139'}</span>
          <div class="rep-signal-body">
            <span class="rep-signal-label">${escHtml(s.label)}</span>
            <span class="rep-signal-value">${escHtml(s.value)}</span>
          </div>
        </div>`).join('')}
    </div>
    ${transport.hops?.length ? `
      <div class="accordion-section">
        <button class="accordion-trigger" data-target="etHopsList"><span>Routing Chain</span><span class="badge-count">${transport.hops.length}</span><span class="accordion-arrow">&#9660;</span></button>
        <div class="accordion-body" id="etHopsList">
          <div class="et-hops">
            ${transport.hops.map((h, i) => `
              <div class="et-hop">
                <span class="et-hop__num">${i + 1}</span>
                <span class="et-hop__encrypted ${h.encrypted ? 'et-hop__encrypted--yes' : 'et-hop__encrypted--no'}">${h.encrypted ? 'TLS' : 'Plain'}</span>
                <span class="et-hop__detail">${escHtml((h.from_host || '?') + ' → ' + (h.by_host || '?'))}</span>
                ${h.ip ? `<code class="et-hop__ip">${escHtml(h.ip)}</code>` : ''}
              </div>`).join('')}
          </div>
        </div>
      </div>` : ''}`;
}

// ── Identity & compliance ───────────────────────────
function renderIdentity(identity, listUnsub, dkimSig, mime) {
  if (!identity) return;
  const el = $('#etIdentityContent');
  const signals = [];

  // From / Return-Path
  signals.push({
    label: 'From',
    value: identity.from || '?',
    status: 'info',
  });
  signals.push({
    label: 'Return-Path',
    value: identity.return_path || '(empty)',
    status: identity.aligned ? 'pass' : 'warning',
    note: identity.aligned ? 'Aligned with From domain' : 'Differs from From domain — may affect DMARC alignment',
  });

  // Message-ID
  if (identity.message_id) {
    signals.push({ label: 'Message-ID', value: identity.message_id, status: 'info' });
  }

  // X-Mailer
  if (identity.x_mailer) {
    signals.push({ label: 'Sending Client', value: identity.x_mailer, status: 'info' });
  }

  // List-Unsubscribe — use header_grades verdict if available (it checks body too)
  if (listUnsub) {
    let luStatus, luValue, luNote;
    if (listUnsub.present) {
      luStatus = listUnsub.one_click ? 'pass' : 'warning';
      luValue = listUnsub.one_click ? 'Present with RFC 8058 one-click' : 'Present' + (listUnsub.mailto ? ` (mailto: ${listUnsub.mailto})` : '') + (listUnsub.url ? ` (URL)` : '');
    } else {
      // Pull from header_grades if available (backend checks body for unsub links)
      const luGrade = (window._etHeaderGrades || []).find(g => g.label === 'List-Unsubscribe');
      if (luGrade) {
        luStatus = luGrade.status === 'pass' ? 'pass' : luGrade.status === 'warning' ? 'warning' : 'fail';
        luValue = luGrade.verdict;
        luNote = luGrade.detail;
      } else {
        luStatus = 'fail';
        luValue = 'Not present — required by Gmail and Yahoo for bulk senders';
      }
    }
    signals.push({ label: 'List-Unsubscribe', value: luValue, status: luStatus, note: luNote });
  }

  // DKIM Signature
  if (dkimSig?.present) {
    signals.push({
      label: 'DKIM Signature',
      value: `Signed by ${dkimSig.domain || '?'} (s=${dkimSig.selector || '?'}, a=${dkimSig.algorithm || '?'})`,
      status: 'pass',
      note: `${dkimSig.headers_signed?.length || 0} headers signed`,
    });
  }

  // MIME
  if (mime) {
    const mimeStatus = (mime.has_html && mime.has_plain_text) ? 'pass' : (mime.has_html && !mime.has_plain_text ? 'warning' : 'pass');
    const mimeValue = (mime.has_html && mime.has_plain_text) ? 'HTML + plain text (best practice)'
      : mime.has_html ? 'HTML only — add a plain text part for better compatibility'
      : 'Plain text only';
    signals.push({ label: 'MIME Structure', value: `${mimeValue} (${mime.part_count} parts)`, status: mimeStatus });
  }

  el.innerHTML = `<div class="et-signals">
    ${signals.map(s => `
      <div class="rep-signal-row">
        <span class="rep-signal-icon auth-status-icon--${s.status}">${STATUS_ICON[s.status] || '\u2139'}</span>
        <div class="rep-signal-body">
          <span class="rep-signal-label">${escHtml(s.label)}</span>
          <span class="rep-signal-value">${escHtml(s.value)}</span>
          ${s.note ? `<span class="rep-signal-note">${escHtml(s.note).replace(/\n/g, '<br>')}</span>` : ''}
        </div>
      </div>`).join('')}
  </div>`;
}

// ── Content scores ──────────────────────────────────
function renderScores(spam, copy) {
  if (!spam && !copy) return;
  const el = $('#etScoresRow');
  const section = $('#etScores');
  section.style.display = '';

  const cards = [];
  if (spam) {
    const sc = spam.score;
    const clr = sc <= 20 ? 'var(--color-green)' : sc <= 40 ? 'var(--color-blue)' : sc <= 60 ? 'var(--color-yellow)' : 'var(--color-red)';
    cards.push(`
      <div class="et-score-card et-score-card--reveal" style="border-top-color:${clr}; animation-delay: 0ms">
        <span class="et-score-card__title">Spam Risk</span>
        <span class="et-score-card__score" style="color:${clr}" data-target="${sc}" data-counting="true">0<small>/100</small></span>
        <span class="et-score-card__label">${escHtml(spam.label || '')}</span>
      </div>`);
  }
  if (copy) {
    const sc = copy.score;
    const clr = sc >= 80 ? 'var(--color-green)' : sc >= 60 ? 'var(--color-blue)' : sc >= 40 ? 'var(--color-yellow)' : 'var(--color-red)';
    cards.push(`
      <div class="et-score-card et-score-card--reveal" style="border-top-color:${clr}; animation-delay: 150ms">
        <span class="et-score-card__title">Copy Effectiveness</span>
        <span class="et-score-card__score" style="color:${clr}" data-target="${sc}" data-counting="true">0<small>/100</small></span>
        <span class="et-score-card__label">${escHtml(copy.label || '')}</span>
      </div>`);
  }
  el.innerHTML = cards.join('');

  // Animate count-up
  requestAnimationFrame(() => {
    $$('[data-counting="true"]', el).forEach(scoreEl => {
      animateCountUp(scoreEl, parseInt(scoreEl.dataset.target, 10));
    });
  });
}

function animateCountUp(el, target, duration = 1200) {
  const start = performance.now();
  const ease = t => t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
  function tick(now) {
    const elapsed = now - start;
    const progress = Math.min(elapsed / duration, 1);
    const current = Math.round(ease(progress) * target);
    el.innerHTML = `${current}<small>/100</small>`;
    if (progress < 1) requestAnimationFrame(tick);
    else el.removeAttribute('data-counting');
  }
  requestAnimationFrame(tick);
}

// ── Readability ─────────────────────────────────────
function renderReadability(data) {
  if (!data) return;
  const el = $('#etReadabilityContent');
  const section = $('#etReadability');
  section.style.display = '';

  const sc = data.score;
  const clr = sc >= 80 ? 'var(--color-green)' : sc >= 60 ? 'var(--color-blue)' : sc >= 40 ? 'var(--color-yellow)' : 'var(--color-red)';

  el.innerHTML = `
    <div class="et-readability-overview">
      <div class="et-score-card et-score-card--reveal" style="border-top-color:${clr}">
        <span class="et-score-card__title">Readability</span>
        <span class="et-score-card__score" style="color:${clr}" data-target="${sc}" data-counting="true">0<small>/100</small></span>
        <span class="et-score-card__label">Grade ${escHtml(String(data.grade_level || '?'))}</span>
      </div>
      <div class="et-readability-summary">
        <p>${escHtml(data.summary || '')}</p>
      </div>
    </div>`;
  requestAnimationFrame(() => {
    const scoreEl = el.querySelector('[data-counting="true"]');
    if (scoreEl) animateCountUp(scoreEl, sc);
  });
}

// ── Reputation ──────────────────────────────────────
function renderReputation(data) {
  if (!data) return;
  const el = $('#etReputationContent');
  const section = $('#etReputation');
  section.style.display = '';

  const { auth, reputation, combined } = data;
  const clr = combined?.color === 'green' ? 'var(--color-green)' : combined?.color === 'blue' ? 'var(--color-blue)' : combined?.color === 'yellow' ? 'var(--color-yellow)' : combined?.color === 'orange' ? 'var(--color-orange)' : 'var(--color-red)';

  const repScore = combined?.score || 0;
  let html = `
    <div class="et-scores-row">
      <div class="et-score-card et-score-card--reveal" style="border-top-color:${clr}">
        <span class="et-score-card__title">Combined</span>
        <span class="et-score-card__score" style="color:${clr}" data-target="${repScore}" data-counting="true">0<small>/100</small></span>
        <span class="et-score-card__label">${escHtml(combined?.label || '')}</span>
      </div>
    </div>`;

  // Blocklist summary
  const dnsbl = reputation?.dnsbl || [];
  const listedBls = dnsbl.filter(r => r.listed);
  const listedCount = reputation?.listed_count || listedBls.length;
  if (listedCount === 0) {
    html += `<div class="srep-bl-clean"><span class="srep-bl-clean__icon">\u2713</span> Clean across all checked blocklists</div>`;
  } else {
    html += `
      <div class="srep-bl-alert"><span class="srep-bl-alert__icon">\u26A0</span> Listed on ${listedCount} blocklist${listedCount !== 1 ? 's' : ''}</div>
      <div class="srep-bl-listed">
        ${listedBls.map(r => `
          <div class="srep-bl-item">
            <span class="srep-bl-name">${escHtml(r.name)}</span>
            <span class="srep-bl-zone">${escHtml(r.zone)}</span>
            ${r.reason ? `<span class="srep-bl-reason">${escHtml(r.reason.slice(0, 100))}</span>` : ''}
            ${r.delist ? `<a href="${escHtml(r.delist)}" target="_blank" rel="noopener" class="srep-bl-delist">Delist &rarr;</a>` : ''}
          </div>`).join('')}
      </div>`;
  }

  el.innerHTML = html;
  requestAnimationFrame(() => {
    const scoreEl = el.querySelector('[data-counting="true"]');
    if (scoreEl) animateCountUp(scoreEl, repScore);
  });
}

// ── Audit ───────────────────────────────────────────
function renderAudit(data) {
  if (!data) return;
  const el = $('#etAuditContent');
  const section = $('#etAudit');
  section.style.display = '';

  const checks = data.checks || [];
  el.innerHTML = checks.map(c => {
    const icon = c.pass ? '\u2713' : '\u2717';
    const cls = c.pass ? 'pass' : 'fail';
    return `
      <div class="et-audit-item et-audit-item--${cls}">
        <span class="et-audit-icon et-audit-icon--${cls}">${icon}</span>
        <div class="et-audit-body">
          <span class="et-audit-label">${escHtml(c.label || c.check || '')}</span>
          ${c.detail ? `<span class="et-audit-detail">${escHtml(c.detail)}</span>` : ''}
        </div>
      </div>`;
  }).join('');
}

// ── Raw headers ─────────────────────────────────────
function renderRawHeaders(headers) {
  if (!headers?.length) return;
  $('#etHeaderCount').textContent = headers.length;
  $('#etRawHeadersList').innerHTML = `
    <div class="et-raw-headers">
      ${headers.map(h => `<code class="et-raw-header">${escHtml(h)}</code>`).join('')}
    </div>`;
}

// ══════════════════════════════════════════════════════
//  NAVIGATION
// ══════════════════════════════════════════════════════
$('#backToStep1').addEventListener('click', () => {
  currentToken = '';
  notFoundCount = 0;
  clearAutoRecheck();
  goToStep(1);
});

$('#newTestBtn').addEventListener('click', () => {
  currentToken = '';
  notFoundCount = 0;
  clearAutoRecheck();
  goToStep(1);
});

// ── Step 2 help toggle ──
$('#step2HelpToggle').addEventListener('click', () => {
  const body = $('#step2HelpBody');
  const arrow = $('.et-step2-help__arrow');
  const open = body.style.display !== 'none';
  body.style.display = open ? 'none' : '';
  if (arrow) arrow.style.transform = open ? '' : 'rotate(180deg)';
});

// ══════════════════════════════════════════════════════
//  COPY HANDLERS
// ══════════════════════════════════════════════════════
$('#copyTokenBtn').addEventListener('click', () => {
  copyText(currentToken, $('#copyTokenBtn'));
});

$('#copySeedBtn').addEventListener('click', () => {
  copyText(seedAddress, $('#copySeedBtn'));
});

function copyText(text, btn) {
  navigator.clipboard.writeText(text).then(() => {
    const orig = btn.textContent;
    btn.textContent = 'Copied!';
    setTimeout(() => { btn.textContent = orig; }, 1500);
  }).catch(() => {});
}

// Scroll-to-test CTA button
const scrollToTestBtn = $('#scrollToTestBtn');
if (scrollToTestBtn) {
  scrollToTestBtn.addEventListener('click', (e) => {
    e.preventDefault();
    const toolSection = document.querySelector('[data-section-id="email_test_tool"]');
    if (toolSection) {
      toolSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  });
}

// Hero + bottom CTA scroll buttons — scroll to the start button
document.querySelectorAll('.js-scroll-to-test').forEach(function(btn) {
  btn.addEventListener('click', function(e) {
    e.preventDefault();
    var startBtn = document.getElementById('startTestBtn');
    if (startBtn) {
      startBtn.scrollIntoView({ behavior: 'smooth', block: 'center' });
    } else {
      var toolSection = document.querySelector('[data-section-id="email_test_tool"]');
      if (toolSection) {
        toolSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    }
  });
});

// ══════════════════════════════════════════════════════
//  ACCORDION
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
//  SANITIZATION
// ══════════════════════════════════════════════════════
function escHtml(str) {
  return String(str ?? '')
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}
function escAttr(str) {
  return String(str ?? '').replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/'/g,'&#39;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ══════════════════════════════════════════════════════
//  FULL AUDIT CTA — One-click from Email Test results
// ══════════════════════════════════════════════════════
let auditDomain = '';
let auditSelector = '';

function setupFullAuditCTA(data) {
  const ctaSection = $('#etFullAuditCta');
  if (!ctaSection) return;

  // Extract domain from received email
  const domain = data.headers?.identity?.from_domain
    || (data.content?.sender_email ? data.content.sender_email.split('@').pop() : '');
  const selector = data.headers?.dkim_signature?.selector || '';

  if (!domain) {
    ctaSection.classList.add('hidden');
    return;
  }

  auditDomain = domain;
  auditSelector = selector;

  // Update CTA text
  const domainEl = $('#faCTADomain');
  if (domainEl) domainEl.textContent = domain;

  ctaSection.classList.remove('hidden');
  ctaSection.style.display = '';

  // Reset inline results
  $('#faCTAResults').classList.add('hidden');
  $('#faCTAReport').innerHTML = '';
}

// Wire up the button
const auditBtn = $('#runFullAuditBtn');
if (auditBtn) {
  auditBtn.addEventListener('click', async () => {
    if (!auditDomain) return;

    const btn = auditBtn;
    btn.disabled = true;
    const btnText = $('.btn-text', btn);
    const btnSpinner = $('.btn-spinner', btn);
    btnText.textContent = 'Running audit...';
    btnSpinner.classList.remove('hidden');

    const resultsWrap = $('#faCTAResults');
    const loading = $('#faCTALoading');
    const report = $('#faCTAReport');

    resultsWrap.classList.remove('hidden');
    loading.classList.remove('hidden');
    report.innerHTML = '';

    // Rotate loading messages
    const msgs = [
      'Running full audit...', 'Checking all authentication records...',
      'Scanning blocklists...', 'Detecting email provider...',
      'Generating fix records...',
    ];
    let msgIdx = 0;
    const msgEl = $('#faCTALoadingMsg');
    const msgInterval = setInterval(() => {
      msgIdx = (msgIdx + 1) % msgs.length;
      if (msgEl) msgEl.textContent = msgs[msgIdx];
    }, 2200);

    try {
      const res = await fetch('/api/full-audit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ domain: auditDomain, dkim_selector: auditSelector || null }),
      });
      const auditData = await res.json();

      clearInterval(msgInterval);
      loading.classList.add('hidden');

      if (!res.ok || auditData.error) {
        report.innerHTML = `<div class="sender-error"><strong>Error:</strong> ${escHtml(auditData.error || 'Audit failed.')}</div>`;
        return;
      }

      renderInlineAudit(report, auditData);
      resultsWrap.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (err) {
      clearInterval(msgInterval);
      loading.classList.add('hidden');
      report.innerHTML = '<div class="sender-error"><strong>Error:</strong> Network error. Please try again.</div>';
    } finally {
      btn.disabled = false;
      btnText.textContent = 'Run Full Audit';
      btnSpinner.classList.add('hidden');
    }
  });
}

function renderInlineAudit(container, data) {
  let html = '';

  // Severity summary
  const sev = data.severity_summary || {};
  const sevItems = [];
  if (sev.critical > 0) sevItems.push(`<span class="fa-sev fa-sev--critical">${sev.critical} Critical</span>`);
  if (sev.warning > 0) sevItems.push(`<span class="fa-sev fa-sev--warning">${sev.warning} Warning${sev.warning !== 1 ? 's' : ''}</span>`);
  if (sev.pass > 0) sevItems.push(`<span class="fa-sev fa-sev--pass">${sev.pass} Passing</span>`);
  if (sev.info > 0) sevItems.push(`<span class="fa-sev fa-sev--info">${sev.info} Info</span>`);
  html += `<div class="fa-severity-bar">${sevItems.join('')}</div>`;

  // Grade
  const gColor = data.grade === 'A' ? 'green' : data.grade === 'B' ? 'blue' : data.grade === 'C' ? 'yellow' : data.grade === 'D' ? 'orange' : 'red';
  html += `
    <div class="et-assessment-grade" style="border-left-color:var(--color-${gColor})">
      <div class="et-assessment-grade__letter" style="color:var(--color-${gColor})">${escHtml(data.grade)}</div>
      <div class="et-assessment-grade__body">
        <span class="et-assessment-grade__label">Domain Health Score: ${data.score}/100</span>
      </div>
    </div>`;

  // ESP badge
  if (data.esp?.detected) {
    html += `
      <div class="fa-esp-badge">
        <span class="fa-esp-icon">&#9993;</span>
        <span class="fa-esp-text">
          <strong>Detected ESP:</strong> ${escHtml(data.esp.esp_name)}
          <small>via ${escHtml(data.esp.mx_host)}</small>
        </span>
      </div>`;
  }

  // Fix records — the key value
  if (data.fix_records && data.fix_records.length) {
    html += `<h3 style="font-size:0.92rem;font-weight:700;color:var(--text-primary);margin:16px 0 8px">Copy-Paste Fix Records</h3>`;
    html += `<p style="font-size:0.78rem;color:var(--text-hint);margin:0 0 12px">Add these DNS records to fix the issues found above.</p>`;

    data.fix_records.forEach((fix, i) => {
      const actionColors = { create: 'red', fix: 'orange', upgrade: 'yellow' };
      const actionColor = actionColors[fix.action] || 'blue';
      const actionLabel = (fix.action || 'create').charAt(0).toUpperCase() + (fix.action || 'create').slice(1);

      html += `<div class="fa-fix-card" style="animation-delay:${i * 80}ms">`;
      html += `<div class="fa-fix-header">`;
      html += `<span class="fa-fix-action fa-fix-action--${actionColor}">${actionLabel}</span>`;
      html += `<h3 class="fa-fix-title">${escHtml(fix.title)}</h3>`;
      if (fix.esp_detected) html += `<span class="fa-fix-esp">${escHtml(fix.esp_detected)}</span>`;
      html += `</div>`;
      html += `<p class="fa-fix-desc">${escHtml(fix.description)}</p>`;

      if (fix.record && fix.host) {
        html += `<div class="fa-fix-record">`;
        html += `<div class="fa-fix-record-meta">`;
        html += `<span class="fa-fix-label">Host:</span><code class="fa-fix-host">${escHtml(fix.host)}</code>`;
        html += `<span class="fa-fix-label">Type:</span><code class="fa-fix-type">${escHtml(fix.dns_type || 'TXT')}</code>`;
        html += `</div>`;
        html += `<div class="fa-fix-record-value">`;
        html += `<pre class="fa-fix-code"><code>${escHtml(fix.record)}</code></pre>`;
        html += `<button class="fa-copy-btn" data-copy="${escAttr(fix.record)}">Copy</button>`;
        html += `</div></div>`;
      }

      if (fix.instructions && fix.instructions.length) {
        html += `<div class="fa-fix-instructions"><strong>Setup Steps:</strong>`;
        html += `<ol>${fix.instructions.map(s => `<li>${escHtml(s)}</li>`).join('')}</ol></div>`;
      }

      if (fix.policy_text) {
        html += `<div class="fa-fix-record" style="margin-top:12px">`;
        html += `<div class="fa-fix-record-meta"><span class="fa-fix-label">Policy File:</span><code class="fa-fix-host">${escHtml(fix.policy_url || '')}</code></div>`;
        html += `<div class="fa-fix-record-value"><pre class="fa-fix-code"><code>${escHtml(fix.policy_text)}</code></pre>`;
        html += `<button class="fa-copy-btn" data-copy="${escAttr(fix.policy_text)}">Copy</button></div></div>`;
      }

      if (fix.warnings && fix.warnings.length) {
        html += `<div class="fa-fix-warnings">${fix.warnings.map(w => `<p class="fa-fix-warning">\u26A0 ${escHtml(w)}</p>`).join('')}</div>`;
      }
      html += `</div>`;
    });
  } else {
    html += `<p style="font-size:0.85rem;color:var(--color-green);padding:12px 0">\u2713 No DNS fixes needed — your domain configuration looks healthy.</p>`;
  }

  // Link to full standalone page
  html += `<div style="text-align:center;padding:12px 0">`;
  html += `<a href="/sender?domain=${encodeURIComponent(auditDomain)}" class="run-again-btn" style="text-decoration:none">View Full Report &rarr;</a>`;
  html += `</div>`;

  container.innerHTML = html;

  // Wire up copy buttons
  container.querySelectorAll('.fa-copy-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const text = btn.dataset.copy;
      navigator.clipboard.writeText(text).then(() => {
        btn.textContent = 'Copied!';
        btn.classList.add('fa-copy-btn--copied');
        setTimeout(() => { btn.textContent = 'Copy'; btn.classList.remove('fa-copy-btn--copied'); }, 1500);
      }).catch(() => {
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.cssText = 'position:fixed;opacity:0';
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

// ── Next Steps CTAs ─────────────────────────────────
function renderNextSteps(data) {
  const el = $('#etNextSteps');
  if (!el) return;

  const actions = [];

  // Extract domain and IP from received headers
  const domain = data.headers?.identity?.from_domain
    || (data.content?.sender_email ? data.content.sender_email.split('@').pop() : '');
  const senderIp = data.headers?.transport?.sender_ip || '';
  const selector = data.headers?.dkim_signature?.selector || '';
  const subject = data.content?.clean_subject || data.content?.subject || '';
  const grades = data.header_grades || [];
  const spam = data.spam;
  const placement = data.placement;

  // 1. Auth failures → Sender Check
  const authFails = grades.filter(g => g.status === 'fail' || g.status === 'warning');
  if (authFails.length > 0 && domain) {
    const params = new URLSearchParams({ domain });
    if (senderIp) params.set('sender_ip', senderIp);
    if (selector) params.set('dkim_selector', selector);
    const failLabels = authFails.map(g => g.label).join(', ');
    actions.push({
      icon: '&#9888;',
      title: `Fix ${failLabels}`,
      desc: `Your ${failLabels} ${authFails.length > 1 ? 'checks need' : 'check needs'} attention. Run a full Sender Check to get copy-paste DNS records that fix ${authFails.length > 1 ? 'these issues' : 'this issue'}.`,
      href: `/sender?${params.toString()}`,
      btn: 'Open Sender Check',
      color: 'orange',
    });
  }

  // 2. Spam landed → Sender Check (if no auth action already)
  if (placement?.placement === 'spam' && !authFails.length && domain) {
    const params = new URLSearchParams({ domain });
    if (senderIp) params.set('sender_ip', senderIp);
    actions.push({
      icon: '&#128465;',
      title: 'Diagnose Spam Placement',
      desc: 'Your email landed in spam. Check your sender reputation and blocklist status to find out why.',
      href: `/sender?${params.toString()}`,
      btn: 'Check Sender Reputation',
      color: 'red',
    });
  }

  // 3. High spam score → Email Analyzer
  if (spam && spam.score >= 40) {
    actions.push({
      icon: '&#9998;',
      title: 'Improve Email Content',
      desc: `Spam risk score is ${spam.score}/100. Paste your email into the Analyzer for specific content fixes and AI-powered rewrite suggestions.`,
      href: '/analyzer',
      btn: 'Open Email Analyzer',
      color: 'yellow',
    });
  }

  // 4. Subject line testing
  if (subject) {
    actions.push({
      icon: '&#127919;',
      title: 'Test Subject Line Variations',
      desc: `Compare "${subject.length > 50 ? subject.slice(0, 47) + '...' : subject}" against alternatives. Score each on deliverability, clarity, and engagement.`,
      href: `/subject-scorer`,
      btn: 'Open Subject Scorer',
      color: 'blue',
    });
  }

  // 5. All good → suggest Placement test
  if (!authFails.length && (!spam || spam.score < 40) && placement?.placement === 'inbox') {
    actions.push({
      icon: '&#10003;',
      title: 'Everything Looks Good',
      desc: 'Your email passed all checks. Run a multi-seed Inbox Placement test to confirm delivery across Gmail, Yahoo, and Outlook.',
      href: '/placement',
      btn: 'Run Placement Test',
      color: 'green',
    });
  }

  if (!actions.length) { el.style.display = 'none'; return; }

  el.style.display = '';
  el.innerHTML = `
    <h3 class="et-section-title">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18" style="vertical-align:middle;margin-right:6px"><path d="M13 17l5-5-5-5M6 17l5-5-5-5"/></svg>
      What to Do Next
    </h3>
    <div class="et-next-steps">
      ${actions.map(a => `
        <a href="${a.href}" class="et-next-step et-next-step--${a.color}">
          <span class="et-next-step__icon">${a.icon}</span>
          <div class="et-next-step__body">
            <strong class="et-next-step__title">${escHtml(a.title)}</strong>
            <p class="et-next-step__desc">${escHtml(a.desc)}</p>
          </div>
          <span class="et-next-step__btn">${escHtml(a.btn)} &rarr;</span>
        </a>`).join('')}
    </div>`;
}

// ══════════════════════════════════════════════════════
//  MOVE TO PRIMARY — Campaign Template Generator
// ══════════════════════════════════════════════════════
function renderMoveToPrimary(data) {
  const el = $('#etMoveToPrimary');
  if (!el) return;
  const placement = data.placement || {};
  if (placement.tab !== 'promotions' && placement.tab !== 'updates') {
    el.style.display = 'none';
    return;
  }

  const tabName = placement.tab === 'promotions' ? 'Promotions' : 'Updates';
  const template = `Subject: Quick favor — takes 3 seconds

Hey [First Name],

I want to make sure you're seeing my emails!

Gmail may have sorted me into your ${tabName} tab, which means you could be missing updates you signed up for.

Here's how to fix it (takes 3 seconds):

ON DESKTOP:
1. Open this email in Gmail
2. Drag it from ${tabName} to your Primary tab
3. Click "Yes" when Gmail asks to do this for future messages

ON MOBILE:
1. Open this email in the Gmail app
2. Tap the three dots (top right)
3. Tap "Move to" → "Primary"

That's it! You'll never miss an update again.

Thanks!
[Your Name]`;

  el.style.display = '';
  el.innerHTML = `
    <div class="mtp-card">
      <div class="mtp-header">
        <div class="mtp-header__icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="22" height="22"><path d="M22 2L11 13"/><path d="M22 2L15 22l-4-9-9-4z"/></svg>
        </div>
        <div>
          <h3 class="mtp-header__title">Escape the ${escHtml(tabName)} Tab</h3>
          <p class="mtp-header__desc">Send this email to your subscribers — one real person moving you to Primary is more effective than any automation tool.</p>
        </div>
      </div>
      <div class="mtp-template">
        <div class="mtp-template__header">
          <span>Ready-to-send email template</span>
          <button class="mtp-copy-btn" id="mtpCopyBtn">Copy Template</button>
        </div>
        <pre class="mtp-template__body" id="mtpTemplateText">${escHtml(template)}</pre>
      </div>
      <div class="mtp-tips">
        <p class="mtp-tips__title">Why this works better than automation:</p>
        <ul class="mtp-tips__list">
          <li><strong>One real subscriber</strong> moving you to Primary trains Gmail permanently for that person</li>
          <li><strong>Engagement signals compound</strong> — opens and replies from Primary teach Gmail your emails belong there</li>
          <li><strong>No risk to your account</strong> — this is the method Gmail themselves recommend</li>
        </ul>
      </div>
    </div>`;

  document.getElementById('mtpCopyBtn').addEventListener('click', function() {
    navigator.clipboard.writeText(document.getElementById('mtpTemplateText').textContent).then(() => {
      this.textContent = 'Copied!';
      setTimeout(() => { this.textContent = 'Copy Template'; }, 2000);
    });
  });
}

// ══════════════════════════════════════════════════════
//  PRIMARY INBOX OPTIMIZER — AI Content Rewrite
// ══════════════════════════════════════════════════════
function renderPrimaryOptimizer(data) {
  const el = $('#etPrimaryOptimizer');
  if (!el) return;
  const placement = data.placement || {};
  const hasBody = !!(data.email_body || data.body_html);
  const hasSubject = !!(data.headers?.subject);

  if ((placement.tab !== 'promotions' && placement.tab !== 'updates') || (!hasBody && !hasSubject)) {
    el.style.display = 'none';
    return;
  }

  const tier = window.__userTier || 'free';
  const isPro = tier === 'pro' || tier === 'agency' || tier === 'api';

  el.style.display = '';
  el.innerHTML = `
    <div class="po-card">
      <div class="po-header">
        <div class="po-header__icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="22" height="22"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 013 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
        </div>
        <div>
          <h3 class="po-header__title">AI Primary Inbox Optimizer</h3>
          <p class="po-header__desc">Let AI rewrite your email to escape the Promotions tab — strips marketing language, reduces links, makes it sound like a real person wrote it.</p>
        </div>
      </div>
      <div class="po-action">
        ${isPro
          ? `<button class="po-btn" id="poOptimizeBtn">
               <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>
               Optimize for Primary Inbox
             </button>`
          : `<a href="/pricing" class="po-btn po-btn--upgrade">
               Upgrade to Pro to unlock AI optimizer
             </a>`
        }
      </div>
      <div class="po-results hidden" id="poResults"></div>
    </div>`;

  if (isPro) {
    document.getElementById('poOptimizeBtn').addEventListener('click', async function() {
      const btn = this;
      btn.disabled = true;
      btn.innerHTML = '<span class="btn-spinner"></span> Optimizing...';

      const resultsEl = document.getElementById('poResults');
      resultsEl.classList.add('hidden');

      try {
        const resp = await fetch('/ai-optimize-primary', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            subject: data.headers?.subject || '',
            body: data.email_body || data.body_html || '',
          }),
        });
        const result = await resp.json();
        if (!resp.ok) throw new Error(result.error || 'Optimization failed');

        resultsEl.classList.remove('hidden');
        resultsEl.innerHTML = `
          <div class="po-result-section">
            <div class="po-result-label">Optimized Subject</div>
            <div class="po-result-value po-result-value--subject">${escHtml(result.optimized_subject)}</div>
          </div>
          <div class="po-result-section">
            <div class="po-result-label">Optimized Body <button class="mtp-copy-btn po-copy-btn" id="poCopyBody">Copy</button></div>
            <pre class="po-result-body" id="poBodyText">${escHtml(result.optimized_body)}</pre>
          </div>
          ${result.changes_made?.length ? `
          <div class="po-result-section">
            <div class="po-result-label">What we changed</div>
            <ul class="po-changes-list">
              ${result.changes_made.map(c => `<li>${escHtml(c)}</li>`).join('')}
            </ul>
          </div>` : ''}
          ${result.before_after?.length ? `
          <div class="po-result-section">
            <div class="po-result-label">Before &rarr; After</div>
            <div class="po-diff-list">
              ${result.before_after.map(d => `
                <div class="po-diff">
                  <span class="po-diff__before">${escHtml(d.before)}</span>
                  <span class="po-diff__arrow">&rarr;</span>
                  <span class="po-diff__after">${escHtml(d.after)}</span>
                  <span class="po-diff__reason">${escHtml(d.reason)}</span>
                </div>`).join('')}
            </div>` : ''}
          </div>
          ${result.tips?.length ? `
          <div class="po-result-section">
            <div class="po-result-label">Tips for staying in Primary</div>
            <ul class="po-changes-list">
              ${result.tips.map(t => `<li>${escHtml(t)}</li>`).join('')}
            </ul>
          </div>` : ''}
        `;

        document.getElementById('poCopyBody')?.addEventListener('click', function() {
          navigator.clipboard.writeText(document.getElementById('poBodyText').textContent).then(() => {
            this.textContent = 'Copied!';
            setTimeout(() => { this.textContent = 'Copy'; }, 2000);
          });
        });

        btn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><path d="M9 11l3 3L22 4"/></svg> Done!';
      } catch (err) {
        btn.disabled = false;
        btn.innerHTML = 'Optimize for Primary Inbox';
        if (window.showToast) showToast(err.message, 'error');
      }
    });
  }
}

// ══════════════════════════════════════════════════════
//  SAFETY WARNING — Seed Engagement Risks
// ══════════════════════════════════════════════════════
function renderSafetyWarning(data) {
  const el = $('#etSafetyWarning');
  if (!el) return;

  el.style.display = '';
  el.innerHTML = `
    <div class="safety-card">
      <div class="safety-card__icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="20" height="20"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
      </div>
      <div class="safety-card__body">
        <h3 class="safety-card__title">Beware of tools that promise to "fix" your inbox placement</h3>
        <p class="safety-card__text">Some deliverability tools use networks of fake accounts to automatically open, click, and reply to your emails — tricking Gmail into thinking real people are engaged. This is called <strong>seed engagement</strong>, and here's why you should avoid it:</p>
        <ul class="safety-card__list">
          <li><strong>It violates Gmail, Outlook, and Yahoo's terms of service.</strong> These providers are actively detecting artificial engagement patterns. If caught, your domain can be permanently blacklisted.</li>
          <li><strong>It creates a costly dependency.</strong> The moment you stop paying, your placement drops — often worse than before, because your real engagement metrics were never improved.</li>
          <li><strong>It masks the actual problems.</strong> If your emails land in spam because of a missing DMARC record or spammy content, fake engagement doesn't fix that — it just hides it until it blows up.</li>
          <li><strong>The "results" aren't real.</strong> Higher open rates from bot accounts don't translate to revenue. Your actual subscribers are still not seeing your emails.</li>
        </ul>
        <div class="safety-card__cta">
          <strong>The sustainable approach:</strong> Fix the real issues. InbXr shows you exactly what email providers see — authentication verdicts, spam triggers, content scores, blocklist status — and gives you the specific steps to fix each one. Real diagnostics, real fixes, permanent results.
        </div>
      </div>
    </div>`;
}

// ══════════════════════════════════════════════════════
//  UPGRADE NUDGES (Feature 2 — Free-to-Paid Conversion)
// ══════════════════════════════════════════════════════
function renderUpgradeNudges(data) {
  const el = $('#etUpgradeNudge');
  if (!el) return;

  const tier = window.__userTier || 'free';
  if (tier !== 'free') { el.style.display = 'none'; return; }

  const nudges = [];
  const placement = data.placement || {};
  const spam = data.spam || {};

  if (placement.placement === 'spam' || spam.score >= 40) {
    nudges.push({
      icon: '&#128276;',
      title: 'Get Alerted If This Gets Worse',
      text: 'Pro monitors your domain 24/7 and sends instant alerts when your emails hit spam or you land on a blocklist.',
    });
  }

  nudges.push({
    icon: '&#128196;',
    title: 'Download This Report as PDF',
    text: 'Save and share this analysis with your team. Pro includes downloadable PDF reports for every test.',
  });

  nudges.push({
    icon: '&#128202;',
    title: 'Track Your Score Over Time',
    text: 'See how your deliverability changes day-by-day with trend charts, history, and domain health dashboards.',
  });

  el.style.display = '';
  el.innerHTML = `
    <div class="upgrade-nudge">
      <div class="upgrade-nudge__icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="20" height="20"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>
      </div>
      <div class="upgrade-nudge__body">
        <h3 class="upgrade-nudge__title">Get More From Your Results</h3>
        ${nudges.map(n => `
          <p class="upgrade-nudge__text"><strong>${n.icon} ${n.title}</strong> &mdash; ${escHtml(n.text)}</p>
        `).join('')}
        <a href="/pricing" class="upgrade-nudge__cta">Upgrade to Pro &rarr;</a>
      </div>
    </div>`;
}

// ══════════════════════════════════════════════════════
//  EMAIL PREVIEW (Feature 4 — How Email Looks Across Clients)
// ══════════════════════════════════════════════════════
function renderEmailPreview(data) {
  const el = $('#etEmailPreview');
  if (!el) return;

  const content = data.content || {};
  const htmlBody = data.html_body || content.body_html || '';
  const textBody = content.body_text || content.body_snippet || '';

  if (!htmlBody && !textBody) { el.style.display = 'none'; return; }

  const from = content.from_header || content.sender_email || 'sender@example.com';
  const subject = content.clean_subject || content.subject || 'No subject';
  const providers = [
    { name: 'Gmail', icon: 'G', bg: '#f8f9fa', font: 'Arial, sans-serif' },
    { name: 'Outlook', icon: 'O', bg: '#f3f2f1', font: 'Segoe UI, sans-serif' },
    { name: 'Apple Mail', icon: 'A', bg: '#ffffff', font: '-apple-system, sans-serif' },
  ];

  const warnings = [];
  if (data.spam && data.spam.score >= 40) {
    warnings.push('High spam score — this email may be filtered before it reaches the inbox.');
  }
  const placement = data.placement || {};
  if (placement.tab && placement.tab !== 'primary') {
    warnings.push('Gmail sorted this into the "' + placement.tab + '" tab instead of Primary.');
  }
  if (!htmlBody) {
    warnings.push('No HTML version detected — email will render as plain text.');
  }

  el.style.display = '';
  el.innerHTML = `
    <h3 class="et-section-title">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18" style="vertical-align:middle;margin-right:6px"><rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8"/><path d="M12 17v4"/></svg>
      Email Preview
    </h3>
    <div class="email-preview-section">
      <div class="email-preview-tabs" id="previewTabs">
        ${providers.map((p, i) => `
          <button class="email-preview-tab${i === 0 ? ' email-preview-tab--active' : ''}" data-provider="${i}">${escHtml(p.name)}</button>
        `).join('')}
      </div>
      <div id="previewContent"></div>
      ${warnings.length ? `
        <div class="email-preview-warnings">
          ${warnings.map(w => `
            <div class="email-preview-warning">
              <span class="email-preview-warning__icon">&#9888;</span>
              <span>${escHtml(w)}</span>
            </div>`).join('')}
        </div>` : ''}
    </div>`;

  function showProvider(idx) {
    const p = providers[idx];
    const previewEl = document.getElementById('previewContent');
    const bodyContent = htmlBody
      ? htmlBody
      : '<pre style="white-space:pre-wrap;font-family:monospace;font-size:13px;margin:0;">' + escHtml(textBody) + '</pre>';
    previewEl.innerHTML = `
      <div class="email-preview-provider-label">${escHtml(p.name)} Preview</div>
      <div class="email-preview-frame">
        <div class="email-preview-chrome" style="background:${p.bg};font-family:${p.font}">
          <div class="email-preview-dots">
            <span class="email-preview-dot email-preview-dot--red"></span>
            <span class="email-preview-dot email-preview-dot--yellow"></span>
            <span class="email-preview-dot email-preview-dot--green"></span>
          </div>
          <span class="email-preview-from" style="font-family:${p.font}">${escHtml(from)}</span>
        </div>
        <div class="email-preview-body" style="font-family:${p.font}">
          <div style="padding:0 0 8px;border-bottom:1px solid #e2e8f0;margin-bottom:12px;">
            <strong style="font-size:1rem;">${escHtml(subject)}</strong><br>
            <span style="font-size:0.8rem;color:#64748b;">From: ${escHtml(from)}</span>
          </div>
          <div class="email-preview-html">${bodyContent}</div>
        </div>
      </div>`;
    previewEl.querySelectorAll('.email-preview-html script').forEach(s => s.remove());
  }

  showProvider(0);

  document.getElementById('previewTabs').addEventListener('click', (e) => {
    const tab = e.target.closest('.email-preview-tab');
    if (!tab) return;
    $$('.email-preview-tab', el).forEach(t => t.classList.remove('email-preview-tab--active'));
    tab.classList.add('email-preview-tab--active');
    showProvider(parseInt(tab.dataset.provider));
  });
}

// ══════════════════════════════════════════════════════
//  EMAIL ME THIS REPORT
// ══════════════════════════════════════════════════════
function setupEmailReport() {
  const wrap = $('#etEmailReport');
  if (!wrap) return;
  wrap.style.display = '';

  const trigger = $('#emailReportTrigger');
  const form = $('#emailReportForm');
  const input = $('#emailReportInput');
  const sendBtn = $('#emailReportSend');
  const status = $('#emailReportStatus');

  // Pre-fill email for logged-in users
  if (window.__userEmail) {
    input.value = window.__userEmail;
  }

  // Reset state from previous reports
  form.style.display = 'none';
  trigger.style.display = '';
  status.textContent = '';
  status.className = 'et-email-report__status';
  sendBtn.disabled = false;
  $('.btn-text', sendBtn).textContent = 'Send';
  $('.btn-spinner', sendBtn).classList.add('hidden');

  trigger.onclick = function() {
    form.style.display = '';
    trigger.style.display = 'none';
    input.focus();
  };

  sendBtn.onclick = function() { sendEmailReport(); };
  input.onkeydown = function(e) {
    if (e.key === 'Enter') sendEmailReport();
  };
}

function buildReportHtml(data) {
  // Build a clean HTML summary from the report data
  const p = data.placement || {};
  const spam = data.spam || {};
  const copy = data.copy || {};
  const grades = data.header_grades || [];
  const assessment = data.assessment_items || [];

  // Overall verdict
  const inSpam = p.placement === 'spam' || p.placement === 'trash';
  const inPromo = p.placement === 'inbox' && p.tab === 'promotions';
  let verdict = 'Results Ready';
  let verdictColor = '#3b82f6';
  if (inSpam) { verdict = 'Landed in Spam'; verdictColor = '#ef4444'; }
  else if (inPromo) { verdict = 'Promotions Tab'; verdictColor = '#f59e0b'; }
  else if (p.placement === 'inbox') { verdict = 'Inbox'; verdictColor = '#22c55e'; }

  // Grade pills
  const gradeColors = { pass: '#22c55e', warning: '#f59e0b', fail: '#ef4444', missing: '#94a3b8' };
  const gradeLetters = { pass: 'A', warning: 'C', fail: 'F', missing: '?' };
  let gradeHtml = grades.map(g => {
    const c = gradeColors[g.status] || '#94a3b8';
    const l = g.grade || gradeLetters[g.status] || '?';
    return '<td style="text-align:center;padding:8px 12px;">' +
      '<span style="display:inline-block;width:32px;height:32px;line-height:32px;border-radius:50%;' +
      'background:' + c + ';color:#fff;font-weight:700;font-size:14px;">' + l + '</span>' +
      '<br><span style="font-size:12px;color:#64748b;">' + (g.label || '') + '</span></td>';
  }).join('');

  // Top 3 issues
  let issuesHtml = '';
  const issues = [];
  grades.filter(g => g.status === 'fail').forEach(g => {
    issues.push(g.label + ' is failing — ' + (g.detail || 'needs attention'));
  });
  grades.filter(g => g.status === 'warning').forEach(g => {
    issues.push(g.label + ' — ' + (g.detail || 'has warnings'));
  });
  if (spam.score > 40) {
    issues.push('Spam risk score is ' + spam.score + '/100 — review content triggers');
  }
  if (copy.score !== undefined && copy.score < 50) {
    issues.push('Copy score is ' + copy.score + '/100 — improve email content');
  }

  const topIssues = issues.slice(0, 3);
  if (topIssues.length > 0) {
    issuesHtml = '<h3 style="color:#0c1a3a;font-size:15px;margin:20px 0 8px;">Top Issues to Fix</h3><ul style="margin:0;padding-left:20px;">';
    topIssues.forEach(function(issue) {
      issuesHtml += '<li style="color:#334155;font-size:14px;line-height:1.7;">' + escHtml(issue) + '</li>';
    });
    issuesHtml += '</ul>';
  } else {
    issuesHtml = '<p style="color:#22c55e;font-size:14px;margin:16px 0;">No critical issues found — your email looks good.</p>';
  }

  // Scores
  let scoresHtml = '';
  if (spam.score !== undefined) {
    scoresHtml += '<td style="padding:8px 16px;text-align:center;">' +
      '<span style="font-size:24px;font-weight:700;color:' + (spam.score <= 20 ? '#22c55e' : spam.score <= 40 ? '#f59e0b' : '#ef4444') + ';">' + spam.score + '</span>' +
      '<span style="color:#64748b;font-size:13px;">/100</span><br><span style="font-size:12px;color:#64748b;">Spam Risk</span></td>';
  }
  if (copy.score !== undefined) {
    scoresHtml += '<td style="padding:8px 16px;text-align:center;">' +
      '<span style="font-size:24px;font-weight:700;color:' + (copy.score >= 70 ? '#22c55e' : copy.score >= 50 ? '#f59e0b' : '#ef4444') + ';">' + copy.score + '</span>' +
      '<span style="color:#64748b;font-size:13px;">/100</span><br><span style="font-size:12px;color:#64748b;">Copy Score</span></td>';
  }

  return '<div style="font-family:Inter,Arial,sans-serif;max-width:520px;margin:0 auto;padding:32px 24px;">' +
    '<h2 style="color:#0c1a3a;margin:0 0 4px;font-size:20px;">Your Email Test Report</h2>' +
    '<p style="color:#64748b;font-size:13px;margin:0 0 20px;">from InbXr &mdash; Email Intelligence Platform</p>' +
    '<div style="background:' + verdictColor + '10;border-left:4px solid ' + verdictColor + ';padding:12px 16px;border-radius:6px;margin-bottom:20px;">' +
      '<span style="font-size:16px;font-weight:700;color:' + verdictColor + ';">' + escHtml(verdict) + '</span>' +
      (p.tab ? '<span style="color:#64748b;font-size:13px;margin-left:8px;">(' + escHtml(p.tab) + ')</span>' : '') +
    '</div>' +
    (gradeHtml ? '<table style="width:100%;border-collapse:collapse;margin:16px 0;"><tr>' + gradeHtml + '</tr></table>' : '') +
    (scoresHtml ? '<table style="width:100%;border-collapse:collapse;margin:12px 0;"><tr>' + scoresHtml + '</tr></table>' : '') +
    issuesHtml +
    '<div style="text-align:center;margin:28px 0 16px;">' +
      '<a href="https://inbxr.us/" style="display:inline-block;background:#16a34a;color:#fff;padding:12px 28px;border-radius:999px;text-decoration:none;font-weight:600;font-size:15px;">Run Another Test at InbXr</a>' +
    '</div>' +
    '<p style="color:#94a3b8;font-size:12px;margin-top:24px;border-top:1px solid #e2e8f0;padding-top:16px;">InbXr &mdash; Free email deliverability tools. <a href="https://inbxr.us" style="color:#94a3b8;">inbxr.us</a></p>' +
  '</div>';
}

async function sendEmailReport() {
  const input = $('#emailReportInput');
  const sendBtn = $('#emailReportSend');
  const status = $('#emailReportStatus');
  const email = (input.value || '').trim();

  if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    status.textContent = 'Please enter a valid email address.';
    status.className = 'et-email-report__status et-email-report__status--error';
    input.focus();
    return;
  }

  if (!lastReportData) {
    status.textContent = 'No report data available. Run a test first.';
    status.className = 'et-email-report__status et-email-report__status--error';
    return;
  }

  sendBtn.disabled = true;
  $('.btn-text', sendBtn).textContent = 'Sending...';
  $('.btn-spinner', sendBtn).classList.remove('hidden');
  status.textContent = '';
  status.className = 'et-email-report__status';

  try {
    const reportHtml = buildReportHtml(lastReportData);
    const res = await fetch('/api/email-report', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: email, report_html: reportHtml }),
    });
    const data = await res.json();

    if (res.ok && !data.error) {
      status.textContent = 'Report sent! Check your inbox.';
      status.className = 'et-email-report__status et-email-report__status--success';
      sendBtn.disabled = true;
      $('.btn-text', sendBtn).textContent = 'Sent';
      $('.btn-spinner', sendBtn).classList.add('hidden');
    } else {
      status.textContent = data.error || 'Failed to send. Try again.';
      status.className = 'et-email-report__status et-email-report__status--error';
      sendBtn.disabled = false;
      $('.btn-text', sendBtn).textContent = 'Send';
      $('.btn-spinner', sendBtn).classList.add('hidden');
    }
  } catch (err) {
    status.textContent = 'Network error. Please try again.';
    status.className = 'et-email-report__status et-email-report__status--error';
    sendBtn.disabled = false;
    $('.btn-text', sendBtn).textContent = 'Send';
    $('.btn-spinner', sendBtn).classList.add('hidden');
  }
}
