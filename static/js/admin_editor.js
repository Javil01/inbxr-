/* ══════════════════════════════════════════════════════
   INBXR — Admin Page Editor
   Drag-and-drop reordering + inline editing
   Explicit Save / Undo (no auto-save)
   ══════════════════════════════════════════════════════ */

'use strict';

const PAGE_NAME = document.body.dataset.page || 'index';

// ── State ────────────────────────────────────────────────
let snapshot = {};   // last-saved state
let dirty = false;   // any unsaved changes?

function captureSnapshot() {
  const sections = document.querySelectorAll('.page-section');
  const order = [...sections].map(s => s.dataset.sectionId);
  const texts = {};
  document.querySelectorAll('.page-section [contenteditable="true"]').forEach(el => {
    const sec = el.closest('.page-section');
    if (!sec) return;
    const key = sec.dataset.sectionId + '::' + el.dataset.field +
      (el.dataset.chipIndex !== undefined ? '::' + el.dataset.chipIndex : '');
    texts[key] = el.innerText;
  });
  const visibility = {};
  sections.forEach(s => {
    visibility[s.dataset.sectionId] = !s.classList.contains('page-section--hidden');
  });
  return { order, texts, visibility };
}

function hasChanges() {
  const current = captureSnapshot();
  return JSON.stringify(current) !== JSON.stringify(snapshot);
}

function updateDirtyState() {
  dirty = hasChanges();
  const bar = document.getElementById('admin-save-bar');
  if (!bar) return;
  const undoBtn = document.getElementById('admin-undo-btn');
  const label = bar.querySelector('.admin-save-bar__label');
  if (dirty) {
    bar.classList.add('admin-save-bar--dirty');
    if (undoBtn) undoBtn.style.display = '';
    if (label) label.textContent = 'Unsaved changes';
  } else {
    bar.classList.remove('admin-save-bar--dirty');
    if (undoBtn) undoBtn.style.display = 'none';
    if (label) label.textContent = 'No pending changes';
  }
}

// ── Toast notification ───────────────────────────────────
function showToast(msg, type = 'success') {
  const existing = document.querySelector('.admin-toast');
  if (existing) existing.remove();

  const el = document.createElement('div');
  el.className = `admin-toast admin-toast--${type}`;
  el.textContent = msg;
  document.body.appendChild(el);
  requestAnimationFrame(() => el.classList.add('admin-toast--visible'));
  setTimeout(() => {
    el.classList.remove('admin-toast--visible');
    setTimeout(() => el.remove(), 200);
  }, 2000);
}

// ── Save bar UI ──────────────────────────────────────────
function createSaveBar() {
  const bar = document.createElement('div');
  bar.id = 'admin-save-bar';
  bar.className = 'admin-save-bar';
  bar.innerHTML =
    '<span class="admin-save-bar__label">No pending changes</span>' +
    '<button class="admin-save-bar__btn admin-save-bar__btn--undo" id="admin-undo-btn" style="display:none">Undo</button>' +
    '<button class="admin-save-bar__btn admin-save-bar__btn--save" id="admin-save-btn">Save</button>';
  document.body.appendChild(bar);

  document.getElementById('admin-save-btn').addEventListener('click', saveAll);
  document.getElementById('admin-undo-btn').addEventListener('click', undoAll);
}

// ── Helper: POST JSON and return parsed body ─────────────
async function postJSON(url, payload) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  const data = await res.json();
  if (!res.ok || !data.ok) {
    throw new Error(data.error || 'Server returned an error');
  }
  return data;
}

// ── Save all pending changes ─────────────────────────────
async function saveAll() {
  const btn = document.getElementById('admin-save-btn');
  btn.disabled = true;
  btn.textContent = 'Saving…';

  const current = captureSnapshot();
  const requests = [];

  // 1) Order
  if (JSON.stringify(current.order) !== JSON.stringify(snapshot.order)) {
    requests.push(
      postJSON('/admin/api/reorder', { page: PAGE_NAME, order: current.order })
    );
  }

  // 2) Text edits
  for (const key in current.texts) {
    if (current.texts[key] !== snapshot.texts[key]) {
      const parts = key.split('::');
      const sectionId = parts[0];
      const field = parts[1];
      const chipIndex = parts[2];

      if (chipIndex !== undefined) {
        requests.push(
          postJSON('/admin/api/update-chip', {
            page: PAGE_NAME,
            section_id: sectionId,
            field: field,
            index: parseInt(chipIndex),
            value: current.texts[key]
          })
        );
      } else {
        requests.push(
          postJSON('/admin/api/update-content', {
            page: PAGE_NAME,
            section_id: sectionId,
            field: field,
            value: current.texts[key]
          })
        );
      }
    }
  }

  // 3) Visibility
  for (const id in current.visibility) {
    if (current.visibility[id] !== snapshot.visibility[id]) {
      requests.push(
        postJSON('/admin/api/toggle-visibility', {
          page: PAGE_NAME,
          section_id: id,
          visible: current.visibility[id]
        })
      );
    }
  }

  if (requests.length === 0) {
    showToast('No changes to save');
    btn.disabled = false;
    btn.textContent = 'Save';
    return;
  }

  try {
    await Promise.all(requests);
    snapshot = captureSnapshot();
    updateDirtyState();
    showToast(requests.length + ' change' + (requests.length > 1 ? 's' : '') + ' saved');
  } catch (err) {
    showToast('Save failed: ' + err.message, 'error');
    console.error('Admin save error:', err);
  }

  btn.disabled = false;
  btn.textContent = 'Save';
}

