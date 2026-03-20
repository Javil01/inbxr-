/* ══════════════════════════════════════════════════════
   INBXR — Frontend Application
   ══════════════════════════════════════════════════════ */

'use strict';

const $ = (sel, ctx = document) => ctx.querySelector(sel);
const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

// ══════════════════════════════════════════════════════
//  FORM TABS  (Compose / Settings)
// ══════════════════════════════════════════════════════
$$('.tab').forEach(btn => {
  btn.addEventListener('click', () => {
    $$('.tab').forEach(t => t.classList.remove('active'));
    $$('.tab-content').forEach(tc => tc.classList.remove('active'));
    btn.classList.add('active');
    $(`#tab-${btn.dataset.tab}`).classList.add('active');
  });
});

// ══════════════════════════════════════════════════════
//  SUBJECT LINE COUNTER
// ══════════════════════════════════════════════════════
const subjectInput = $('#subject');
const subjectCounter = $('#subject-counter');
subjectInput.addEventListener('input', () => {
  const len = subjectInput.value.length;
  subjectCounter.textContent = `${len} chars`;
  subjectCounter.style.color =
    len >= 30 && len <= 55 ? 'var(--color-green)'  :
    len > 55  && len <= 70 ? 'var(--color-yellow)' :
    len > 70               ? 'var(--color-red)'    :
                             'var(--text-hint)';
});

// ══════════════════════════════════════════════════════
//  BODY INPUT MODE SWITCHER
// ══════════════════════════════════════════════════════
let activeMode = 'paste-email';   // 'paste-email' | 'paste-html' | 'upload'
let parsedFileBody = '';           // HTML body extracted from uploaded file

$$('.input-mode-tab').forEach(btn => {
  btn.addEventListener('click', () => {
    $$('.input-mode-tab').forEach(t => {
      t.classList.remove('active');
      t.setAttribute('aria-selected', 'false');
    });
    $$('.body-mode-panel').forEach(p => p.classList.remove('active'));

    btn.classList.add('active');
    btn.setAttribute('aria-selected', 'true');
    activeMode = btn.dataset.mode;
    $(`#mode-${activeMode}`).classList.add('active');
  });
});

// ══════════════════════════════════════════════════════
//  MODE: PASTE EMAIL  (rich contenteditable)
// ══════════════════════════════════════════════════════
const bodyEditor    = $('#bodyEditor');
const bodyCounter   = $('#body-counter');
const linkBadge     = $('#linkBadge');
const linkBadgeText = $('#linkBadgeText');
const pasteSuccess  = $('#pasteSuccess');
let pasteSuccessTimer = null;

function updateBodyStatus() {
  const text = bodyEditor.textContent || '';
  const wc = text.trim().split(/\s+/).filter(Boolean).length;
  bodyCounter.textContent = `${wc} word${wc !== 1 ? 's' : ''}`;

  const links = bodyEditor.querySelectorAll('a[href]');
  if (links.length > 0) {
    linkBadgeText.textContent = `${links.length} link${links.length !== 1 ? 's' : ''} detected`;
    linkBadge.classList.remove('hidden');
  } else {
    linkBadge.classList.add('hidden');
  }
}

bodyEditor.addEventListener('input', updateBodyStatus);

$('#bodyClearBtn').addEventListener('click', () => {
  bodyEditor.innerHTML = '';
  updateBodyStatus();
  bodyEditor.focus();
});

// ─── HTML sanitizer ───────────────────────────────────
function sanitizePastedHTML(rawHTML) {
  const parser = new DOMParser();
  const doc = parser.parseFromString(rawHTML, 'text/html');

  const stripTags = ['script','style','meta','link','head','title',
                     'form','input','button','select','textarea',
                     'iframe','object','embed','applet','base'];
  stripTags.forEach(tag => doc.querySelectorAll(tag).forEach(el => el.remove()));

  doc.querySelectorAll('img').forEach(img => {
    const alt = (img.getAttribute('alt') || '').trim();
    img.replaceWith(document.createTextNode(alt ? `[${alt}]` : ''));
  });

  doc.querySelectorAll('*').forEach(el => {
    const tag = el.tagName.toLowerCase();
    const allowed = tag === 'a' ? ['href', 'title'] : [];
    Array.from(el.attributes).forEach(attr => {
      if (!allowed.includes(attr.name.toLowerCase())) el.removeAttribute(attr.name);
    });
    if (tag === 'a') {
      const href = el.getAttribute('href') || '';
      if (!/^(https?:|mailto:)/i.test(href)) el.removeAttribute('href');
    }
  });

  return doc.body.innerHTML;
}

// ─── Paste handler ────────────────────────────────────
bodyEditor.addEventListener('paste', e => {
  e.preventDefault();
  const html  = e.clipboardData.getData('text/html');
  const plain = e.clipboardData.getData('text/plain');

  if (html && html.trim()) {
    document.execCommand('insertHTML', false, sanitizePastedHTML(html));
    clearTimeout(pasteSuccessTimer);
    pasteSuccess.classList.remove('hidden');
    pasteSuccessTimer = setTimeout(() => pasteSuccess.classList.add('hidden'), 3000);
  } else {
    document.execCommand('insertText', false, plain);
  }
  updateBodyStatus();
});

// ══════════════════════════════════════════════════════
//  MODE: PASTE HTML  (raw source textarea)
// ══════════════════════════════════════════════════════
const htmlSource  = $('#htmlSource');
const htmlCounter = $('#html-counter');

htmlSource.addEventListener('input', () => {
  const len = htmlSource.value.length;
  htmlCounter.textContent = `${len.toLocaleString()} chars`;
});

$('#htmlClearBtn').addEventListener('click', () => {
  htmlSource.value = '';
  htmlCounter.textContent = '0 chars';
  htmlSource.focus();
});

// ══════════════════════════════════════════════════════
//  MODE: UPLOAD FILE  (.eml / .msg / .mbox / .html)
// ══════════════════════════════════════════════════════
const fileInput      = $('#fileInput');
const uploadZone     = $('#uploadZone');
const uploadPreview  = $('#uploadPreview');
const uploadParsed   = $('#uploadParsed');
const uploadError    = $('#uploadError');
const uploadLoading  = $('#uploadLoading');

// Icon map by extension
const EXT_ICONS = { eml: '📨', msg: '📧', mbox: '📬', html: '🌐', htm: '🌐' };

function getExt(filename) {
  return (filename.split('.').pop() || '').toLowerCase();
}

// Open file browser on button or zone click
$('#uploadBrowseBtn').addEventListener('click', e => {
  e.stopPropagation();
  fileInput.click();
});
uploadZone.addEventListener('click', () => fileInput.click());

// Drag-and-drop
uploadZone.addEventListener('dragover', e => {
  e.preventDefault();
  uploadZone.classList.add('drag-over');
});
['dragleave','dragend'].forEach(evt =>
  uploadZone.addEventListener(evt, () => uploadZone.classList.remove('drag-over'))
);
uploadZone.addEventListener('drop', e => {
  e.preventDefault();
  uploadZone.classList.remove('drag-over');
  const file = e.dataTransfer.files[0];
  if (file) handleFile(file);
});

fileInput.addEventListener('change', () => {
  if (fileInput.files[0]) handleFile(fileInput.files[0]);
});

$('#uploadRemoveBtn').addEventListener('click', resetUpload);

function resetUpload() {
  parsedFileBody = '';
  fileInput.value = '';
  uploadPreview.classList.add('hidden');
  uploadZone.classList.remove('hidden');
  uploadError.classList.add('hidden');
  uploadParsed.classList.add('hidden');
}

