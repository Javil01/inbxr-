/* ══════════════════════════════════════════════════════
   INBXR — Email Test Analyzer
   ══════════════════════════════════════════════════════ */

'use strict';

const $ = (sel, ctx = document) => ctx.querySelector(sel);
const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

let currentToken = '';
let seedAddress = '';
let autoRecheckTimer = null;
let autoRecheckSeconds = 0;
let notFoundCount = 0;

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
  ['#etPlacementSummary', '#etAssessment', '#etHeaderGrades', '#etTransport', '#etIdentity', '#etScores', '#etReadability', '#etReputation', '#etAudit', '#etRawHeaders'].forEach(s => {
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
//  RENDER: NOT FOUND
// ══════════════════════════════════════════════════════
function renderNotFound() {
  let msg, extra = '';

  if (notFoundCount <= 1) {
    msg = "Email not found in the seed mailbox yet. It may still be in transit — we'll auto-check again in 45 seconds.";
  } else if (notFoundCount === 2) {
    msg = "Still waiting — email hasn't arrived yet. Some email systems can take 1–2 minutes to deliver. We'll check once more automatically.";
  } else if (notFoundCount === 3) {
    msg = "Third check — still no email. This is taking longer than usual. We'll try one more time.";
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
    msg = "Email not found after multiple checks. This may indicate a delivery issue — the email could have been blocked or rejected before reaching the mailbox.";
    extra = `
      <div class="et-nf-recommend">
        <div class="et-nf-recommend__icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="24" height="24"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>
        </div>
        <div class="et-nf-recommend__body">
          <strong>Recommended: Run a Placement Test</strong>
          <p>If your email isn't reaching our seed account, it may be getting blocked or filtered before delivery.
          The <a href="/placement">Inbox Placement Test</a> sends to multiple seed accounts across Gmail, Outlook, Yahoo, and more —
          giving you a broader view of where your email lands and helping pinpoint whether the issue is provider-specific or systemic.</p>
          <a href="/placement" class="et-nf-recommend__btn">Run Placement Test &rarr;</a>
        </div>
      </div>
      <div class="et-nf-tips">
        <strong>Other things to check:</strong>
        <ul>
          <li><strong>Sender Check</strong> — <a href="/sender">run a sender audit</a> to verify your SPF, DKIM, DMARC, and check for blocklist listings</li>
          <li><strong>Bounce notifications</strong> — check if your ESP or mail server sent a bounce-back or delivery failure notice</li>
          <li><strong>Sending limits</strong> — some ESPs throttle new accounts or domains with low reputation</li>
          <li><strong>Firewall / security</strong> — corporate email systems may block outbound mail to unknown addresses</li>
        </ul>
      </div>`;
  }

  const borderColor = notFoundCount >= 4 ? 'var(--color-red)' : 'var(--color-yellow)';
  const icon = notFoundCount >= 4 ? '\u2717' : '?';
  const title = notFoundCount >= 4 ? 'Delivery Issue Detected' : 'Not Found';
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
function renderFullReport(data) {
  clearAutoRecheck();

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
  renderNextSteps(data);

  // Show all sections with staggered reveal
  const revealSections = ['#etAssessment', '#etHeaderGrades', '#etTransport', '#etIdentity', '#etScores', '#etReadability', '#etReputation', '#etAudit', '#etFullAuditCta', '#etNextSteps', '#etRawHeaders'];
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
        info.push({
          label: 'Inbox Placement',
          text: 'Delivered to inbox but sorted into Promotions tab.',
          fix: 'To reach Primary: reduce image-to-text ratio, avoid multiple CTAs, use conversational tone, minimize HTML complexity, and send from a person\'s name rather than a brand.',
        });
      } else if (placement.tab && placement.tab === 'updates') {
        info.push({
          label: 'Inbox Placement',
          text: 'Delivered to inbox but sorted into Updates tab.',
          fix: 'Updates tab is typical for transactional/notification emails. To reach Primary: make the content more personal and conversational.',
        });
      } else {
        good.push({ label: 'Inbox Placement', text: `Delivered to ${placement.tab || 'inbox'} — no issues detected.` });
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
  const listed = reputation?.listed_count || 0;
  if (listed === 0) {
    html += `<div class="srep-bl-clean"><span class="srep-bl-clean__icon">\u2713</span> Clean across all checked blocklists</div>`;
  } else {
    html += `<div class="srep-bl-alert"><span class="srep-bl-alert__icon">\u26A0</span> Listed on ${listed} blocklist${listed !== 1 ? 's' : ''}</div>`;
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

// Hero + bottom CTA scroll buttons (class-based)
document.querySelectorAll('.js-scroll-to-test').forEach(function(btn) {
  btn.addEventListener('click', function(e) {
    e.preventDefault();
    var toolSection = document.querySelector('[data-section-id="email_test_tool"]');
    if (toolSection) {
      toolSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
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