// ── Undo all unsaved changes ─────────────────────────────
function undoAll() {
  // Restore text
  document.querySelectorAll('.page-section [contenteditable="true"]').forEach(el => {
    const sec = el.closest('.page-section');
    if (!sec) return;
    const key = sec.dataset.sectionId + '::' + el.dataset.field +
      (el.dataset.chipIndex !== undefined ? '::' + el.dataset.chipIndex : '');
    if (key in snapshot.texts) {
      el.innerText = snapshot.texts[key];
    }
  });

  // Restore visibility
  document.querySelectorAll('.page-section').forEach(sec => {
    const id = sec.dataset.sectionId;
    if (id in snapshot.visibility) {
      sec.classList.toggle('page-section--hidden', !snapshot.visibility[id]);
    }
  });

  // Restore order
  const container = document.getElementById('page-sections');
  if (container) {
    const currentEls = [...container.querySelectorAll('.page-section')];
    const elMap = {};
    currentEls.forEach(el => { elMap[el.dataset.sectionId] = el; });
    snapshot.order.forEach(id => {
      if (elMap[id]) container.appendChild(elMap[id]);
    });
  }

  updateDirtyState();
  showToast('Changes undone');
}

// ── SortableJS initialization ────────────────────────────
const container = document.getElementById('page-sections');

if (container && typeof Sortable !== 'undefined') {
  Sortable.create(container, {
    handle: '.section-drag-handle',
    animation: 180,
    ghostClass: 'sortable-ghost',
    chosenClass: 'sortable-chosen',
    dragClass: 'sortable-drag',
    filter: '.page-section--locked',
    onEnd: function () {
      updateDirtyState();
    }
  });
}

// ── Inline text editing ──────────────────────────────────
document.querySelectorAll('.page-section [contenteditable="true"]').forEach(el => {
  el.addEventListener('focus', function () {
    this._original = this.innerText;
    this.classList.add('admin-editing');
  });

  el.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      this.innerText = this._original;
      this.blur();
    }
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      this.blur();
    }
  });

  el.addEventListener('blur', function () {
    this.classList.remove('admin-editing');
    updateDirtyState();
  });
});

// ── Section visibility toggle ────────────────────────────
document.querySelectorAll('.section-visibility-btn').forEach(btn => {
  btn.addEventListener('click', function () {
    const section = this.closest('.page-section');
    section.classList.toggle('page-section--hidden');
    updateDirtyState();
  });
});

// ── Universal text editing ───────────────────────────────
// Make ALL visible text elements in page sections editable
document.querySelectorAll('.page-section').forEach(sec => {
  sec.querySelectorAll('h1, h2, h3, h4, h5, h6, p, span, a, li, strong, td, th, label').forEach(el => {
    if (el.getAttribute('contenteditable')) return;
    if (el.closest('input, textarea, select, .asp, .admin-toolbar, .admin-save-bar')) return;
    if (el.children.length > 2) return;

    var text = el.textContent.trim();
    if (!text || text.length < 2) return;

    el.setAttribute('contenteditable', 'true');
    if (!el.dataset.field) {
      el.dataset.field = '_auto_' + el.tagName.toLowerCase() + '_' + Math.random().toString(36).substr(2, 6);
    }

    el.addEventListener('focus', function() {
      this._original = this.innerText;
      this.classList.add('admin-editing');
    });

    el.addEventListener('keydown', function(e) {
      if (e.key === 'Escape') {
        this.innerText = this._original;
        this.blur();
      }
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        this.blur();
      }
    });

    el.addEventListener('blur', function() {
      this.classList.remove('admin-editing');
      if (this.innerText !== this._original) {
        var section = this.closest('.page-section');
        if (!section) return;
        var tag = this.tagName.toLowerCase();
        var cls = this.className ? '.' + this.className.trim().split(/\s+/)[0] : '';
        var selector = tag + cls;

        postJSON('/admin/api/update-inline', {
          page: PAGE_NAME,
          section_id: section.dataset.sectionId,
          selector: selector,
          value: this.innerText
        }).then(() => {
          showToast('Text saved');
        }).catch(() => {
          showToast('Text save failed', 'error');
        });
      }
      updateDirtyState();
    });
  });
});

// Expose showToast globally for other admin scripts
window.showToast = showToast;

// ── Init ─────────────────────────────────────────────────
createSaveBar();
snapshot = captureSnapshot();