function formatBytes(bytes) {
  if (bytes < 1024)       return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

async function handleFile(file) {
  const ext = getExt(file.name);
  const allowed = ['html','htm','eml','msg','mbox'];
  if (!allowed.includes(ext)) {
    showUploadError(`Unsupported file type ".${ext}". Accepted: .html, .eml, .msg, .mbox`);
    return;
  }

  // Show loading
  uploadZone.classList.add('hidden');
  uploadPreview.classList.add('hidden');
  uploadError.classList.add('hidden');
  uploadLoading.classList.remove('hidden');

  const formData = new FormData();
  formData.append('file', file);

  try {
    const res = await fetch('/parse-file', { method: 'POST', body: formData });
    const data = await res.json();

    uploadLoading.classList.add('hidden');

    if (!res.ok || data.error) {
      showUploadError(data.error || 'Could not parse this file.');
      uploadZone.classList.remove('hidden');
      return;
    }

    // Populate parsed fields
    parsedFileBody = data.body || '';

    // Show preview card
    $('#uploadFileIcon').textContent = EXT_ICONS[ext] || '📄';
    $('#uploadFileName').textContent = file.name;
    $('#uploadFileMeta').textContent = formatBytes(file.size);

    // Show parsed info
    const rows = [];
    if (data.subject)   rows.push(`<strong>Subject:</strong> ${escHtml(data.subject)}`);
    if (data.from_addr) rows.push(`<strong>From:</strong> ${escHtml(data.from_addr)}`);
    if (data.message_count > 1) rows.push(`<strong>Messages in file:</strong> ${data.message_count} (first message loaded)`);

    if (rows.length) {
      $('#uploadParsedSubject').innerHTML = rows[0] || '';
      $('#uploadParsedFrom').innerHTML    = rows[1] || '';
      $('#uploadParsedMsgCount').innerHTML = rows[2] || '';
      uploadParsed.classList.remove('hidden');
    }

    uploadPreview.classList.remove('hidden');
    uploadError.classList.add('hidden');

    // Auto-fill subject if empty
    if (data.subject && !subjectInput.value.trim()) {
      subjectInput.value = data.subject;
      subjectInput.dispatchEvent(new Event('input'));
    }
    // Auto-fill sender if empty
    if (data.from_addr && !$('#sender_email').value.trim()) {
      const emailMatch = data.from_addr.match(/[\w.+-]+@[\w.-]+\.\w+/);
      if (emailMatch) $('#sender_email').value = emailMatch[0];
    }

  } catch (err) {
    uploadLoading.classList.add('hidden');
    uploadZone.classList.remove('hidden');
    showUploadError('Network error while parsing file. Please try again.');
  }
}

function showUploadError(msg) {
  uploadError.textContent = msg;
  uploadError.classList.remove('hidden');
}

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
//  COPY TO CLIPBOARD
// ══════════════════════════════════════════════════════
document.addEventListener('click', e => {
  const btn = e.target.closest('.copy-btn, .dns-copy-btn, .subject-suggestion, .cta-example');
  if (!btn) return;
  const text = btn.dataset.copy || btn.textContent.trim();
  navigator.clipboard.writeText(text).then(() => {
    const orig = btn.textContent;
    btn.textContent = 'Copied!';
    setTimeout(() => { btn.textContent = orig; }, 1500);
  }).catch(() => {});
});

// ══════════════════════════════════════════════════════
//  FORM SUBMISSION
// ══════════════════════════════════════════════════════
$('#analyzeForm').addEventListener('submit', async e => {
  e.preventDefault();

  const submitBtn = $('#submitBtn');
  const btnText   = $('.btn-text', submitBtn);
  const spinner   = $('.btn-spinner', submitBtn);

  submitBtn.disabled = true;
  btnText.textContent = 'Analyzing…';
  spinner.classList.remove('hidden');

  // ── Validate sender email ──
  const senderEmail = $('#sender_email').value.trim();
  if (!senderEmail || !senderEmail.includes('@')) {
    $('#sender_email').focus();
    $('#sender_email').style.borderColor = 'var(--color-red)';
    showError('Please enter a valid sender email address.');
    submitBtn.disabled = false;
    btnText.textContent = 'Analyze Email';
    spinner.classList.add('hidden');
    return;
  }
  $('#sender_email').style.borderColor = '';

  // ── Resolve body by active mode ──
  let body = '';
  if (activeMode === 'paste-email') {
    body = bodyEditor.innerHTML.trim();
  } else if (activeMode === 'paste-html') {
    body = htmlSource.value.trim();
  } else if (activeMode === 'upload') {
    body = parsedFileBody.trim();
    if (!body) {
      showError('No file loaded. Please upload an email file first.');
      submitBtn.disabled = false;
      btnText.textContent = 'Analyze Email';
      spinner.classList.add('hidden');
      return;
    }
  }

  // Auto-pull hrefs from body editor as CTA URLs
  const editorLinks = [...bodyEditor.querySelectorAll('a[href]')]
    .map(a => a.getAttribute('href')).filter(Boolean);
  const manualUrls = $('#cta_urls').value.split(',').map(s => s.trim()).filter(Boolean);
  const allUrls = manualUrls.length ? manualUrls : editorLinks;

  const payload = {
    sender_email:     $('#sender_email').value.trim(),
    industry:         $('#industry').value,
    subject:          subjectInput.value.trim(),
    preheader:        $('#preheader').value.trim(),
    body,
    cta_texts:        $('#cta_texts').value.split(',').map(s => s.trim()).filter(Boolean),
    cta_urls:         allUrls,
    is_transactional: $('#is_transactional').checked,
    is_cold_email:    $('#is_cold_email').checked,
    is_plain_text:    $('#is_plain_text').checked,
  };

  showAnalysisProgress();

  try {
    const res  = await fetch('/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();

    hideAnalysisProgress();

    if (!res.ok || data.error) {
      showError(data.error || 'Analysis failed. Please try again.');
      return;
    }

    renderResults(data, payload);
  } catch (err) {
    hideAnalysisProgress();
    showError('Network error. Check your connection and try again.');
  } finally {
    submitBtn.disabled = false;
    btnText.textContent = 'Analyze Email';
    spinner.classList.add('hidden');
  }
});

// ══════════════════════════════════════════════════════
//  RENDER RESULTS
// ══════════════════════════════════════════════════════
// ══════════════════════════════════════════════════════
//  VERDICT SUMMARY — Top-level analysis verdict
// ══════════════════════════════════════════════════════
function renderAnalyzerVerdict(data) {
  const el = $('#analyzerVerdict');
  if (!el) return;

  const spam = data.spam;
  const copy = data.copy;
  const reputation = data.reputation;
  const audit = data.audit;

  // Determine overall verdict
  const spamScore = spam ? spam.score : 0;
  const copyScore = copy ? copy.score : 50;
  const auditFails = audit?.checks ? audit.checks.filter(c => !c.pass).length : 0;

  let verdict, verdictColor, verdictIcon, verdictDesc;

  if (spamScore >= 60 || auditFails >= 3) {
    verdict = 'Needs Work';
    verdictColor = 'var(--color-red)';
    verdictIcon = '\u2717';
    verdictDesc = 'Significant issues found that could hurt delivery. Review the critical items below.';
  } else if (spamScore >= 30 || copyScore < 50 || auditFails >= 1) {
    verdict = 'Room to Improve';
    verdictColor = 'var(--color-yellow)';
    verdictIcon = '\u26A0';
    verdictDesc = 'Your email is decent but has areas that could be stronger before sending.';
  } else if (copyScore >= 70 && spamScore <= 15) {
    verdict = 'Ready to Send';
    verdictColor = 'var(--color-green)';
    verdictIcon = '\u2713';
    verdictDesc = 'Low spam risk and strong copy. This email looks ready for your audience.';
  } else {
    verdict = 'Analysis Complete';
    verdictColor = 'var(--color-blue)';
    verdictIcon = '\u2139';
    verdictDesc = 'Review your scores and recommendations below.';
  }

  // Top recommendation
  let topRec = '';
  if (spam && spam.score >= 30 && spam.top_recommendations?.length) {
    const rec = spam.top_recommendations[0];
    const recText = rec.recommendation || rec.item || rec;
    topRec = `<div class="hero-action hero-action--${spamScore >= 60 ? 'critical' : 'warning'}"><span class="hero-action__icon">\u26A0</span><span>${_escHtml(String(recText))}</span></div>`;
  } else if (copy && copy.score < 50 && copy.weaknesses?.length) {
    topRec = `<div class="hero-action hero-action--warning"><span class="hero-action__icon">\u26A0</span><span>Weak point: <strong>${_escHtml(copy.weaknesses[0])}</strong></span></div>`;
  }

  // Score pills
  const pills = [];
  if (spam) {
    const sColor = spam.score <= 20 ? 'var(--color-green)' : spam.score <= 40 ? 'var(--color-yellow)' : 'var(--color-red)';
    pills.push(`<div class="hero-pill"><span class="hero-pill__label">Spam Risk</span><span class="hero-pill__value" style="color:${sColor}">${spam.score}/100</span></div>`);
  }
  if (copy) {
    const cColor = copy.score >= 70 ? 'var(--color-green)' : copy.score >= 50 ? 'var(--color-yellow)' : 'var(--color-red)';
    pills.push(`<div class="hero-pill"><span class="hero-pill__label">Copy Score</span><span class="hero-pill__value" style="color:${cColor}">${copy.score}/100</span></div>`);
  }
  if (data.readability?.score != null) {
    const r = data.readability;
    const rColor = r.score >= 70 ? 'var(--color-green)' : r.score >= 50 ? 'var(--color-yellow)' : 'var(--color-red)';
    pills.push(`<div class="hero-pill"><span class="hero-pill__label">Readability</span><span class="hero-pill__value" style="color:${rColor}">${r.score}/100</span></div>`);
  }

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
            <span class="hero-summary__title">${_escHtml(verdict)}</span>
            <span class="hero-summary__desc">${_escHtml(verdictDesc)}</span>
          </div>
        </div>
        <div class="hero-summary__pills">${pills.join('')}</div>
      </div>
      ${topRec}
    </div>`;
  el.style.display = '';
}

function _escHtml(str) {
  if (!str) return '';
  return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function renderResults(data, payload) {
  const { spam, copy, meta, reputation } = data;

  // Store for export
  _lastAnalysisData = data;
  _lastPayload = payload;

  // Auto-save to history (localStorage)
  _saveToHistory(data, payload);

  $('#emptyState').classList.add('hidden');
  const rc = $('#resultsContent');
  rc.classList.remove('hidden');

  if (window.innerWidth < 960) rc.scrollIntoView({ behavior: 'smooth', block: 'start' });

  // ── Verdict summary (top-level) ──
  renderAnalyzerVerdict(data);

  // ── Pre-Send Audit Banner (top of results) ──
  if (data.audit) {
    renderAuditBanner(data.audit);
    renderAuditChecklist(data.audit);
  } else {
    $('#auditBanner').style.display = 'none';
    $('#auditModule').style.display = 'none';
  }

  renderMetaBar(meta);
  renderGauge('spam', spam.score, spam.label, spam.color, spam.summary);
  renderGauge('copy', copy.score, copy.label, copy.color, copy.summary);

  // ── Industry Benchmarks ──
  if (data.benchmarks) {
    renderBenchmarks(data.benchmarks);
  } else {
    $('#benchmarkModule').style.display = 'none';
    $('#spamBench').innerHTML = '';
    $('#copyBench').innerHTML = '';
  }

  // ── Inbox Client Previews ──
  renderInboxPreviews(payload.subject, payload.preheader || '', payload.sender_email || '');

  renderCategoryBars('spamCategories', spam.categories, 'spam');
  renderFlagList('spamFlagList', spam.high_risk_elements);
  updateBadgeCount('spamHighRiskCount', (spam.high_risk_elements || []).length);
  renderRecList('spamRecList', spam.top_recommendations);

  renderCategoryBars('copyCategories', copy.categories, 'copy');
  renderStrengthsWeaknesses(copy.strengths, copy.weaknesses);
  renderFlagList('copyFlagList', copy.all_flags, true);
  updateBadgeCount('copyFlagCount', (copy.all_flags || []).length);
  renderRewrites(copy.rewrites, payload.subject);

  // ── Readability ──
  const readModule = $('#readabilityModule');
  if (data.readability && data.readability.score !== null) {
    readModule.style.display = '';
    renderReadability(data.readability);
  } else {
    readModule.style.display = 'none';
  }

  // ── AI Rewrite Engine ──
  const aiModule = $('#aiRewriteModule');
  initAiRewrite(data, payload);

  // ── Link & Image Validation ──
  const liModule = $('#linkImageModule');
  if (data.link_image && (data.link_image.links.total > 0 || data.link_image.images.total > 0)) {
    liModule.style.display = '';
    renderLinkImage(data.link_image);
  } else {
    liModule.style.display = 'none';
  }

  // ── BIMI Validation ──
  const bimiModule = $('#bimiModule');
  if (data.bimi) {
    bimiModule.style.display = '';
    renderBimi(data.bimi);
  } else {
    bimiModule.style.display = 'none';
  }

  // ── Sender Reputation ──
  const repModule = $('#senderRepModule');
  if (reputation) {
    repModule.style.display = '';
    renderSenderReputation(reputation);
  } else {
    repModule.style.display = 'none';
  }

  // ── DNS Suggestions ──
  const dnsEl = $('#dnsSuggestions');
  if (data.dns_suggestions && data.dns_suggestions.has_suggestions) {
    dnsEl.style.display = '';
    renderDnsSuggestions(data.dns_suggestions);
  } else {
    dnsEl.style.display = 'none';
  }

  // ── Email Rendering Preview ──
  renderEmailPreview(payload.body, payload.subject);

  rc.classList.add('fade-in');

  renderNextSteps(data, payload);

  // Init results nav (after modules are shown/hidden)
  setTimeout(() => initResultsNav(), 50);
}

// ══════════════════════════════════════════════════════
//  NEXT STEPS — Contextual CTAs linking to other tools
// ══════════════════════════════════════════════════════
function renderNextSteps(data, payload) {
  const el = $('#analyzerNextSteps');
  if (!el) return;

  const actions = [];
  const spam = data.spam;
  const reputation = data.reputation;
  const domain = reputation?.meta?.domain || '';

  // 1. High spam score → specific content guidance
  if (spam && spam.score >= 50) {
    const topFlags = (spam.high_risk_elements || []).slice(0, 3).map(f => f.item || f).join(', ');
    actions.push({
      icon: '\u26A0',
      title: 'High Spam Risk: ' + spam.score + '/100',
      desc: topFlags ? 'Top triggers: ' + topFlags + '. Use the AI Rewriter above for instant fixes.' : 'Multiple spam signals detected. Use the AI Rewriter above to fix flagged content.',
      href: null,
      btn: null,
      color: 'red',
    });
  }

  // 2. Auth/reputation issues → Sender Check
  if (reputation?.combined?.score < 70 && domain) {
    actions.push({
      icon: '\uD83D\uDD12',
      title: 'Sender Reputation Needs Work',
      desc: 'Your domain scored ' + reputation.combined.score + '/100 on reputation. Run a full Sender Check for copy-paste DNS fixes.',
      href: '/sender?domain=' + encodeURIComponent(domain),
      btn: 'Open Sender Check',
      color: 'orange',
    });
  }

  // 3. Always suggest real-world test
  actions.push({
    icon: '\u2709',
    title: 'Test with a Real Email',
    desc: 'Analyzing copy is step one. Send your email through the Email Test to see actual SPF, DKIM, and DMARC verdicts from a real mail server.',
    href: '/',
    btn: 'Run Email Test',
    color: 'blue',
  });

  // 4. Subject line refinement
  if (payload?.subject) {
    actions.push({
      icon: '\uD83C\uDFAF',
      title: 'Optimize Your Subject Line',
      desc: 'Compare "' + (payload.subject.length > 40 ? payload.subject.slice(0, 37) + '...' : payload.subject) + '" against alternatives across 7 scoring dimensions.',
      href: '/subject-scorer',
      btn: 'Open Subject Scorer',
      color: 'blue',
    });
  }

  if (!actions.length) { el.style.display = 'none'; return; }

  el.style.display = '';
  el.innerHTML = `
    <div class="module-header">
      <h2 class="module-title"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="20" height="20" style="vertical-align:middle;margin-right:6px"><path d="M13 17l5-5-5-5M6 17l5-5-5-5"/></svg> What to Do Next</h2>
    </div>
    <div class="et-next-steps">
      ${actions.map(a => {
        if (!a.href) {
          return `<div class="et-next-step et-next-step--${a.color}">
            <span class="et-next-step__icon">${a.icon}</span>
            <div class="et-next-step__body">
              <strong class="et-next-step__title">${escHtml(a.title)}</strong>
              <p class="et-next-step__desc">${escHtml(a.desc)}</p>
            </div></div>`;
        }
        return `<a href="${a.href}" class="et-next-step et-next-step--${a.color}">
          <span class="et-next-step__icon">${a.icon}</span>
          <div class="et-next-step__body">
            <strong class="et-next-step__title">${escHtml(a.title)}</strong>
            <p class="et-next-step__desc">${escHtml(a.desc)}</p>
          </div>
          <span class="et-next-step__btn">${escHtml(a.btn)} &rarr;</span></a>`;
      }).join('')}
    </div>`;
}

function renderMetaBar(meta) {
  const chips = [
    { label: 'Subject',  value: `${meta.subject_length} chars` },
    { label: 'Body',     value: `${meta.body_word_count} words` },
    { label: 'Type',     value: meta.email_type },
    { label: 'Industry', value: meta.industry },
  ];
  $('#metaBar').innerHTML = chips.map(c =>
    `<span class="meta-chip"><strong>${c.value}</strong> ${c.label}</span>`
  ).join('');
}

function renderGauge(type, score, label, color, summary) {
  const colorMap = {
    green: 'var(--color-green)', blue: 'var(--color-blue)',
    yellow: 'var(--color-yellow)', orange: 'var(--color-orange)', red: 'var(--color-red)',
  };
  const gaugeColor = colorMap[color] || 'var(--color-blue)';
  const ARC = 173;

  const fill    = $(`#${type}GaugeFill`);
  const numEl   = $(`#${type}GaugeNum`);
  const badge   = $(`#${type}Badge`);
  const summaryEl = $(`#${type}Summary`);

  fill.style.stroke = gaugeColor;
  badge.className   = `score-card__badge badge--${color}`;
  badge.textContent = label;
  summaryEl.textContent = summary;

  // Animate number
  let current = 0;
  const target = score;
  const step = () => {
    current = Math.min(current + Math.ceil(target / 30), target);
    numEl.textContent = current;
    if (current < target) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);

  setTimeout(() => {
    fill.style.strokeDasharray = `${(score / 100) * ARC} ${ARC}`;
  }, 100);
}

// ══════════════════════════════════════════════════════
//  INDUSTRY BENCHMARKS
// ══════════════════════════════════════════════════════
function renderBenchmarks(bench) {
  const industry = bench.industry || 'Other';

  // ── Score card inline indicators ──
  if (bench.spam) {
    const s = bench.spam;
    const arrow = s.vs_avg > 0 ? '▼' : s.vs_avg < 0 ? '▲' : '—';
    const cls = s.vs_avg > 0 ? 'bench-good' : s.vs_avg < 0 ? 'bench-bad' : 'bench-neutral';
    $('#spamBench').innerHTML = `<div class="bench-inline ${cls}">
      <span class="bench-inline__arrow">${arrow}</span>
      <span class="bench-inline__text">${s.detail}</span>
      <span class="bench-inline__pct">${s.label}</span>
    </div>`;
  }

  if (bench.copy) {
    const c = bench.copy;
    const arrow = c.vs_avg > 0 ? '▲' : c.vs_avg < 0 ? '▼' : '—';
    const cls = c.vs_avg > 0 ? 'bench-good' : c.vs_avg < 0 ? 'bench-bad' : 'bench-neutral';
    $('#copyBench').innerHTML = `<div class="bench-inline ${cls}">
      <span class="bench-inline__arrow">${arrow}</span>
      <span class="bench-inline__text">${c.detail}</span>
      <span class="bench-inline__pct">${c.label}</span>
    </div>`;
  }

  // ── Full benchmark module ──
  const mod = $('#benchmarkModule');
  mod.style.display = '';
  const grid = $('#benchGrid');

  const metrics = [];

  if (bench.spam) {
    metrics.push({
      title: 'Spam Risk',
      yours: bench.spam.your_score,
      avg: bench.spam.industry_avg,
      pct: bench.spam.percentile,
      label: bench.spam.label,
      detail: bench.spam.detail,
      inverted: true,
    });
  }
  if (bench.copy) {
    metrics.push({
      title: 'Copy Effectiveness',
      yours: bench.copy.your_score,
      avg: bench.copy.industry_avg,
      pct: bench.copy.percentile,
      label: bench.copy.label,
      detail: bench.copy.detail,
      inverted: false,
    });
  }
  if (bench.readability) {
    metrics.push({
      title: 'Readability',
      yours: bench.readability.your_score,
      avg: bench.readability.industry_avg,
      pct: bench.readability.percentile,
      label: bench.readability.label,
      detail: bench.readability.detail,
      inverted: false,
    });
  }
  if (bench.subject_length) {
    const sl = bench.subject_length;
    metrics.push({
      title: 'Subject Length',
      yours: sl.your_value,
      avg: sl.industry_avg,
      range: sl.optimal_range,
      inRange: sl.in_range,
      isInfo: true,
    });
  }
  if (bench.body_word_count) {
    const bw = bench.body_word_count;
    metrics.push({
      title: 'Body Word Count',
      yours: bw.your_value,
      avg: bw.industry_avg,
      range: bw.optimal_range,
      inRange: bw.in_range,
      isInfo: true,
    });
  }

  grid.innerHTML = `
    <div class="bench-header">
      <span class="bench-header__industry">vs ${industry} Industry</span>
    </div>
    <div class="bench-cards">
      ${metrics.map(m => {
        if (m.isInfo) {
          const statusCls = m.inRange ? 'bench-card--good' : 'bench-card--warn';
          return `<div class="bench-card ${statusCls}">
            <div class="bench-card__title">${m.title}</div>
            <div class="bench-card__values">
              <span class="bench-card__yours">${m.yours}</span>
              <span class="bench-card__vs">avg ${m.avg}</span>
            </div>
            <div class="bench-card__range">${m.inRange ? '✓ In' : '✗ Outside'} optimal range (${m.range})</div>
          </div>`;
        }

        const pctColor = m.pct >= 75 ? 'var(--color-green)' : m.pct >= 50 ? 'var(--color-blue)' : m.pct >= 25 ? 'var(--color-yellow)' : 'var(--color-red)';
        const diff = m.inverted ? m.avg - m.yours : m.yours - m.avg;
        const diffSign = diff > 0 ? '+' : '';
        return `<div class="bench-card">
          <div class="bench-card__title">${m.title}</div>
          <div class="bench-card__values">
            <span class="bench-card__yours">${m.yours}</span>
            <span class="bench-card__vs">avg ${m.avg}</span>
          </div>
          <div class="bench-card__bar-wrap">
            <div class="bench-card__bar" style="width:${Math.min(m.pct, 100)}%;background:${pctColor}"></div>
          </div>
          <div class="bench-card__footer">
            <span class="bench-card__pct" style="color:${pctColor}">${m.label}</span>
            <span class="bench-card__diff">${diffSign}${diff} vs avg</span>
          </div>
        </div>`;
      }).join('')}
    </div>`;
}

// ══════════════════════════════════════════════════════
//  INBOX CLIENT PREVIEWS
// ══════════════════════════════════════════════════════
function renderInboxPreviews(subject, preheader, senderEmail) {
  const mod = $('#inboxPreviewModule');
  if (!subject) { mod.style.display = 'none'; return; }
  mod.style.display = '';

  const senderName = senderEmail ? senderEmail.split('@')[0].replace(/[._-]/g, ' ').replace(/\b\w/g, c => c.toUpperCase()) : 'Sender';
  const senderAddr = senderEmail || 'sender@example.com';
  const subj = subject;
  const pre = preheader || '';
  const now = new Date();
  const timeStr = now.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  const dateStr = now.toLocaleDateString([], { month: 'short', day: 'numeric' });

  // Truncation helpers
  const trunc = (s, max) => s.length > max ? s.slice(0, max) + '…' : s;

  const clients = {
    gmail: _renderGmailPreview(senderName, senderAddr, subj, pre, timeStr, trunc),
    outlook: _renderOutlookPreview(senderName, senderAddr, subj, pre, timeStr, dateStr, trunc),
    apple: _renderApplePreview(senderName, subj, pre, dateStr, trunc),
    mobile: _renderMobilePreview(senderName, subj, pre, timeStr, trunc),
  };

  let activeClient = 'gmail';
  const area = $('#ipPreviewArea');
  area.innerHTML = clients[activeClient];

  // Tab switching
  $$('.ip-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      $$('.ip-tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      activeClient = tab.dataset.client;
      area.innerHTML = clients[activeClient];
    });
  });
}

