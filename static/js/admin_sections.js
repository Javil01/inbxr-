/* ══════════════════════════════════════════════════════
   INBXR — Section Library Manager
   Add / remove page sections via admin toolbar
   ══════════════════════════════════════════════════════ */
'use strict';

(function() {

var PAGE_NAME = document.body.dataset.page || 'index';

// ── Add "Sections" button to toolbar ──────────────────
var toolbar = document.querySelector('.admin-toolbar');
if (!toolbar) return;

var sep = document.createElement('span');
sep.className = 'admin-toolbar__sep';
toolbar.appendChild(sep);

var btn = document.createElement('button');
btn.textContent = 'Sections';
btn.className = 'admin-toolbar__style-btn';
btn.style.cssText = 'background:none;border:1px solid rgba(255,255,255,0.2);color:#c7d2fe;padding:4px 12px;border-radius:6px;font-size:0.75rem;font-weight:600;cursor:pointer;';
btn.addEventListener('click', openLibrary);
toolbar.appendChild(btn);

// ── Add "Preview" button to toolbar ───────────────────
var sep2 = document.createElement('span');
sep2.className = 'admin-toolbar__sep';
toolbar.appendChild(sep2);

var previewBtn = document.createElement('button');
previewBtn.textContent = 'Preview';
previewBtn.className = 'admin-toolbar__style-btn';
previewBtn.style.cssText = 'background:none;border:1px solid rgba(255,255,255,0.2);color:#c7d2fe;padding:4px 12px;border-radius:6px;font-size:0.75rem;font-weight:600;cursor:pointer;';
previewBtn.addEventListener('click', togglePreview);
toolbar.appendChild(previewBtn);

// ── Add "Page Builder" button to toolbar ──────────────
var sep3 = document.createElement('span');
sep3.className = 'admin-toolbar__sep';
toolbar.appendChild(sep3);

var builderBtn = document.createElement('a');
builderBtn.textContent = 'Page Builder';
builderBtn.href = '/admin/builder/' + PAGE_NAME;
builderBtn.className = 'admin-toolbar__style-btn';
builderBtn.style.cssText = 'background:rgba(37,99,235,0.2);border:1px solid #2563eb;color:#bfdbfe;padding:4px 12px;border-radius:6px;font-size:0.75rem;font-weight:600;cursor:pointer;text-decoration:none;';
toolbar.appendChild(builderBtn);

// ── Preview mode ──────────────────────────────────────
function togglePreview() {
  document.body.classList.add('admin-preview');

  var exitBtn = document.createElement('button');
  exitBtn.className = 'admin-preview-exit';
  exitBtn.textContent = 'Exit Preview';
  exitBtn.addEventListener('click', function() {
    document.body.classList.remove('admin-preview');
    this.remove();
  });
  document.body.appendChild(exitBtn);
}

// ── Section Library modal ─────────────────────────────
function openLibrary() {
  fetch('/admin/api/section-library').then(function(r) {
    return r.json();
  }).then(function(d) {
    if (!d.sections) return;
    showModal(d.sections);
  });
}

function showModal(sections) {
  // Get currently used section IDs
  var used = {};
  document.querySelectorAll('.page-section').forEach(function(el) {
    used[el.dataset.sectionId] = true;
  });

  var overlay = document.createElement('div');
  overlay.className = 'section-lib-overlay';

  var html =
    '<div class="section-lib-modal">' +
      '<div class="section-lib-modal__header">' +
        '<span class="section-lib-modal__title">Section Library</span>' +
        '<button class="section-lib-modal__close">&times;</button>' +
      '</div>' +
      '<div class="section-lib-modal__body">';

  sections.forEach(function(sec) {
    var inUse = !!used[sec.id];
    html +=
      '<div class="section-lib-card">' +
        '<div class="section-lib-card__info">' +
          '<span class="section-lib-card__name">' + sec.id + '</span>' +
          '<span class="section-lib-card__desc">' + (sec.template || '') + '</span>' +
        '</div>' +
        (inUse
          ? '<span style="font-size:0.72rem;color:#64748b;">In use</span>'
          : '<button class="section-lib-card__add" data-section-id="' + sec.id + '">Add</button>'
        ) +
      '</div>';
  });

  html += '</div></div>';
  overlay.innerHTML = html;
  document.body.appendChild(overlay);

  // Close handlers
  overlay.querySelector('.section-lib-modal__close').addEventListener('click', function() {
    overlay.remove();
  });
  overlay.addEventListener('click', function(e) {
    if (e.target === overlay) overlay.remove();
  });

  // Add section handlers
  overlay.querySelectorAll('.section-lib-card__add').forEach(function(addBtn) {
    addBtn.addEventListener('click', function() {
      var sectionId = this.dataset.sectionId;
      addSection(sectionId);
      overlay.remove();
    });
  });
}

function addSection(sectionId) {
  fetch('/admin/api/add-section', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ page: PAGE_NAME, section_id: sectionId })
  }).then(function(r) { return r.json(); }).then(function(d) {
    if (d.ok) {
      if (window.showToast) window.showToast('Section added — reloading…');
      setTimeout(function() { location.reload(); }, 800);
    } else {
      if (window.showToast) window.showToast(d.error || 'Failed to add section', 'error');
    }
  });
}

// ── Remove section buttons ────────────────────────────
document.querySelectorAll('.page-section').forEach(function(sec) {
  if (sec.classList.contains('page-section--locked')) return;

  var removeBtn = document.createElement('button');
  removeBtn.className = 'section-remove-btn';
  removeBtn.title = 'Remove section';
  removeBtn.innerHTML = '&times;';
  removeBtn.addEventListener('click', function(e) {
    e.stopPropagation();
    if (!confirm('Remove this section from the page?')) return;
    var sectionId = sec.dataset.sectionId;
    fetch('/admin/api/remove-section', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ page: PAGE_NAME, section_id: sectionId })
    }).then(function(r) { return r.json(); }).then(function(d) {
      if (d.ok) {
        sec.remove();
        if (window.showToast) window.showToast('Section removed');
      } else {
        if (window.showToast) window.showToast(d.error || 'Failed', 'error');
      }
    });
  });
  sec.appendChild(removeBtn);
});

})();
