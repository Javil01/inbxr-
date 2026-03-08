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
  const btn = e.target.closest('.copy-btn, .subject-suggestion, .cta-example');
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

  try {
    const res  = await fetch('/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();

    if (!res.ok || data.error) {
      showError(data.error || 'Analysis failed. Please try again.');
      return;
    }

    renderResults(data, payload);
  } catch (err) {
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
function renderResults(data, payload) {
  const { spam, copy, meta } = data;

  $('#emptyState').classList.add('hidden');
  const rc = $('#resultsContent');
  rc.classList.remove('hidden');

  if (window.innerWidth < 900) rc.scrollIntoView({ behavior: 'smooth', block: 'start' });

  renderMetaBar(meta);
  renderGauge('spam', spam.score, spam.label, spam.color, spam.summary);
  renderGauge('copy', copy.score, copy.label, copy.color, copy.summary);

  renderCategoryBars('spamCategories', spam.categories, 'spam');
  renderFlagList('spamFlagList', spam.high_risk_elements);
  updateBadgeCount('spamHighRiskCount', (spam.high_risk_elements || []).length);
  renderRecList('spamRecList', spam.top_recommendations);

  renderCategoryBars('copyCategories', copy.categories, 'copy');
  renderStrengthsWeaknesses(copy.strengths, copy.weaknesses);
  renderFlagList('copyFlagList', copy.all_flags, true);
  updateBadgeCount('copyFlagCount', (copy.all_flags || []).length);
  renderRewrites(copy.rewrites, payload.subject);

  rc.classList.add('fade-in');
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

function renderFlagList(containerId, flags) {
  const container = $(`#${containerId}`);
  if (!flags?.length) {
    container.innerHTML = '<p style="font-size:0.8rem;color:var(--text-secondary);padding:8px 0">No issues in this category.</p>';
    return;
  }
  container.innerHTML = flags.map(flag => {
    const sev = flag.severity || flag.impact || 'low';
    return `
      <div class="flag-item flag-item--${sev}">
        <div class="flag-item__meta">
          <span class="severity-dot severity-dot--${sev}"></span>
          <span class="flag-item__cat">${escHtml(flag.category || '')}</span>
        </div>
        <div class="flag-item__text">${escHtml(flag.item || '')}</div>
        ${flag.recommendation ? `<div class="flag-item__rec">${escHtml(flag.recommendation)}</div>` : ''}
      </div>`;
  }).join('');
}

function renderRecList(containerId, recs) {
  const container = $(`#${containerId}`);
  if (!recs?.length) {
    container.innerHTML = '<p style="font-size:0.8rem;color:var(--color-green);padding:8px 0">✓ No major spam issues found.</p>';
    return;
  }
  container.innerHTML = recs.map(rec => `
    <div class="rec-item">
      <div class="rec-item__header">
        <span class="rec-item__cat">${escHtml(rec.category || '')}</span>
        <button class="copy-btn" data-copy="${escAttr(rec.recommendation)}">Copy</button>
      </div>
      <div class="rec-item__issue">${escHtml(rec.item || '')}</div>
      <div class="rec-item__text">${escHtml(rec.recommendation || '')}</div>
    </div>`).join('');
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