function _renderGmailPreview(name, addr, subj, pre, time, trunc) {
  const preText = pre ? ` — ${trunc(pre, 90)}` : '';
  return `
    <div class="ip-client ip-gmail">
      <div class="ip-gmail__toolbar">
        <span class="ip-gmail__tab ip-gmail__tab--active">Primary</span>
        <span class="ip-gmail__tab">Promotions</span>
        <span class="ip-gmail__tab">Social</span>
      </div>
      <div class="ip-gmail__row ip-gmail__row--unread">
        <span class="ip-gmail__check">☐</span>
        <span class="ip-gmail__star">☆</span>
        <span class="ip-gmail__sender">${escHtml(name)}</span>
        <span class="ip-gmail__content">
          <strong class="ip-gmail__subject">${escHtml(trunc(subj, 70))}</strong><span class="ip-gmail__preheader">${escHtml(preText)}</span>
        </span>
        <span class="ip-gmail__time">${time}</span>
      </div>
      <div class="ip-gmail__row ip-gmail__row--read">
        <span class="ip-gmail__check">☐</span>
        <span class="ip-gmail__star">☆</span>
        <span class="ip-gmail__sender">Other Sender</span>
        <span class="ip-gmail__content">
          <span class="ip-gmail__subject">Weekly newsletter update</span><span class="ip-gmail__preheader"> — Here are this week's top stories and updates from our team</span>
        </span>
        <span class="ip-gmail__time">9:41 AM</span>
      </div>
    </div>`;
}

function _renderOutlookPreview(name, addr, subj, pre, time, date, trunc) {
  const preText = pre ? trunc(pre, 100) : 'No preview available.';
  return `
    <div class="ip-client ip-outlook">
      <div class="ip-outlook__toolbar">
        <span class="ip-outlook__tab ip-outlook__tab--active">Focused</span>
        <span class="ip-outlook__tab">Other</span>
      </div>
      <div class="ip-outlook__row ip-outlook__row--unread">
        <div class="ip-outlook__avatar">${escHtml(name.charAt(0))}</div>
        <div class="ip-outlook__body">
          <div class="ip-outlook__top">
            <span class="ip-outlook__sender">${escHtml(name)}</span>
            <span class="ip-outlook__time">${time}</span>
          </div>
          <div class="ip-outlook__subject">${escHtml(trunc(subj, 80))}</div>
          <div class="ip-outlook__preheader">${escHtml(preText)}</div>
        </div>
      </div>
      <div class="ip-outlook__row ip-outlook__row--read">
        <div class="ip-outlook__avatar">O</div>
        <div class="ip-outlook__body">
          <div class="ip-outlook__top">
            <span class="ip-outlook__sender">Other Sender</span>
            <span class="ip-outlook__time">Yesterday</span>
          </div>
          <div class="ip-outlook__subject">Re: Project update</div>
          <div class="ip-outlook__preheader">Sounds good, let's sync on this tomorrow morning.</div>
        </div>
      </div>
    </div>`;
}

function _renderApplePreview(name, subj, pre, date, trunc) {
  const preText = pre ? trunc(pre, 100) : '';
  return `
    <div class="ip-client ip-apple">
      <div class="ip-apple__toolbar">
        <span class="ip-apple__count">2 Unread</span>
        <span class="ip-apple__filter">Filter</span>
      </div>
      <div class="ip-apple__row ip-apple__row--unread">
        <div class="ip-apple__blue-dot"></div>
        <div class="ip-apple__body">
          <div class="ip-apple__top">
            <span class="ip-apple__sender">${escHtml(name)}</span>
            <span class="ip-apple__date">${date}</span>
          </div>
          <div class="ip-apple__subject">${escHtml(trunc(subj, 70))}</div>
          ${preText ? `<div class="ip-apple__preheader">${escHtml(preText)}</div>` : ''}
        </div>
      </div>
      <div class="ip-apple__row ip-apple__row--read">
        <div class="ip-apple__body">
          <div class="ip-apple__top">
            <span class="ip-apple__sender">Other Sender</span>
            <span class="ip-apple__date">Yesterday</span>
          </div>
          <div class="ip-apple__subject">Weekly digest</div>
          <div class="ip-apple__preheader">Your weekly summary is ready to view</div>
        </div>
      </div>
    </div>`;
}

function _renderMobilePreview(name, subj, pre, time, trunc) {
  const preText = pre ? trunc(pre, 60) : '';
  return `
    <div class="ip-client ip-mobile">
      <div class="ip-mobile__status-bar">
        <span>${time}</span>
        <span class="ip-mobile__notch"></span>
        <span class="ip-mobile__icons">
          <svg viewBox="0 0 24 24" fill="currentColor" width="12" height="12"><path d="M1 9l2 2c4.97-4.97 13.03-4.97 18 0l2-2C16.93 2.93 7.08 2.93 1 9zm8 8l3 3 3-3a4.237 4.237 0 00-6 0zm-4-4l2 2a7.074 7.074 0 0110 0l2-2C15.14 9.14 8.87 9.14 5 13z"/></svg>
          <svg viewBox="0 0 24 24" fill="currentColor" width="12" height="12"><path d="M15.67 4H14V2h-4v2H8.33C7.6 4 7 4.6 7 5.33v15.33C7 21.4 7.6 22 8.33 22h7.33c.74 0 1.34-.6 1.34-1.33V5.33C17 4.6 16.4 4 15.67 4z"/></svg>
        </span>
      </div>
      <div class="ip-mobile__header">Inbox</div>
      <div class="ip-mobile__row ip-mobile__row--unread">
        <div class="ip-mobile__top">
          <span class="ip-mobile__sender">${escHtml(trunc(name, 20))}</span>
          <span class="ip-mobile__time">${time}</span>
        </div>
        <div class="ip-mobile__subject">${escHtml(trunc(subj, 45))}</div>
        ${preText ? `<div class="ip-mobile__preheader">${escHtml(preText)}</div>` : ''}
      </div>
      <div class="ip-mobile__row ip-mobile__row--read">
        <div class="ip-mobile__top">
          <span class="ip-mobile__sender">Other Sender</span>
          <span class="ip-mobile__time">9:41 AM</span>
        </div>
        <div class="ip-mobile__subject">Weekly newsletter update</div>
        <div class="ip-mobile__preheader">Here are this week's top stories</div>
      </div>
    </div>`;
}

function renderCategoryBars(containerId, categories, type) {
  const container = $(`#${containerId}`);
  if (!categories?.length) { container.innerHTML = ''; return; }

  container.innerHTML = categories.map(cat => {
    const pct = cat.max > 0 ? (cat.score / cat.max) * 100 : 0;
    const barColor = type === 'spam'
      ? (pct <= 20 ? 'var(--color-green)' : pct <= 50 ? 'var(--color-yellow)' : pct <= 75 ? 'var(--color-orange)' : 'var(--color-red)')
      : (pct >= 75 ? 'var(--color-green)' : pct >= 50 ? 'var(--color-blue)'   : pct >= 25 ? 'var(--color-yellow)' : 'var(--color-red)');
    return `
      <div class="category-item">
        <span class="category-item__label" title="${cat.label}">${cat.label}</span>
        <div class="progress-track">
          <div class="progress-fill" data-width="${pct}" style="background:${barColor};width:0%"></div>
        </div>
        <span class="category-item__score">${cat.score}/${cat.max}</span>
      </div>`;
  }).join('');

  requestAnimationFrame(() => {
    $$('.progress-fill', container).forEach(bar => {
      setTimeout(() => { bar.style.width = `${bar.dataset.width}%`; }, 150);
    });
  });
}

// ══════════════════════════════════════════════════════
//  ONE-CLICK FIXES
// ══════════════════════════════════════════════════════
function _detectFix(flag) {
  const item = (flag.item || '').toLowerCase();
  const cat = (flag.category || '').toLowerCase();

  // Subject: ALL CAPS
  if (item.includes('all caps') && cat.includes('subject'))
    return { type: 'subject_caps', icon: 'Aa', label: 'Convert subject to sentence case' };

  // Subject: high capitalization
  if (item.includes('capitalization ratio') && cat.includes('subject'))
    return { type: 'subject_caps', icon: 'Aa', label: 'Reduce capitalization in subject' };

  // Subject: excessive punctuation
  if ((item.includes('excessive punctuation') || item.includes('exclamation/question')) && cat.includes('subject'))
    return { type: 'subject_punct', icon: '!→.', label: 'Reduce punctuation in subject' };

  // Subject: emojis
  if (item.includes('emoji') && cat.includes('subject'))
    return { type: 'subject_emoji', icon: '😀→', label: 'Remove extra emojis from subject' };

  // Subject: spam trigger words
  if (item.includes('spam trigger word') && cat.includes('subject'))
    return { type: 'subject_triggers', icon: '✎', label: 'Remove spam trigger words from subject' };

  // Subject: too long
  if (item.includes('too long') && cat.includes('subject'))
    return { type: 'subject_shorten', icon: '✂', label: 'Trim subject line' };

  // Body: ALL CAPS words
  if (item.includes('all-caps words') && cat.includes('body'))
    return { type: 'body_caps', icon: 'Aa', label: 'Convert caps words to normal case in body' };

  // Body: spam trigger phrases
  if (item.includes('spam trigger phrase') && cat.includes('body'))
    return { type: 'body_highlight', icon: '🔍', label: 'Highlight spam phrases in editor' };

  // CTA: risky phrases
  if (item.includes('risky cta'))
    return { type: 'body_highlight_cta', icon: '🔍', label: 'Highlight risky CTAs in editor' };

  // Deceptive patterns (Re:/Fwd:)
  if (item.includes('deceptive phrasing'))
    return { type: 'subject_deceptive', icon: '✎', label: 'Remove deceptive prefixes from subject' };

  return null;
}

function _applyFix(containerId, idx) {
  const container = $(`#${containerId}`);
  const flags = container._flags;
  if (!flags || !flags[idx]) return;

  const flag = flags[idx];
  const fix = _detectFix(flag);
  if (!fix) return;

  const subjectEl = $('#subject');
  const bodyEl = $('#bodyEditor');
  let applied = false;

  switch (fix.type) {
    case 'subject_caps': {
      const s = subjectEl.value;
      if (s) {
        subjectEl.value = _toSentenceCase(s);
        subjectEl.dispatchEvent(new Event('input'));
        applied = true;
      }
      break;
    }

    case 'subject_punct': {
      let s = subjectEl.value;
      if (s) {
        // Reduce repeated ! and ? to single
        s = s.replace(/!{2,}/g, '!').replace(/\?{2,}/g, '?').replace(/[!?]{3,}/g, '!');
        subjectEl.value = s;
        subjectEl.dispatchEvent(new Event('input'));
        applied = true;
      }
      break;
    }

    case 'subject_emoji': {
      let s = subjectEl.value;
      if (s) {
        // Keep first emoji, remove the rest
        const emojiRx = /[\u{1F300}-\u{1F9FF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}\u{FE00}-\u{FE0F}\u{1FA00}-\u{1FA6F}\u{1FA70}-\u{1FAFF}\u{200D}\u{20E3}\u{E0020}-\u{E007F}]/gu;
        let count = 0;
        s = s.replace(emojiRx, (match) => {
          count++;
          return count <= 1 ? match : '';
        });
        subjectEl.value = s.replace(/  +/g, ' ').trim();
        subjectEl.dispatchEvent(new Event('input'));
        applied = true;
      }
      break;
    }

    case 'subject_triggers': {
      // Extract trigger words from the flag item
      const match = flag.item.match(/:\s*(.+)$/);
      if (match) {
        let s = subjectEl.value;
        const triggers = match[1].split(',').map(t => t.trim().toLowerCase());
        triggers.forEach(trigger => {
          const rx = new RegExp('\\b' + _escRegex(trigger) + '\\b', 'gi');
          s = s.replace(rx, '').replace(/  +/g, ' ').trim();
        });
        subjectEl.value = s;
        subjectEl.dispatchEvent(new Event('input'));
        applied = true;
      }
      break;
    }

    case 'subject_shorten': {
      let s = subjectEl.value;
      if (s.length > 55) {
        // Cut at word boundary near 55 chars
        const cut = s.lastIndexOf(' ', 55);
        subjectEl.value = s.slice(0, cut > 20 ? cut : 55).trim();
        subjectEl.dispatchEvent(new Event('input'));
        applied = true;
      }
      break;
    }

    case 'subject_deceptive': {
      let s = subjectEl.value;
      s = s.replace(/^(Re:\s*|Fwd?:\s*|FW:\s*)+/gi, '').trim();
      subjectEl.value = s;
      subjectEl.dispatchEvent(new Event('input'));
      applied = true;
      break;
    }

    case 'body_caps': {
      // Convert ALL CAPS words (>3 chars) to title case in the body editor
      const html = bodyEl.innerHTML;
      const updated = html.replace(/\b([A-Z]{4,})\b/g, (m) => {
        return m.charAt(0) + m.slice(1).toLowerCase();
      });
      if (updated !== html) {
        bodyEl.innerHTML = updated;
        updateBodyStatus();
        applied = true;
      }
      break;
    }

    case 'body_highlight':
    case 'body_highlight_cta': {
      // Scroll to body editor and flash it
      bodyEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
      bodyEl.classList.add('fix-highlight');
      setTimeout(() => bodyEl.classList.remove('fix-highlight'), 2000);
      applied = true;
      break;
    }
  }

  if (applied) {
    // Mark flag as fixed
    const flagEl = $(`#${containerId}_flag_${idx}`);
    if (flagEl) {
      flagEl.classList.add('flag-item--fixed');
      const btn = $('.fix-btn', flagEl);
      if (btn) {
        btn.textContent = '✓ Fixed';
        btn.disabled = true;
      }
    }
  }
}

function _toSentenceCase(str) {
  return str.charAt(0).toUpperCase() + str.slice(1).toLowerCase()
    .replace(/([\.\!\?]\s*)(\w)/g, (m, sep, ch) => sep + ch.toUpperCase());
}

function _escRegex(str) {
  return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

// Delegate fix button clicks
document.addEventListener('click', (e) => {
  const btn = e.target.closest('.fix-btn');
  if (!btn) return;
  const idx = parseInt(btn.dataset.fixIdx, 10);
  const containerId = btn.dataset.fixContainer;
  if (!isNaN(idx) && containerId) _applyFix(containerId, idx);
});

function renderFlagList(containerId, flags) {
  const container = $(`#${containerId}`);
  if (!flags?.length) {
    container.innerHTML = '<p style="font-size:0.8rem;color:var(--text-secondary);padding:8px 0">No issues in this category.</p>';
    return;
  }
  container.innerHTML = flags.map((flag, i) => {
    const sev = flag.severity || flag.impact || 'low';
    const fix = _detectFix(flag);
    const fixBtn = fix
      ? `<button class="fix-btn" data-fix-idx="${i}" data-fix-container="${containerId}" title="${escAttr(fix.label)}">${fix.icon} Fix</button>`
      : '';
    return `
      <div class="flag-item flag-item--${sev}" id="${containerId}_flag_${i}">
        <div class="flag-item__meta">
          <span class="severity-dot severity-dot--${sev}"></span>
          <span class="flag-item__cat">${escHtml(flag.category || '')}</span>
          ${fixBtn}
        </div>
        <div class="flag-item__text">${escHtml(flag.item || '')}</div>
        ${flag.recommendation ? `<div class="flag-item__rec">${escHtml(flag.recommendation)}</div>` : ''}
      </div>`;
  }).join('');

  // Store flags for fix handlers
  container._flags = flags;
}

function renderRecList(containerId, recs) {
  const container = $(`#${containerId}`);
  if (!recs?.length) {
    container.innerHTML = '<p style="font-size:0.8rem;color:var(--color-green);padding:8px 0">✓ No major spam issues found.</p>';
    return;
  }
  container.innerHTML = recs.map((rec, i) => {
    const fix = _detectFix(rec);
    const fixBtn = fix
      ? `<button class="fix-btn" data-fix-idx="${i}" data-fix-container="${containerId}" title="${escAttr(fix.label)}">${fix.icon} Fix</button>`
      : '';
    return `
    <div class="rec-item" id="${containerId}_flag_${i}">
      <div class="rec-item__header">
        <span class="rec-item__cat">${escHtml(rec.category || '')}</span>
        ${fixBtn}
        <button class="copy-btn" data-copy="${escAttr(rec.recommendation)}">Copy</button>
      </div>
      <div class="rec-item__issue">${escHtml(rec.item || '')}</div>
      <div class="rec-item__text">${escHtml(rec.recommendation || '')}</div>
    </div>`;
  }).join('');

  container._flags = recs;
}

function renderStrengthsWeaknesses(strengths, weaknesses) {
  $('#copyStrengths').innerHTML = strengths?.length
    ? strengths.map(s => `<li>${escHtml(s)}</li>`).join('')
    : '<li class="sw-empty">Complete your email for strength analysis.</li>';
  $('#copyWeaknesses').innerHTML = weaknesses?.length
    ? weaknesses.map(w => `<li>${escHtml(w)}</li>`).join('')
    : '<li class="sw-empty">No major weaknesses found.</li>';
}

function renderRewrites(rewrites, originalSubject) {
  const container = $('#rewriteContent');
  if (!rewrites || !Object.keys(rewrites).length) {
    container.innerHTML = '<p class="no-rewrites">No rewrites needed — copy is strong.</p>';
    return;
  }
  let html = '';
  if (rewrites.subject_alternatives?.length) {
    html += `
      <div class="rewrite-block">
        <h4>Subject Line Alternatives</h4>
        ${originalSubject ? `<div class="rewrite-original">${escHtml(originalSubject)}</div>` : ''}
        <p class="rewrite-tip">Click any suggestion to copy it:</p>
        <div class="subject-suggestions">
          ${rewrites.subject_alternatives.map(s =>
            `<div class="subject-suggestion" data-copy="${escAttr(s)}">
              <span>${escHtml(s)}</span><span class="copy-icon">📋</span>
            </div>`).join('')}
        </div>
      </div>`;
  }
  if (rewrites.opening_suggestion) {
    const op = rewrites.opening_suggestion;
    html += `
      <div class="rewrite-block">
        <h4>Opening Hook Improvement</h4>
        <div class="rewrite-original">${escHtml(op.original)}</div>
        <p class="rewrite-tip">${escHtml(op.tip)}</p>
      </div>`;
  }
  if (rewrites.cta_examples?.length) {
    html += `
      <div class="rewrite-block">
        <h4>Stronger CTA Examples</h4>
        <p class="rewrite-tip">Click to copy:</p>
        <div class="cta-examples">
          ${rewrites.cta_examples.map(c =>
            `<button class="cta-example" data-copy="${escAttr(c)}">${escHtml(c)}</button>`).join('')}
        </div>
      </div>`;
  }
  container.innerHTML = html || '<p class="no-rewrites">Copy is performing well. Refine based on the feedback above.</p>';
}

function updateBadgeCount(id, count) {
  const el = $(`#${id}`);
  if (!el) return;
  el.textContent = count;
  el.classList.toggle('has-items', count > 0);
}

// ══════════════════════════════════════════════════════
//  SENDER REPUTATION (inline in email analyzer)
// ══════════════════════════════════════════════════════
const REP_COLOR = {
  green: 'var(--color-green)', blue: 'var(--color-blue)',
  yellow: 'var(--color-yellow)', orange: 'var(--color-orange)', red: 'var(--color-red)',
};
const REP_STATUS_ICON  = { pass: '\u2713', warning: '\u26A0', fail: '\u2717', missing: '\u2717', info: '\u2139' };
const REP_STATUS_LABEL = { pass: 'Configured', warning: 'Needs Work', fail: 'Failed', missing: 'Not Found', info: 'Info' };

function renderSenderReputation(data) {
  const { auth, reputation, combined, recommendations, meta } = data;

  // ── Overview: combined score + mini gauges ──
  const overviewColor = REP_COLOR[combined.color] || 'var(--color-blue)';
  $('#senderRepOverview').innerHTML = `
    <div class="srep-overview">
      <div class="srep-combined" style="border-color:${overviewColor}">
        <span class="srep-combined__score" style="color:${overviewColor}">${combined.score}</span>
        <span class="srep-combined__label badge--${combined.color}">${escHtml(combined.label)}</span>
        <span class="srep-combined__domain">${escHtml(meta.domain)}</span>
      </div>
      <div class="srep-gauges">
        <div class="srep-gauge-card">
          <span class="srep-gauge-title">Authentication</span>
          <span class="srep-gauge-score" style="color:${REP_COLOR[auth.color] || 'var(--color-blue)'}">${auth.score}<small>/100</small></span>
          <span class="srep-gauge-label badge--${auth.color}">${escHtml(auth.label)}</span>
        </div>
        <div class="srep-gauge-card">
          <span class="srep-gauge-title">Reputation</span>
          <span class="srep-gauge-score" style="color:${REP_COLOR[reputation.color] || 'var(--color-blue)'}">${reputation.score}<small>/100</small></span>
          <span class="srep-gauge-label badge--${reputation.color}">${escHtml(reputation.label)}</span>
        </div>
      </div>
    </div>`;

  // ── Auth summary cards ──
  const cats = auth.categories || [];
  $('#senderRepAuth').innerHTML = cats.length ? `
    <div class="srep-auth-grid">
      ${cats.map(cat => {
        const st = cat.status || 'missing';
        const icon = REP_STATUS_ICON[st] || '?';
        const lbl = REP_STATUS_LABEL[st] || st;
        const issues = (cat.issues || []).filter(Boolean);
        return `
          <div class="srep-auth-card srep-auth-card--${st}">
            <div class="srep-auth-card__head">
              <span class="srep-auth-icon srep-auth-icon--${st}">${icon}</span>
              <span class="srep-auth-name">${escHtml(cat.label)}</span>
              <span class="srep-auth-score">${cat.score}/${cat.max}</span>
            </div>
            <span class="srep-auth-status">${lbl}</span>
            ${issues.length ? `<ul class="srep-auth-issues">${issues.map(i => `<li>${escHtml(i)}</li>`).join('')}</ul>` : ''}
          </div>`;
      }).join('')}
    </div>` : '';

  // ── Blocklists summary ──
  const dnsbl = reputation.dnsbl || [];
  const listed = dnsbl.filter(r => r.listed);
  const listedCount = reputation.listed_count || listed.length;

  let blHtml = '';
  if (listedCount === 0) {
    blHtml = `<div class="srep-bl-clean"><span class="srep-bl-clean__icon">\u2713</span> Clean across all ${dnsbl.length} checked blocklists</div>`;
  } else {
    blHtml = `
      <div class="srep-bl-alert"><span class="srep-bl-alert__icon">\u26A0</span> Listed on ${listedCount} blocklist${listedCount !== 1 ? 's' : ''}</div>
      <div class="srep-bl-listed">
        ${listed.map(r => `
          <div class="srep-bl-item">
            <span class="srep-bl-name">${escHtml(r.name)}</span>
            <span class="srep-bl-zone">${escHtml(r.zone)}</span>
            ${r.reason ? `<span class="srep-bl-reason">${escHtml(r.reason.slice(0, 100))}</span>` : ''}
            ${r.delist ? `<a href="${escHtml(r.delist)}" target="_blank" rel="noopener" class="srep-bl-delist">Delist &rarr;</a>` : ''}
          </div>`).join('')}
      </div>`;
  }
  $('#senderRepBlocklists').innerHTML = blHtml;

  // ── Recommendations ──
  const recList = $('#senderRepRecList');
  if (!recommendations?.length) {
    recList.innerHTML = '<p style="font-size:0.85rem;color:var(--color-green);padding:8px 0">\u2713 Sender configuration looks healthy.</p>';
  } else {
    recList.innerHTML = recommendations.map(rec => `
      <div class="rec-item">
        <div class="rec-item__header">
          <span class="rec-item__cat">${escHtml(rec.category)}</span>
        </div>
        <div class="rec-item__issue">${escHtml(rec.item)}</div>
        <div class="rec-item__text">${escHtml(rec.recommendation)}</div>
      </div>`).join('');
  }
}

// ══════════════════════════════════════════════════════
//  READABILITY ANALYSIS
// ══════════════════════════════════════════════════════
const READ_COLOR = {
  green: 'var(--color-green)', blue: 'var(--color-blue)',
  yellow: 'var(--color-yellow)', orange: 'var(--color-orange)', red: 'var(--color-red)',
};

function renderReadability(data) {
  const { score, grade_level, fog_index, label, color, summary, stats, issues, recommendations } = data;
  const clr = READ_COLOR[color] || 'var(--color-blue)';

  // ── Overview: score circle + grade level + summary ──
  $('#readabilityOverview').innerHTML = `
    <div class="read-overview">
      <div class="read-score-ring" style="border-color:${clr}">
        <span class="read-score-num" style="color:${clr}">${score}</span>
        <span class="read-score-of">/100</span>
      </div>
      <div class="read-overview-info">
        <span class="read-label badge--${color}">${escHtml(label)}</span>
        <span class="read-grade">Grade Level <strong>${grade_level}</strong></span>
        ${fog_index != null ? `<span class="read-fog">Fog Index <strong>${fog_index}</strong></span>` : ''}
        <p class="read-summary">${escHtml(summary)}</p>
      </div>
    </div>`;

  // ── Stats grid ──
  const s = stats;
  const statItems = [
    { label: 'Words',            value: s.word_count },
    { label: 'Sentences',        value: s.sentence_count },
    { label: 'Avg Sentence',     value: `${s.avg_sentence_length} words` },
    { label: 'Longest Sentence', value: `${s.max_sentence_length} words` },
    { label: 'Avg Syllables',    value: `${s.avg_syllables_per_word}/word` },
    { label: 'Complex Words',    value: `${s.complex_word_pct}%` },
    { label: 'Passive Voice',    value: `${s.passive_voice_pct}%` },
    { label: 'Paragraphs',       value: s.paragraph_count },
  ];
  $('#readabilityStats').innerHTML = `
    <div class="read-stats-grid">
      ${statItems.map(si => `
        <div class="read-stat-card">
          <span class="read-stat-value">${si.value}</span>
          <span class="read-stat-label">${si.label}</span>
        </div>`).join('')}
    </div>`;

  // ── Issues ──
  const issueContainer = $('#readabilityIssues');
  if (issues?.length) {
    issueContainer.innerHTML = `
      <div class="read-issues">
        ${issues.map(iss => {
          const sev = iss.severity || 'medium';
          return `
            <div class="flag-item flag-item--${sev}">
              <div class="flag-item__meta">
                <span class="severity-dot severity-dot--${sev}"></span>
                <span class="flag-item__cat">${escHtml(iss.category || '')}</span>
              </div>
              <div class="flag-item__text">${escHtml(iss.item || '')}</div>
            </div>`;
        }).join('')}
      </div>`;
  } else {
    issueContainer.innerHTML = '<p style="font-size:0.85rem;color:var(--color-green);padding:8px 0">\u2713 No readability issues detected.</p>';
  }

  // ── Recommendations ──
  const recList = $('#readabilityRecList');
  if (recommendations?.length) {
    recList.innerHTML = recommendations.map(rec => `
      <div class="rec-item">
        <div class="rec-item__text">${escHtml(rec)}</div>
      </div>`).join('');
  } else {
    recList.innerHTML = '<p style="font-size:0.85rem;color:var(--color-green);padding:8px 0">\u2713 Readability is excellent — no changes needed.</p>';
  }
}

// ══════════════════════════════════════════════════════
//  AI REWRITE ENGINE
// ══════════════════════════════════════════════════════
let _aiPayloadCache = null;
let _aiDataCache = null;

function initAiRewrite(data, payload) {
  const module = $('#aiRewriteModule');
  _aiPayloadCache = payload;
  _aiDataCache = data;

  // Check if AI is available
  fetch('/ai-rewrite/status').then(r => r.json()).then(status => {
    if (status.available) {
      module.style.display = '';
      $('#aiRewriteContent').style.display = 'none';
      $('#aiRewriteError').classList.add('hidden');
    } else {
      module.style.display = 'none';
    }
  }).catch(() => { module.style.display = 'none'; });
}

$('#aiRewriteBtn').addEventListener('click', async () => {
  if (!_aiPayloadCache) return;

  const btn = $('#aiRewriteBtn');
  const btnText = $('.btn-text', btn);
  const spinner = $('.btn-spinner', btn);
  const errEl = $('#aiRewriteError');

  btn.disabled = true;
  btnText.textContent = 'Generating rewrite...';
  spinner.classList.remove('hidden');
  errEl.classList.add('hidden');

  // Collect issues from the analysis
  const issues = [];
  if (_aiDataCache?.spam?.high_risk_elements) {
    _aiDataCache.spam.high_risk_elements.slice(0, 3).forEach(f => issues.push(f.item || ''));
  }
  if (_aiDataCache?.copy?.weaknesses) {
    _aiDataCache.copy.weaknesses.slice(0, 3).forEach(w => issues.push(w));
  }
  if (_aiDataCache?.readability?.issues) {
    _aiDataCache.readability.issues.slice(0, 2).forEach(i => issues.push(i.item || ''));
  }

  const tone = $('#aiToneSelect').value;

  try {
    const res = await fetch('/ai-rewrite', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        subject: _aiPayloadCache.subject,
        body: _aiPayloadCache.body,
        industry: _aiPayloadCache.industry,
        tone,
        cta_texts: _aiPayloadCache.cta_texts,
        issues: issues.filter(Boolean),
      }),
    });
    const data = await res.json();

    if (!res.ok || data.error) {
      errEl.textContent = data.error || 'Rewrite failed.';
      errEl.classList.remove('hidden');
      return;
    }

    renderAiRewrite(data);
    $('#aiRewriteContent').style.display = '';
  } catch (err) {
    errEl.textContent = 'Network error. Please try again.';
    errEl.classList.remove('hidden');
  } finally {
    btn.disabled = false;
    btnText.textContent = 'Generate AI Rewrite';
    spinner.classList.add('hidden');
  }
});

// ── Primary Inbox Optimizer (Analyzer page) ──
$('#aiPrimaryBtn').addEventListener('click', async () => {
  if (!_aiPayloadCache) return;

  const btn = $('#aiPrimaryBtn');
  const btnText = $('.btn-text', btn);
  const spinner = $('.btn-spinner', btn);
  const errEl = $('#aiPrimaryError');
  const contentEl = $('#aiPrimaryContent');

  btn.disabled = true;
  btnText.textContent = 'Optimizing...';
  spinner.classList.remove('hidden');
  errEl.classList.add('hidden');
  contentEl.style.display = 'none';

  try {
    const res = await fetch('/ai-optimize-primary', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        subject: _aiPayloadCache.subject,
        body: _aiPayloadCache.body,
      }),
    });
    const data = await res.json();

    if (!res.ok || data.error) {
      errEl.textContent = data.error || 'Optimization failed.';
      errEl.classList.remove('hidden');
      return;
    }

    contentEl.style.display = '';
    contentEl.innerHTML = `
      <div class="ai-block">
        <h4 class="ai-block__title">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><path d="M22 2L11 13"/><path d="M22 2L15 22l-4-9-9-4z"/></svg>
          Primary Inbox Optimized Version
        </h4>
        <p style="font-size:0.78rem;color:var(--text-3);margin:0 0 12px">Rewritten to escape Gmail's Promotions tab — stripped marketing language, reduced links, conversational tone.</p>
      </div>
      <div class="ai-block">
        <h4 class="ai-block__title">Optimized Subject</h4>
        <div class="ai-suggestion" data-copy="${escAttr(data.optimized_subject)}">
          <span>${escHtml(data.optimized_subject)}</span>
          <span class="ai-copy-icon">Copy</span>
        </div>
      </div>
      <div class="ai-block">
        <h4 class="ai-block__title">Optimized Body</h4>
        <div class="ai-body-rewrite">
          <pre style="white-space:pre-wrap;word-wrap:break-word;font-family:Inter,sans-serif;font-size:0.82rem;line-height:1.7;margin:0">${escHtml(data.optimized_body)}</pre>
          <button class="ai-copy-body-btn" data-copy="${escAttr(data.optimized_body)}">Copy Body</button>
        </div>
      </div>
      ${data.changes_made?.length ? `
      <div class="ai-block">
        <h4 class="ai-block__title">What We Changed</h4>
        <ul class="ai-tips-list">
          ${data.changes_made.map(c => `<li>${escHtml(c)}</li>`).join('')}
        </ul>
      </div>` : ''}
      ${data.before_after?.length ? `
      <div class="ai-block">
        <h4 class="ai-block__title">Before &rarr; After</h4>
        ${data.before_after.map(d => `
          <div class="po-diff" style="margin-bottom:6px">
            <span class="po-diff__before">${escHtml(d.before)}</span>
            <span class="po-diff__arrow">&rarr;</span>
            <span class="po-diff__after">${escHtml(d.after)}</span>
          </div>`).join('')}
      </div>` : ''}
      ${data.tips?.length ? `
      <div class="ai-block">
        <h4 class="ai-block__title">Tips for Staying in Primary</h4>
        <ul class="ai-tips-list">
          ${data.tips.map(t => `<li>${escHtml(t)}</li>`).join('')}
        </ul>
      </div>` : ''}
    `;

    // Wire copy buttons
    contentEl.querySelectorAll('[data-copy]').forEach(el => {
      el.addEventListener('click', () => {
        const text = el.dataset.copy;
        navigator.clipboard.writeText(text).then(() => {
          const icon = el.querySelector('.ai-copy-icon') || el;
          const orig = icon.textContent;
          icon.textContent = 'Copied!';
          setTimeout(() => { icon.textContent = orig; }, 1500);
        });
      });
    });
  } catch (err) {
    errEl.textContent = 'Network error. Please try again.';
    errEl.classList.remove('hidden');
  } finally {
    btn.disabled = false;
    btnText.textContent = 'Optimize for Primary Inbox';
    spinner.classList.add('hidden');
  }
});

function renderAiRewrite(data) {
  // ── Subject alternatives ──
  const subEl = $('#aiSubjectAlts');
  if (data.subject_alternatives?.length) {
    subEl.innerHTML = `
      <div class="ai-block">
        <h4 class="ai-block__title">Subject Line Alternatives</h4>
        <div class="ai-suggestions">
          ${data.subject_alternatives.map(s => `
            <div class="ai-suggestion" data-copy="${escAttr(s)}">
              <span>${escHtml(s)}</span>
              <span class="ai-copy-icon">Copy</span>
            </div>`).join('')}
        </div>
      </div>`;
  } else { subEl.innerHTML = ''; }

  // ── Preheader ──
  const phEl = $('#aiPreheader');
  if (data.preheader_suggestion) {
    phEl.innerHTML = `
      <div class="ai-block">
        <h4 class="ai-block__title">Preheader Suggestion</h4>
        <div class="ai-suggestion" data-copy="${escAttr(data.preheader_suggestion)}">
          <span>${escHtml(data.preheader_suggestion)}</span>
          <span class="ai-copy-icon">Copy</span>
        </div>
      </div>`;
  } else { phEl.innerHTML = ''; }

  // ── Opening hook ──
  const hookEl = $('#aiOpeningHook');
  if (data.opening_hook) {
    hookEl.innerHTML = `
      <div class="ai-block">
        <h4 class="ai-block__title">Opening Hook</h4>
        <div class="ai-text-block">
          <p>${escHtml(data.opening_hook)}</p>
          <button type="button" class="dns-copy-btn" data-copy="${escAttr(data.opening_hook)}">Copy</button>
        </div>
      </div>`;
  } else { hookEl.innerHTML = ''; }

  // ── Body rewrite ──
  const bodyEl = $('#aiBodyRewrite');
  if (data.body_rewrite) {
    const paragraphs = data.body_rewrite.split(/\n\n+/).filter(Boolean);
    bodyEl.innerHTML = `
      <div class="ai-block">
        <h4 class="ai-block__title">Full Body Rewrite</h4>
        <div class="ai-text-block ai-text-block--body">
          ${paragraphs.map(p => `<p>${escHtml(p)}</p>`).join('')}
          <button type="button" class="dns-copy-btn" data-copy="${escAttr(data.body_rewrite)}">Copy All</button>
        </div>
      </div>`;
  } else { bodyEl.innerHTML = ''; }

  // ── Closing ──
  const closeEl = $('#aiClosingRewrite');
  if (data.closing_rewrite) {
    closeEl.innerHTML = `
      <div class="ai-block">
        <h4 class="ai-block__title">Closing Paragraph</h4>
        <div class="ai-text-block">
          <p>${escHtml(data.closing_rewrite)}</p>
          <button type="button" class="dns-copy-btn" data-copy="${escAttr(data.closing_rewrite)}">Copy</button>
        </div>
      </div>`;
  } else { closeEl.innerHTML = ''; }

  // ── CTA alternatives ──
  const ctaEl = $('#aiCtaAlts');
  if (data.cta_alternatives?.length) {
    ctaEl.innerHTML = `
      <div class="ai-block">
        <h4 class="ai-block__title">CTA Button Alternatives</h4>
        <div class="ai-cta-grid">
          ${data.cta_alternatives.map(c => `
            <button type="button" class="ai-cta-example" data-copy="${escAttr(c)}">${escHtml(c)}</button>`).join('')}
        </div>
      </div>`;
  } else { ctaEl.innerHTML = ''; }

  // ── Tips ──
  const tipsEl = $('#aiTips');
  if (data.tips?.length) {
    tipsEl.innerHTML = `
      <div class="ai-block">
        <h4 class="ai-block__title">What Changed &amp; Why</h4>
        <ul class="ai-tips-list">
          ${data.tips.map(t => `<li>${escHtml(t)}</li>`).join('')}
        </ul>
      </div>`;
  } else { tipsEl.innerHTML = ''; }

  // ── Meta ──
  const metaEl = $('#aiMeta');
  const parts = [];
  if (data.model) parts.push(`Model: ${data.model}`);
  if (data.elapsed_ms) parts.push(`${data.elapsed_ms}ms`);
  if (data.usage?.total_tokens) parts.push(`${data.usage.total_tokens} tokens`);
  if (data.tone) parts.push(`Tone: ${data.tone}`);
  metaEl.textContent = parts.join(' · ');
}

// Click-to-copy for AI suggestions
document.addEventListener('click', e => {
  const suggestion = e.target.closest('.ai-suggestion, .ai-cta-example');
  if (!suggestion) return;
  const text = suggestion.dataset.copy || suggestion.textContent.trim();
  navigator.clipboard.writeText(text).then(() => {
    const copyIcon = suggestion.querySelector('.ai-copy-icon');
    if (copyIcon) {
      const orig = copyIcon.textContent;
      copyIcon.textContent = 'Copied!';
      setTimeout(() => { copyIcon.textContent = orig; }, 1500);
    } else {
      const orig = suggestion.textContent;
      suggestion.textContent = 'Copied!';
      setTimeout(() => { suggestion.textContent = orig; }, 1500);
    }
  }).catch(() => {});
});

// ══════════════════════════════════════════════════════
//  LINK & IMAGE VALIDATION
// ══════════════════════════════════════════════════════
const LI_STATUS = {
  ok:         { icon: '\u2713', label: 'OK',         cls: 'ok' },
  redirect:   { icon: '\u2192', label: 'Redirect',   cls: 'redirect' },
  shortener:  { icon: '\u26A0', label: 'Shortener',  cls: 'shortener' },
  suspicious: { icon: '\u26A0', label: 'Suspicious', cls: 'suspicious' },
  broken:     { icon: '\u2717', label: 'Broken',     cls: 'broken' },
  error:      { icon: '?',     label: 'Error',      cls: 'error' },
  oversized:  { icon: '\u26A0', label: 'Oversized',  cls: 'oversized' },
  insecure:   { icon: '\u26A0', label: 'Insecure',   cls: 'insecure' },
};

function renderLinkImage(data) {
  const { score, label, color, summary: s, links, images, issues, recommendations } = data;
  const clr = READ_COLOR[color] || 'var(--color-blue)';

  // Update badge counts
  const linkCountEl = $('#linkCount');
  const imgCountEl = $('#imageCount');
  if (linkCountEl) { linkCountEl.textContent = links.total; linkCountEl.classList.toggle('has-items', links.total > 0); }
  if (imgCountEl) { imgCountEl.textContent = images.total; imgCountEl.classList.toggle('has-items', images.total > 0); }

  // ── Overview ──
  const statsChips = [
    { label: 'Links', value: s.links_total, ok: s.links_ok, bad: s.links_broken + s.links_error },
    { label: 'Images', value: s.images_total, ok: s.images_ok, bad: s.images_broken + s.images_error },
  ];

  $('#linkImageOverview').innerHTML = `
    <div class="li-overview">
      <div class="li-score-ring" style="border-color:${clr}">
        <span class="li-score-num" style="color:${clr}">${score}</span>
        <span class="li-score-of">/100</span>
      </div>
      <div class="li-overview-info">
        <span class="li-label badge--${color}">${escHtml(label)}</span>
        <div class="li-stat-chips">
          ${statsChips.map(c => `
            <span class="li-chip">
              <strong>${c.value}</strong> ${c.label}
              ${c.bad > 0 ? `<span class="li-chip-bad">${c.bad} issues</span>` : ''}
            </span>`).join('')}
          ${s.links_shortener > 0 ? `<span class="li-chip li-chip--warn">${s.links_shortener} shortener${s.links_shortener !== 1 ? 's' : ''}</span>` : ''}
          ${s.links_http > 0 ? `<span class="li-chip li-chip--warn">${s.links_http} HTTP</span>` : ''}
          ${s.images_no_alt > 0 ? `<span class="li-chip li-chip--warn">${s.images_no_alt} no alt</span>` : ''}
        </div>
        ${data.elapsed_ms ? `<span class="li-timing">Checked in ${data.elapsed_ms}ms</span>` : ''}
      </div>
    </div>`;

  // ── Issues ──
  const issueContainer = $('#linkImageIssues');
  const realIssues = issues.filter(i => i.severity !== 'pass');
  if (realIssues.length) {
    issueContainer.innerHTML = `
      <div class="li-issues">
        ${realIssues.map(iss => {
          const sev = iss.severity || 'medium';
          return `
            <div class="flag-item flag-item--${sev}">
              <div class="flag-item__meta">
                <span class="severity-dot severity-dot--${sev}"></span>
                <span class="flag-item__cat">${escHtml(iss.category || '')}</span>
              </div>
              <div class="flag-item__text">${escHtml(iss.text || '')}</div>
              ${iss.detail ? `<div class="flag-item__rec">${escHtml(iss.detail)}</div>` : ''}
            </div>`;
        }).join('')}
      </div>`;
  } else {
    issueContainer.innerHTML = '<p style="font-size:0.85rem;color:var(--color-green);padding:8px 0">\u2713 All links and images passed validation.</p>';
  }

  // ── Link details ──
  const linkList = $('#linkDetailList');
  if (links.results.length) {
    linkList.innerHTML = links.results.map(r => {
      const st = LI_STATUS[r.status] || LI_STATUS.error;
      const domain = escHtml(r.domain || '');
      const redirectCount = (r.redirects || []).length;
      return `
        <div class="li-detail-row li-detail-row--${st.cls}">
          <span class="li-detail-status li-detail-status--${st.cls}">${st.icon}</span>
          <div class="li-detail-content">
            <span class="li-detail-url" title="${escAttr(r.url)}">${escHtml(_truncUrl(r.url, 70))}</span>
            <div class="li-detail-meta">
              ${r.status_code ? `<span class="li-meta-tag">HTTP ${r.status_code}</span>` : ''}
              ${domain ? `<span class="li-meta-tag">${domain}</span>` : ''}
              ${redirectCount > 0 ? `<span class="li-meta-tag li-meta-tag--warn">${redirectCount} redirect${redirectCount !== 1 ? 's' : ''}</span>` : ''}
              ${r.is_shortener ? '<span class="li-meta-tag li-meta-tag--warn">shortener</span>' : ''}
              ${!r.is_https ? '<span class="li-meta-tag li-meta-tag--warn">HTTP</span>' : ''}
              ${r.text ? `<span class="li-meta-tag li-meta-tag--text">"${escHtml(r.text.slice(0, 30))}"</span>` : ''}
            </div>
            ${r.final_url !== r.url ? `<span class="li-detail-final">Final: ${escHtml(_truncUrl(r.final_url, 60))}</span>` : ''}
          </div>
          ${r.check_time_ms ? `<span class="li-detail-timing">${r.check_time_ms}ms</span>` : ''}
        </div>`;
    }).join('');
  } else {
    linkList.innerHTML = '<p style="font-size:0.82rem;color:var(--text-hint);padding:8px 0">No links found in email body.</p>';
  }

  // ── Image details ──
  const imgList = $('#imageDetailList');
  if (images.results.length) {
    imgList.innerHTML = images.results.map(r => {
      const st = LI_STATUS[r.status] || LI_STATUS.error;
      const sizeStr = r.size_bytes ? `${(r.size_bytes / 1024).toFixed(1)} KB` : '';
      return `
        <div class="li-detail-row li-detail-row--${st.cls}">
          <span class="li-detail-status li-detail-status--${st.cls}">${st.icon}</span>
          <div class="li-detail-content">
            <span class="li-detail-url" title="${escAttr(r.src)}">${escHtml(_truncUrl(r.src, 70))}</span>
            <div class="li-detail-meta">
              ${r.status_code ? `<span class="li-meta-tag">HTTP ${r.status_code}</span>` : ''}
              ${sizeStr ? `<span class="li-meta-tag">${sizeStr}</span>` : ''}
              ${r.content_type ? `<span class="li-meta-tag">${escHtml(r.content_type)}</span>` : ''}
              ${r.alt ? `<span class="li-meta-tag li-meta-tag--text">alt="${escHtml(r.alt.slice(0, 25))}"</span>` : '<span class="li-meta-tag li-meta-tag--warn">no alt</span>'}
              ${r.is_tracking_pixel ? '<span class="li-meta-tag">tracking pixel</span>' : ''}
              ${!r.is_https && !r.src.startsWith('data:') ? '<span class="li-meta-tag li-meta-tag--warn">HTTP</span>' : ''}
            </div>
          </div>
          ${r.check_time_ms ? `<span class="li-detail-timing">${r.check_time_ms}ms</span>` : ''}
        </div>`;
    }).join('');
  } else {
    imgList.innerHTML = '<p style="font-size:0.82rem;color:var(--text-hint);padding:8px 0">No images found in email body.</p>';
  }

  // ── Recommendations ──
  const recList = $('#linkImageRecList');
  if (recommendations?.length) {
    recList.innerHTML = recommendations.map(rec => `
      <div class="rec-item"><div class="rec-item__text">${escHtml(rec)}</div></div>`).join('');
  } else {
    recList.innerHTML = '';
  }
}

function _truncUrl(url, max) {
  if (!url || url.length <= max) return url || '';
  return url.slice(0, max - 3) + '...';
}

// ══════════════════════════════════════════════════════
//  BIMI VALIDATION
// ══════════════════════════════════════════════════════
const BIMI_STATUS = {
  pass:    { icon: '\u2713', label: 'Fully Configured', color: 'var(--color-green)',  cls: 'pass' },
  partial: { icon: '\u26A0', label: 'Partially Set Up', color: 'var(--color-yellow)', cls: 'partial' },
  invalid: { icon: '\u2717', label: 'Invalid',          color: 'var(--color-orange)', cls: 'invalid' },
  missing: { icon: '\u2717', label: 'Not Configured',   color: 'var(--color-red)',    cls: 'missing' },
};

function renderBimi(data) {
  const st = BIMI_STATUS[data.status] || BIMI_STATUS.missing;

  // ── Overview ──
  $('#bimiOverview').innerHTML = `
    <div class="bimi-overview">
      <div class="bimi-score-ring" style="border-color:${st.color}">
        <span class="bimi-score-num" style="color:${st.color}">${data.score}</span>
        <span class="bimi-score-of">/${data.max_score}</span>
      </div>
      <div class="bimi-overview-info">
        <span class="bimi-status-badge bimi-status-badge--${st.cls}">${st.icon} ${st.label}</span>
        <span class="bimi-domain">${escHtml(data.domain)}</span>
        <span class="bimi-dns-host">${escHtml(data.dns_host)}</span>
        ${data.elapsed_ms ? `<span class="bimi-timing">${data.elapsed_ms}ms</span>` : ''}
      </div>
    </div>`;

  // ── Details grid ──
  const details = [];

  // Record
  if (data.record && data.record.found) {
    details.push({ label: 'DNS Record', value: 'Found', status: 'pass', detail: data.record.raw });
  } else {
    details.push({ label: 'DNS Record', value: 'Missing', status: 'fail', detail: `No TXT at ${data.dns_host}` });
  }

  // DMARC prerequisite
  if (data.dmarc) {
    if (data.dmarc.meets_requirement) {
      details.push({ label: 'DMARC', value: `p=${data.dmarc.policy}`, status: 'pass', detail: 'Meets BIMI requirement' });
    } else {
      details.push({ label: 'DMARC', value: `p=${data.dmarc.policy}`, status: 'fail', detail: data.dmarc.issue || 'Needs quarantine or reject' });
    }
  }

  // Logo
  if (data.logo) {
    if (data.logo.valid) {
      const size = data.logo.size_bytes ? `${(data.logo.size_bytes / 1024).toFixed(1)} KB` : '';
      details.push({ label: 'SVG Logo', value: 'Valid', status: 'pass', detail: size ? `${size} — ${data.logo.content_type}` : 'Passed all checks' });
    } else if (data.logo.url) {
      details.push({ label: 'SVG Logo', value: 'Issues Found', status: 'warn', detail: (data.logo.issues || [])[0] || 'Check issues below' });
    } else {
      details.push({ label: 'SVG Logo', value: 'Missing', status: 'fail', detail: 'No logo URL in BIMI record' });
    }
  }

  // VMC
  if (data.vmc) {
    if (data.vmc.valid) {
      details.push({ label: 'VMC Certificate', value: 'Valid', status: 'pass', detail: 'Verified Mark Certificate found' });
    } else if (data.vmc.url) {
      details.push({ label: 'VMC Certificate', value: 'Issues Found', status: 'warn', detail: (data.vmc.issues || [])[0] || 'Check issues below' });
    } else {
      details.push({ label: 'VMC Certificate', value: 'Not Set', status: 'info', detail: 'Optional — needed for Gmail logo display' });
    }
  }

  const STATUS_ICON = { pass: '\u2713', fail: '\u2717', warn: '\u26A0', info: '\u2139' };

  $('#bimiDetails').innerHTML = `
    <div class="bimi-details-grid">
      ${details.map(d => `
        <div class="bimi-detail-card bimi-detail-card--${d.status}">
          <div class="bimi-detail-header">
            <span class="bimi-detail-icon bimi-detail-icon--${d.status}">${STATUS_ICON[d.status] || '?'}</span>
            <span class="bimi-detail-label">${escHtml(d.label)}</span>
          </div>
          <span class="bimi-detail-value">${escHtml(d.value)}</span>
          <span class="bimi-detail-info">${escHtml(d.detail || '')}</span>
        </div>`).join('')}
    </div>`;

  // ── Issues ──
  const issueContainer = $('#bimiIssues');
  const issues = data.issues || [];
  if (issues.length) {
    issueContainer.innerHTML = `
      <div class="bimi-issues">
        ${issues.map(iss => {
          const sev = iss.severity || 'medium';
          return `
            <div class="flag-item flag-item--${sev}">
              <div class="flag-item__meta">
                <span class="severity-dot severity-dot--${sev}"></span>
                <span class="flag-item__cat">BIMI</span>
              </div>
              <div class="flag-item__text">${escHtml(iss.text || '')}</div>
              ${iss.detail ? `<div class="flag-item__rec">${escHtml(iss.detail)}</div>` : ''}
            </div>`;
        }).join('')}
      </div>`;
  } else {
    issueContainer.innerHTML = '';
  }

  // ── Recommendations ──
  const recList = $('#bimiRecList');
  const recs = data.recommendations || [];
  if (recs.length) {
    recList.innerHTML = recs.map(rec => {
      const sevCls = rec.severity === 'pass' ? 'pass' : rec.severity === 'high' ? 'high' : rec.severity === 'low' ? 'low' : 'medium';
      const hasRecord = rec.record;
      return `
        <div class="rec-item bimi-rec bimi-rec--${sevCls}">
          <div class="rec-item__header">
            <span class="rec-item__cat">${escHtml(rec.title || '')}</span>
          </div>
          <div class="rec-item__text">${escHtml(rec.text || '')}</div>
          ${rec.steps?.length ? `
            <ol class="bimi-rec-steps">
              ${rec.steps.map(s => `<li>${escHtml(s)}</li>`).join('')}
            </ol>` : ''}
          ${hasRecord ? `
            <div class="dns-record-block" style="margin-top:10px">
              <div class="dns-record-row">
                <span class="dns-record-label">Host:</span>
                <code class="dns-record-value">${escHtml(rec.record.host)}</code>
                <button type="button" class="dns-copy-btn" data-copy="${escAttr(rec.record.host)}">Copy</button>
              </div>
              <div class="dns-record-row">
                <span class="dns-record-label">Type:</span>
                <code class="dns-record-value">${escHtml(rec.record.type)}</code>
              </div>
              <div class="dns-record-row">
                <span class="dns-record-label">Value:</span>
                <code class="dns-record-value dns-record-value--main">${escHtml(rec.record.value)}</code>
                <button type="button" class="dns-copy-btn" data-copy="${escAttr(rec.record.value)}">Copy</button>
              </div>
            </div>` : ''}
        </div>`;
    }).join('');
  } else {
    recList.innerHTML = '';
  }
}

// ══════════════════════════════════════════════════════
//  DNS RECORD SUGGESTIONS
// ══════════════════════════════════════════════════════
function renderDnsSuggestions(data) {
  const container = $('#dnsSuggestions');
  const suggestions = data.suggestions || [];
  if (!suggestions.length) {
    container.style.display = 'none';
    return;
  }

  const TYPE_ICON = { spf: 'SPF', dkim: 'DKIM', dmarc: 'DMARC' };
  const ACTION_LABEL = { create: 'Create', fix: 'Fix', upgrade: 'Upgrade' };

  container.innerHTML = `
    <div class="dns-section">
      <h3 class="dns-section__title">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:18px;height:18px;vertical-align:middle;margin-right:6px"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18"/><path d="M9 21V9"/></svg>
        DNS Record Generator
      </h3>
      <p class="dns-section__subtitle">Copy-paste records to fix your email authentication</p>
      ${suggestions.map(s => renderDnsSuggestion(s)).join('')}
    </div>`;
}

function renderDnsSuggestion(s) {
  const type = (s.type || '').toUpperCase();
  const action = s._action || 'create';
  const actionLabel = { create: 'Add New', fix: 'Fix Existing', upgrade: 'Upgrade' }[action] || action;

  let recordBlock = '';

  if (s.type === 'dkim') {
    // DKIM is instruction-based (ESP generates the key)
    const instructions = s.instructions || [];
    recordBlock = `
      <div class="dns-instructions">
        <h5>Setup Steps</h5>
        <ol class="dns-steps">
          ${instructions.map(step => `<li>${escHtml(step)}</li>`).join('')}
        </ol>
        ${s.host_example ? `
          <div class="dns-record-row">
            <span class="dns-record-label">DNS Host:</span>
            <code class="dns-record-value">${escHtml(s.host_example)}</code>
            <button type="button" class="dns-copy-btn" data-copy="${escAttr(s.host_example)}">Copy</button>
          </div>` : ''}
        ${s.record_example ? `
          <div class="dns-record-row">
            <span class="dns-record-label">Record Format:</span>
            <code class="dns-record-value">${escHtml(s.record_example)}</code>
          </div>` : ''}
      </div>`;
  } else if (s.record) {
    // SPF or DMARC — show the actual record to copy
    recordBlock = `
      ${s.current_record ? `
        <div class="dns-current">
          <span class="dns-record-label">Current:</span>
          <code class="dns-record-value dns-record-value--old">${escHtml(s.current_record)}</code>
        </div>` : ''}
      <div class="dns-record-block">
        <div class="dns-record-row">
          <span class="dns-record-label">Host:</span>
          <code class="dns-record-value">${escHtml(s.dns_name || s.host)}</code>
          <button type="button" class="dns-copy-btn" data-copy="${escAttr(s.dns_name || s.host)}">Copy</button>
        </div>
        <div class="dns-record-row">
          <span class="dns-record-label">Type:</span>
          <code class="dns-record-value">${escHtml(s.dns_type || 'TXT')}</code>
        </div>
        <div class="dns-record-row">
          <span class="dns-record-label">Value:</span>
          <code class="dns-record-value dns-record-value--main">${escHtml(s.record)}</code>
          <button type="button" class="dns-copy-btn" data-copy="${escAttr(s.record)}">Copy</button>
        </div>
      </div>`;
  }

  const warnings = (s.warnings || []).filter(Boolean);

  return `
    <div class="dns-suggestion dns-suggestion--${s.type}">
      <div class="dns-suggestion__header">
        <span class="dns-badge dns-badge--${s.type}">${type}</span>
        <span class="dns-action-label">${escHtml(actionLabel)}</span>
        <span class="dns-suggestion__title">${escHtml(s._title || '')}</span>
      </div>
      <p class="dns-suggestion__desc">${escHtml(s._description || '')}</p>
      ${s.explanation ? `<p class="dns-suggestion__explain">${escHtml(s.explanation)}</p>` : ''}
      ${recordBlock}
      ${warnings.length ? `
        <div class="dns-warnings">
          ${warnings.map(w => `<div class="dns-warning">${escHtml(w)}</div>`).join('')}
        </div>` : ''}
    </div>`;
}

// ══════════════════════════════════════════════════════
//  PRE-SEND AUDIT CHECKLIST
// ══════════════════════════════════════════════════════
const AUDIT_COLOR = {
  green: 'var(--color-green)', blue: 'var(--color-blue)',
  yellow: 'var(--color-yellow)', orange: 'var(--color-orange)', red: 'var(--color-red)',
};
const AUDIT_VERDICT_ICON = {
  ready: '\u2713', mostly_ready: '\u2713', review: '\u26A0', fix_needed: '\u2717', not_ready: '\u2717',
};
const AUDIT_CHECK_ICON = {
  pass: '\u2713', warn: '\u26A0', fail: '\u2717', info: '\u2139',
};
const AUDIT_CAT_ICON = {
  shield: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>',
  target: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/></svg>',
  book: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5A2.5 2.5 0 016.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z"/></svg>',
  link: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71"/></svg>',
  lock: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0110 0v4"/></svg>',
  badge: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M9 12l2 2 4-4"/></svg>',
};

function renderAuditBanner(audit) {
  const banner = $('#auditBanner');
  const clr = AUDIT_COLOR[audit.color] || 'var(--color-blue)';
  const icon = AUDIT_VERDICT_ICON[audit.verdict] || '?';
  const c = audit.counts;

  banner.style.display = '';
  banner.innerHTML = `
    <div class="audit-banner audit-banner--${audit.verdict}" style="border-color:${clr}">
      <div class="audit-banner__left">
        <span class="audit-banner__icon" style="color:${clr}">${icon}</span>
        <div class="audit-banner__info">
          <span class="audit-banner__label" style="color:${clr}">${escHtml(audit.verdict_label)}</span>
          <span class="audit-banner__summary">${escHtml(audit.verdict_summary)}</span>
        </div>
      </div>
      <div class="audit-banner__right">
        <span class="audit-banner__pct" style="color:${clr}">${audit.pass_pct}%</span>
        <div class="audit-banner__counts">
          ${c.pass > 0 ? `<span class="audit-count audit-count--pass">${c.pass} passed</span>` : ''}
          ${c.warn > 0 ? `<span class="audit-count audit-count--warn">${c.warn} warnings</span>` : ''}
          ${c.fail > 0 ? `<span class="audit-count audit-count--fail">${c.fail} failed</span>` : ''}
        </div>
      </div>
    </div>`;
}

function renderAuditChecklist(audit) {
  const module = $('#auditModule');
  const container = $('#auditChecklist');
  module.style.display = '';

  container.innerHTML = audit.categories.map(cat => {
    const iconSvg = AUDIT_CAT_ICON[cat.icon] || '';
    const allPass = cat.pass_count === cat.total;

    return `
      <div class="audit-category ${allPass ? 'audit-category--pass' : ''}">
        <div class="audit-category__header">
          <span class="audit-category__icon">${iconSvg}</span>
          <span class="audit-category__name">${escHtml(cat.name)}</span>
          <span class="audit-category__score">${cat.pass_count}/${cat.total}</span>
        </div>
        <div class="audit-checks">
          ${cat.checks.map(chk => {
            const icon = AUDIT_CHECK_ICON[chk.status] || '?';
            return `
              <div class="audit-check audit-check--${chk.status}">
                <span class="audit-check__icon audit-check__icon--${chk.status}">${icon}</span>
                <span class="audit-check__label">${escHtml(chk.label)}</span>
                <span class="audit-check__detail">${escHtml(chk.detail)}</span>
              </div>`;
          }).join('')}
        </div>
      </div>`;
  }).join('');
}

function showError(msg) {
  $('#emptyState').innerHTML = `
    <div class="empty-logo" style="opacity:1">INBXR</div>
    <h3 style="color:var(--color-red)">Error</h3>
    <p>${escHtml(msg)}</p>`;
  $('#emptyState').classList.remove('hidden');
  $('#resultsContent').classList.add('hidden');
}

// ── Sanitization ─────────────────────────────────────
function escHtml(str) {
  return String(str ?? '')
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}
function escAttr(str) {
  return String(str ?? '').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

// ══════════════════════════════════════════════════════
//  HISTORY — Auto-save to localStorage
// ══════════════════════════════════════════════════════
function _saveToHistory(data, payload) {
  try {
    const STORAGE_KEY = 'inbxr_history';
    const MAX_HISTORY = 50;

    const entry = {
      date: new Date().toISOString(),
      subject: payload?.subject || '',
      sender: payload?.sender_email || '',
      industry: payload?.industry || '',
      spam_score: data.spam?.score ?? null,
      spam_label: data.spam?.label || '',
      spam_color: data.spam?.color || '',
      copy_score: data.copy?.score ?? null,
      copy_label: data.copy?.label || '',
      copy_color: data.copy?.color || '',
      readability_score: data.readability?.score ?? null,
      verdict: data.audit?.verdict || '',
      verdict_label: data.audit?.verdict_label || '',
      pass_pct: data.audit?.pass_pct ?? null,
    };

    let history = [];
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      history = raw ? JSON.parse(raw) : [];
    } catch { history = []; }

    history.push(entry);

    // Trim to max
    if (history.length > MAX_HISTORY) {
      history = history.slice(-MAX_HISTORY);
    }

    localStorage.setItem(STORAGE_KEY, JSON.stringify(history));
  } catch (e) {
    // Silent fail — localStorage may be full or unavailable
  }
}

// ══════════════════════════════════════════════════════
//  ANALYSIS PROGRESS INDICATOR
// ══════════════════════════════════════════════════════
let progressInterval = null;

function showAnalysisProgress() {
  const overlay = $('#analysisProgress');
  if (!overlay) return;
  overlay.classList.remove('hidden');
  $('#emptyState').classList.add('hidden');
  $('#resultsContent').classList.add('hidden');
  const vEl = $('#analyzerVerdict');
  if (vEl) vEl.style.display = 'none';

  const steps = $$('.ap-step', overlay);
  steps.forEach(s => { s.classList.remove('active', 'done'); });

  let idx = 0;
  steps[0].classList.add('active');

  progressInterval = setInterval(() => {
    if (idx < steps.length) {
      steps[idx].classList.remove('active');
      steps[idx].classList.add('done');
    }
    idx++;
    if (idx < steps.length) {
      steps[idx].classList.add('active');
    } else {
      clearInterval(progressInterval);
    }
  }, 600);
}

function hideAnalysisProgress() {
  clearInterval(progressInterval);
  const overlay = $('#analysisProgress');
  if (overlay) overlay.classList.add('hidden');
}

// ══════════════════════════════════════════════════════
//  RESULTS NAVIGATION — Scroll Spy & Click
// ══════════════════════════════════════════════════════
function initResultsNav() {
  const nav = $('#resultsNav');
  if (!nav) return;

  // Hide nav links for modules that are hidden
  $$('.rnav-link', nav).forEach(link => {
    const target = link.getAttribute('href')?.replace('#', '');
    if (!target) return;
    const el = $(`#${target}`);
    if (el && el.style.display === 'none') {
      link.classList.add('rnav-hidden');
    } else {
      link.classList.remove('rnav-hidden');
    }
  });

  // Click handler — smooth scroll
  $$('.rnav-link', nav).forEach(link => {
    link.addEventListener('click', e => {
      e.preventDefault();
      const target = link.getAttribute('href')?.replace('#', '');
      const el = target ? $(`#${target}`) : null;
      if (el) {
        const headerH = parseInt(getComputedStyle(document.documentElement).getPropertyValue('--header-h')) || 58;
        const navH = nav.offsetHeight || 40;
        const top = el.getBoundingClientRect().top + window.scrollY - headerH - navH - 8;
        window.scrollTo({ top, behavior: 'smooth' });
      }
    });
  });

  // Scroll spy
  let rafPending = false;
  const onScroll = () => {
    if (rafPending) return;
    rafPending = true;
    requestAnimationFrame(() => {
      rafPending = false;
      const headerH = parseInt(getComputedStyle(document.documentElement).getPropertyValue('--header-h')) || 58;
      const navH = nav.offsetHeight || 40;
      const offset = headerH + navH + 20;

      let activeId = 'scores-section';
      $$('.rnav-link:not(.rnav-hidden)', nav).forEach(link => {
        const target = link.getAttribute('href')?.replace('#', '');
        const el = target ? $(`#${target}`) : null;
        if (el) {
          const rect = el.getBoundingClientRect();
          if (rect.top <= offset + 100) activeId = target;
        }
      });

      $$('.rnav-link', nav).forEach(l => l.classList.remove('active'));
      const activeLink = $(`.rnav-link[href="#${activeId}"]`, nav);
      if (activeLink) {
        activeLink.classList.add('active');
        // Scroll nav to keep active link visible
        activeLink.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
      }
    });
  };

  window.addEventListener('scroll', onScroll, { passive: true });
}

// ══════════════════════════════════════════════════════
//  MODULE COLLAPSE / EXPAND
// ══════════════════════════════════════════════════════
document.addEventListener('click', e => {
  const header = e.target.closest('.module-header.collapsible');
  if (!header) return;
  const block = header.closest('.module-block');
  if (block) block.classList.toggle('collapsed');
});

// ══════════════════════════════════════════════════════
//  EMAIL RENDERING PREVIEW
// ══════════════════════════════════════════════════════
let _emailBodyHtml = '';
let _emailSubject = '';

function renderEmailPreview(bodyHtml, subject) {
  _emailBodyHtml = bodyHtml || '';
  _emailSubject = subject || 'Untitled Email';

  const module = $('#emailPreviewModule');
  if (!module || !_emailBodyHtml.trim()) {
    if (module) module.style.display = 'none';
    return;
  }
  module.style.display = '';

  $('#epChromeTitle').textContent = _emailSubject;
  _writePreviewIframe(_emailBodyHtml, false);
}

function _writePreviewIframe(html, darkMode) {
  const iframe = $('#emailPreviewIframe');
  if (!iframe) return;

  const darkStyles = darkMode ? `
    <style>
      body { background: #1a1a2e !important; color: #e0e0e0 !important; }
      * { color: inherit !important; border-color: #333 !important; }
      a { color: #6db3f2 !important; }
      img { opacity: 0.85; }
      table, td, th { background: transparent !important; }
    </style>
  ` : '';

  const doc = `<!DOCTYPE html>
<html><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
  body { margin: 0; padding: 16px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 14px; line-height: 1.5; word-break: break-word; }
  img { max-width: 100%; height: auto; }
  a { color: #1a73e8; }
  table { max-width: 100%; }
</style>
${darkStyles}
</head><body>${html}</body></html>`;

  const blob = new Blob([doc], { type: 'text/html' });
  iframe.src = URL.createObjectURL(blob);

  // Auto-resize iframe height after load
  iframe.onload = () => {
    try {
      const h = iframe.contentDocument.documentElement.scrollHeight;
      iframe.style.height = Math.min(Math.max(h + 20, 200), 800) + 'px';
    } catch (e) {}
  };
}

// Viewport toggle
document.addEventListener('click', e => {
  const btn = e.target.closest('.ep-viewport-btn');
  if (!btn) return;
  $$('.ep-viewport-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');

  const chrome = $('#epChrome');
  if (!chrome) return;
  const viewport = btn.dataset.viewport;
  chrome.classList.remove('ep-frame-chrome--desktop', 'ep-frame-chrome--mobile');
  chrome.classList.add(`ep-frame-chrome--${viewport}`);
});

// Client/dark mode toggle
document.addEventListener('click', e => {
  const btn = e.target.closest('.ep-client-btn');
  if (!btn) return;
  $$('.ep-client-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');

  const darkMode = btn.dataset.client === 'gmail';
  _writePreviewIframe(_emailBodyHtml, darkMode);
});

// ══════════════════════════════════════════════════════
//  EXPORT REPORT — Standalone HTML Download
// ══════════════════════════════════════════════════════
let _lastAnalysisData = null;
let _lastPayload = null;

document.addEventListener('click', e => {
  if (!e.target.closest('#exportReportBtn')) return;
  if (!_lastAnalysisData) return;
  exportReport(_lastAnalysisData, _lastPayload);
});

function exportReport(data, payload) {
  const now = new Date();
  const dateStr = now.toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });
  const timeStr = now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });

  const spam = data.spam || {};
  const copy = data.copy || {};
  const audit = data.audit || {};
  const readability = data.readability || {};
  const reputation = data.reputation || {};
  const linkImage = data.link_image || {};

  const verdictColors = {
    ready: '#059669', mostly_ready: '#3b82f6', review: '#d97706',
    fix_needed: '#ea580c', not_ready: '#dc2626'
  };
  const verdictColor = verdictColors[audit.verdict] || '#475569';

  // Build audit checks HTML
  let auditHTML = '';
  if (audit.categories) {
    audit.categories.forEach(cat => {
      auditHTML += `<h3 style="font-size:14px;font-weight:700;color:#0f172a;margin:20px 0 8px;border-bottom:1px solid #e2e8f0;padding-bottom:6px">${esc(cat.group)}</h3>`;
      (cat.checks || []).forEach(chk => {
        const icon = chk.status === 'pass' ? '&#10003;' : chk.status === 'fail' ? '&#10007;' : chk.status === 'warn' ? '&#9888;' : '&#8505;';
        const colors = { pass: '#059669', fail: '#dc2626', warn: '#d97706', info: '#3b82f6' };
        const c = colors[chk.status] || '#94a3b8';
        auditHTML += `<div style="display:flex;align-items:flex-start;gap:10px;padding:6px 0;font-size:13px">
          <span style="color:${c};font-weight:700;min-width:18px">${icon}</span>
          <span style="font-weight:600;min-width:180px;color:#0f172a">${esc(chk.label)}</span>
          <span style="color:#475569">${esc(chk.detail)}</span>
        </div>`;
      });
    });
  }

  // Spam flags
  let flagsHTML = '';
  (spam.high_risk_elements || []).forEach(f => {
    flagsHTML += `<div style="padding:8px 12px;margin:4px 0;background:#fef2f2;border-left:3px solid #dc2626;border-radius:4px;font-size:13px">
      <strong>${esc(f.category || '')}</strong>: ${esc(f.text || '')}
    </div>`;
  });

  // Recommendations
  let recsHTML = '';
  (spam.top_recommendations || []).forEach(r => {
    recsHTML += `<div style="padding:8px 12px;margin:4px 0;background:#f0f9ff;border-left:3px solid #3b82f6;border-radius:4px;font-size:13px">
      <strong>${esc(r.issue || '')}</strong><br>${esc(r.recommendation || '')}
    </div>`;
  });

  const html = `<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>INBXR Report — ${esc(payload?.subject || 'Email Analysis')}</title>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; background:#f8fafc; color:#0f172a; line-height:1.6; padding:40px 24px; }
  .container { max-width:800px; margin:0 auto; }
  .header { text-align:center; margin-bottom:32px; }
  .header h1 { font-size:28px; font-weight:800; letter-spacing:-0.03em; margin-bottom:4px; }
  .header p { color:#64748b; font-size:14px; }
  .verdict-bar { text-align:center; padding:16px 24px; border-radius:10px; margin-bottom:24px; color:#fff; font-weight:700; font-size:18px; }
  .scores { display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-bottom:24px; }
  .score-box { background:#fff; border:1px solid #e2e8f0; border-radius:10px; padding:20px; text-align:center; }
  .score-num { font-size:36px; font-weight:800; line-height:1; }
  .score-label { font-size:12px; text-transform:uppercase; letter-spacing:0.08em; color:#64748b; margin-top:4px; }
  .section { background:#fff; border:1px solid #e2e8f0; border-radius:10px; padding:20px; margin-bottom:16px; }
  .section h2 { font-size:16px; font-weight:700; margin-bottom:12px; color:#0f172a; }
  .meta { display:flex; flex-wrap:wrap; gap:8px; margin-bottom:24px; justify-content:center; }
  .meta-tag { background:#fff; border:1px solid #e2e8f0; border-radius:999px; padding:4px 12px; font-size:12px; color:#475569; }
  .footer { text-align:center; margin-top:32px; color:#94a3b8; font-size:12px; }
  @media print { body { padding:20px; } .container { max-width:100%; } }
</style>
</head><body>
<div class="container">
  <div class="header">
    <h1>INBXR Analysis Report</h1>
    <p>${esc(dateStr)} at ${esc(timeStr)}</p>
  </div>

  <div class="meta">
    <span class="meta-tag"><strong>Subject:</strong> ${esc(payload?.subject || '—')}</span>
    <span class="meta-tag"><strong>Sender:</strong> ${esc(payload?.sender_email || '—')}</span>
    <span class="meta-tag"><strong>Industry:</strong> ${esc(payload?.industry || '—')}</span>
  </div>

  ${audit.verdict ? `<div class="verdict-bar" style="background:${verdictColor}">${esc(audit.verdict_label || audit.verdict)} — ${audit.pass_pct || 0}% checks passed</div>` : ''}

  <div class="scores">
    <div class="score-box">
      <div class="score-num" style="color:${spam.color === 'green' ? '#059669' : spam.color === 'red' ? '#dc2626' : '#d97706'}">${spam.score ?? '—'}</div>
      <div class="score-label">Spam Risk</div>
      <div style="font-size:13px;color:#475569;margin-top:6px">${esc(spam.summary || '')}</div>
    </div>
    <div class="score-box">
      <div class="score-num" style="color:${copy.color === 'green' ? '#059669' : copy.color === 'red' ? '#dc2626' : '#3b82f6'}">${copy.score ?? '—'}</div>
      <div class="score-label">Copy Effectiveness</div>
      <div style="font-size:13px;color:#475569;margin-top:6px">${esc(copy.summary || '')}</div>
    </div>
  </div>

  ${readability.score != null ? `<div class="section">
    <h2>Readability</h2>
    <div style="display:flex;gap:20px;flex-wrap:wrap">
      <div><strong style="font-size:24px">${readability.score}</strong><span style="color:#64748b">/100</span></div>
      <div style="font-size:13px;color:#475569">Grade Level: ${esc(readability.grade_level || '—')} &middot; Avg Sentence: ${readability.avg_sentence_length || '—'} words</div>
    </div>
  </div>` : ''}

  ${flagsHTML ? `<div class="section"><h2>High-Risk Elements</h2>${flagsHTML}</div>` : ''}
  ${recsHTML ? `<div class="section"><h2>Recommendations</h2>${recsHTML}</div>` : ''}

  ${auditHTML ? `<div class="section"><h2>Pre-Send Audit Checklist</h2>${auditHTML}</div>` : ''}

  <div class="footer">
    Generated by INBXR &mdash; Email Pre-Send Analysis Tool
  </div>
</div>
</body></html>`;

  const blob = new Blob([html], { type: 'text/html' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `inbxr-report-${now.toISOString().slice(0,10)}.html`;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { document.body.removeChild(a); URL.revokeObjectURL(url); }, 100);
}

function esc(s) { return escHtml(s); }

/* ── Typewriter effect for hero headings ── */
(function() {
  document.addEventListener('DOMContentLoaded', function() {
    var el = document.querySelector('.tool-hero__h1, .sender-hero__title');
    if (!el || el.getAttribute('contenteditable') === 'true') return;

    var fullText = el.textContent.trim();
    el.textContent = '';
    el.classList.add('typewriter');
    el.style.visibility = 'visible';

    var i = 0;
    var speed = 45;

    function type() {
      if (i < fullText.length) {
        el.textContent += fullText.charAt(i);
        i++;
        setTimeout(type, speed);
      } else {
        setTimeout(function() {
          el.classList.add('typewriter--done');
        }, 600);
      }
    }

    type();
  });
})();
