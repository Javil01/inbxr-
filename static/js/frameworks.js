/* ══════════════════════════════════════════════════════
   INBXR — Framework Lab Frontend
   ══════════════════════════════════════════════════════ */

'use strict';

const $ = (sel, ctx = document) => ctx.querySelector(sel);
const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

const _esc = s => {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
};

const CATEGORY_LABELS = {
  master: 'INBXR Method',
  foundational: 'Foundational',
  value_logic: 'Value & Logic',
  story_transformation: 'Story',
  trust_proof: 'Trust & Proof',
  refinement: 'Refinement',
  niche: 'Niche',
};

let _allFrameworks = [];
let _myFrameworks = [];
let _activeCategory = 'all';
let _editingId = null;

// ── Init ─────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  await loadFrameworks();
  loadDecisionTree();
  initTabs();
  initModal();
  initBuilder();

  const tier = window.__userTier || 'free';
  const isPaid = ['pro', 'agency', 'api'].includes(tier);

  if (isPaid && window.__userId) {
    await loadMyFrameworks();
    $('#fwMySection').style.display = '';
    $('#fwUpsell').style.display = 'none';
  } else {
    $('#fwMySection').style.display = 'none';
    $('#fwUpsell').style.display = '';
  }
});


// ── Load frameworks ──────────────────────────────────
async function loadFrameworks() {
  try {
    const res = await fetch('/api/frameworks');
    _allFrameworks = await res.json();
    renderGrid(_allFrameworks);
  } catch (e) {
    console.error('Failed to load frameworks', e);
  }
}

async function loadMyFrameworks() {
  try {
    const res = await fetch('/api/my-frameworks');
    if (res.ok) {
      _myFrameworks = await res.json();
      renderMyGrid();
    }
  } catch (e) {
    console.error('Failed to load my frameworks', e);
  }
}


// ── Grid rendering ───────────────────────────────────
function renderGrid(frameworks) {
  const grid = $('#fwGrid');
  if (!frameworks.length) {
    grid.innerHTML = '<p class="fw-empty">No frameworks found.</p>';
    return;
  }
  grid.innerHTML = frameworks.map(fw => `
    <div class="fw-card ${fw.locked ? 'fw-card--locked' : ''}" data-slug="${_esc(fw.slug)}" data-category="${_esc(fw.category)}">
      <div class="fw-card__top">
        <span class="fw-card__acronym">${_esc(fw.acronym)}</span>
        <span class="fw-card__pill">${_esc(CATEGORY_LABELS[fw.category] || fw.category)}</span>
      </div>
      <h3 class="fw-card__name">${_esc(fw.name)}</h3>
      <p class="fw-card__desc">${_esc(fw.description)}</p>
      ${fw.locked ? '<span class="fw-card__lock">Pro</span>' : ''}
    </div>
  `).join('');

  // Click handlers
  $$('.fw-card', grid).forEach(card => {
    card.addEventListener('click', () => openModal(card.dataset.slug));
  });
}

function renderMyGrid() {
  const grid = $('#fwMyGrid');
  if (!_myFrameworks.length) {
    grid.innerHTML = '<p class="fw-empty">No custom frameworks yet. Create your first one!</p>';
    return;
  }
  grid.innerHTML = _myFrameworks.map(fw => `
    <div class="fw-card fw-card--custom" data-id="${fw.id}">
      <div class="fw-card__top">
        <span class="fw-card__acronym fw-card__acronym--custom">${_esc(_makeAcronym(fw.steps))}</span>
        <span class="fw-card__pill fw-card__pill--custom">Custom</span>
      </div>
      <h3 class="fw-card__name">${_esc(fw.name)}</h3>
      <p class="fw-card__desc">${_esc(fw.steps.map(s => s.label).join(' → '))}</p>
      <div class="fw-card__actions">
        <button class="fw-card__edit" data-id="${fw.id}">Edit</button>
        <button class="fw-card__delete" data-id="${fw.id}">Delete</button>
      </div>
    </div>
  `).join('');

  // Handlers
  $$('.fw-card__edit', grid).forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      editMyFramework(parseInt(btn.dataset.id));
    });
  });
  $$('.fw-card__delete', grid).forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      deleteMyFramework(parseInt(btn.dataset.id));
    });
  });
}

function _makeAcronym(steps) {
  return steps.map(s => (s.key || s.label || '?')[0]).join('').toUpperCase().slice(0, 5);
}


// ── Tabs ─────────────────────────────────────────────
function initTabs() {
  $$('.fw-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      $$('.fw-tab').forEach(t => t.classList.remove('fw-tab--active'));
      tab.classList.add('fw-tab--active');
      _activeCategory = tab.dataset.category;
      filterGrid();
    });
  });
}

function filterGrid() {
  const filtered = _activeCategory === 'all'
    ? _allFrameworks
    : _allFrameworks.filter(fw => fw.category === _activeCategory);
  renderGrid(filtered);
}


// ── Decision Tree ────────────────────────────────────
async function loadDecisionTree() {
  try {
    const res = await fetch('/api/frameworks/decision-tree');
    const tree = await res.json();
    renderDecisionTree(tree);
  } catch (e) {
    console.error('Failed to load decision tree', e);
  }
}

function renderDecisionTree(tree) {
  $('#fwDecisionQuestion').textContent = tree.question;
  const optContainer = $('#fwDecisionOptions');
  optContainer.innerHTML = tree.options.map((opt, i) => `
    <button class="fw-decision__opt" data-index="${i}">
      <strong>${_esc(opt.label)}</strong>
      <span>${_esc(opt.description)}</span>
    </button>
  `).join('');

  $$('.fw-decision__opt', optContainer).forEach(btn => {
    btn.addEventListener('click', () => {
      const idx = parseInt(btn.dataset.index);
      const opt = tree.options[idx];
      showDecisionResult(opt.frameworks);
    });
  });

  $('#fwDecisionReset').addEventListener('click', () => {
    $('#fwDecisionResult').style.display = 'none';
    optContainer.style.display = '';
  });
}

function showDecisionResult(slugs) {
  const recs = _allFrameworks.filter(fw => slugs.includes(fw.slug));
  const container = $('#fwDecisionRecs');
  container.innerHTML = recs.map(fw => `
    <div class="fw-decision__rec" data-slug="${_esc(fw.slug)}">
      <span class="fw-card__acronym">${_esc(fw.acronym)}</span>
      <div>
        <strong>${_esc(fw.name)}</strong>
        <p>${_esc(fw.description)}</p>
      </div>
    </div>
  `).join('');

  $$('.fw-decision__rec', container).forEach(rec => {
    rec.addEventListener('click', () => openModal(rec.dataset.slug));
  });

  $('#fwDecisionOptions').style.display = 'none';
  $('#fwDecisionResult').style.display = '';
}


// ── Detail Modal ─────────────────────────────────────
function initModal() {
  $('#fwModalClose').addEventListener('click', closeModal);
  $('#fwModalOverlay').addEventListener('click', e => {
    if (e.target === $('#fwModalOverlay')) closeModal();
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
      closeModal();
      closeBuilder();
    }
  });
}

function openModal(slug) {
  const fw = _allFrameworks.find(f => f.slug === slug);
  if (!fw) return;

  const tier = window.__userTier || 'free';
  const isPaid = ['pro', 'agency', 'api'].includes(tier);

  $('#fwModalAcronym').textContent = fw.acronym;
  $('#fwModalName').textContent = fw.name;
  $('#fwModalCategory').textContent = CATEGORY_LABELS[fw.category] || fw.category;
  $('#fwModalDesc').textContent = fw.description;

  // Steps
  const stepsEl = $('#fwModalSteps');
  const lockedEl = $('#fwModalLocked');
  if (fw.locked) {
    stepsEl.innerHTML = fw.steps.map(s => `
      <div class="fw-step fw-step--locked">
        <span class="fw-step__key">${_esc(s.key)}</span>
        <span class="fw-step__label">${_esc(s.label)}</span>
        <span class="fw-step__desc">&#x2022;&#x2022;&#x2022;&#x2022;&#x2022;</span>
      </div>
    `).join('');
    lockedEl.style.display = '';
  } else {
    stepsEl.innerHTML = fw.steps.map(s => `
      <div class="fw-step">
        <span class="fw-step__key">${_esc(s.key)}</span>
        <span class="fw-step__label">${_esc(s.label)}</span>
        <span class="fw-step__desc">${_esc(s.description)}</span>
      </div>
    `).join('');
    lockedEl.style.display = 'none';
  }

  // When to use
  const whenSection = $('#fwModalWhenSection');
  if (fw.when_to_use) {
    $('#fwModalWhen').textContent = fw.when_to_use;
    whenSection.style.display = '';
  } else { whenSection.style.display = 'none'; }

  // Deliverability notes
  const delivSection = $('#fwModalDelivSection');
  if (fw.deliverability_notes) {
    $('#fwModalDeliv').textContent = fw.deliverability_notes;
    delivSection.style.display = '';
  } else { delivSection.style.display = 'none'; }

  // Example
  const exSection = $('#fwModalExampleSection');
  if (fw.example_output) {
    $('#fwModalExample').textContent = fw.example_output;
    exSection.style.display = '';
  } else { exSection.style.display = 'none'; }

  // Fork button (paid only, not for locked)
  const forkBtn = $('#fwModalFork');
  if (isPaid && !fw.locked) {
    forkBtn.style.display = '';
    forkBtn.onclick = () => {
      closeModal();
      openBuilder(null, fw);
    };
  } else { forkBtn.style.display = 'none'; }

  // Apply to Rewriter link
  const applyBtn = $('#fwModalApply');
  if (!fw.locked) {
    applyBtn.href = '/?framework=' + encodeURIComponent(fw.slug);
    applyBtn.style.display = '';
  } else { applyBtn.style.display = 'none'; }

  $('#fwModalOverlay').style.display = 'flex';
  document.body.style.overflow = 'hidden';
}

function closeModal() {
  $('#fwModalOverlay').style.display = 'none';
  document.body.style.overflow = '';
}


// ── Custom Builder ───────────────────────────────────
function initBuilder() {
  $('#fwCreateBtn')?.addEventListener('click', () => openBuilder());
  $('#fwBuilderClose').addEventListener('click', closeBuilder);
  $('#fwBuilderCancel').addEventListener('click', closeBuilder);
  $('#fwBuilderOverlay').addEventListener('click', e => {
    if (e.target === $('#fwBuilderOverlay')) closeBuilder();
  });
  $('#fwBuilderAddStep').addEventListener('click', addBuilderStep);
  $('#fwBuilderForm').addEventListener('submit', saveBuilder);
}

function openBuilder(editFw = null, baseFw = null) {
  _editingId = editFw ? editFw.id : null;
  $('#fwBuilderTitle').textContent = editFw ? 'Edit Framework' : 'Create Custom Framework';
  $('#fwBuilderName').value = editFw ? editFw.name : (baseFw ? baseFw.name + ' (Custom)' : '');
  $('#fwBuilderNotes').value = editFw ? (editFw.notes || '') : '';
  $('#fwBuilderId').value = editFw ? editFw.id : '';
  $('#fwBuilderBaseId').value = baseFw ? baseFw.id : '';

  const stepsContainer = $('#fwBuilderSteps');
  stepsContainer.innerHTML = '';

  const steps = editFw ? editFw.steps : (baseFw ? baseFw.steps : []);
  if (steps.length) {
    steps.forEach(s => addBuilderStep(null, s));
  } else {
    addBuilderStep();
  }

  $('#fwBuilderOverlay').style.display = 'flex';
  document.body.style.overflow = 'hidden';
}

function closeBuilder() {
  $('#fwBuilderOverlay').style.display = 'none';
  document.body.style.overflow = '';
  _editingId = null;
}

function addBuilderStep(e, data = null) {
  if (e) e.preventDefault();
  const container = $('#fwBuilderSteps');
  const count = container.children.length;
  if (count >= 10) return;

  const step = document.createElement('div');
  step.className = 'fw-builder__step';
  step.draggable = true;
  step.innerHTML = `
    <span class="fw-builder__drag">&#x2630;</span>
    <input type="text" class="fw-builder__step-key" placeholder="Key (e.g. A)" maxlength="5" value="${_esc(data?.key || '')}" required />
    <input type="text" class="fw-builder__step-label" placeholder="Label (e.g. Attention)" maxlength="50" value="${_esc(data?.label || '')}" required />
    <input type="text" class="fw-builder__step-desc" placeholder="Description..." maxlength="200" value="${_esc(data?.description || '')}" />
    <button type="button" class="fw-builder__step-remove">&times;</button>
  `;

  step.querySelector('.fw-builder__step-remove').addEventListener('click', () => {
    if (container.children.length > 1) step.remove();
  });

  // Drag reorder
  step.addEventListener('dragstart', e => {
    e.dataTransfer.effectAllowed = 'move';
    step.classList.add('fw-builder__step--dragging');
  });
  step.addEventListener('dragend', () => step.classList.remove('fw-builder__step--dragging'));
  step.addEventListener('dragover', e => {
    e.preventDefault();
    const dragging = $('.fw-builder__step--dragging', container);
    if (dragging && dragging !== step) {
      const rect = step.getBoundingClientRect();
      const mid = rect.top + rect.height / 2;
      if (e.clientY < mid) {
        container.insertBefore(dragging, step);
      } else {
        container.insertBefore(dragging, step.nextSibling);
      }
    }
  });

  container.appendChild(step);
}

async function saveBuilder(e) {
  e.preventDefault();

  const name = $('#fwBuilderName').value.trim();
  const notes = $('#fwBuilderNotes').value.trim();
  const baseId = $('#fwBuilderBaseId').value || null;

  const steps = [];
  $$('.fw-builder__step', $('#fwBuilderSteps')).forEach(el => {
    const key = el.querySelector('.fw-builder__step-key').value.trim();
    const label = el.querySelector('.fw-builder__step-label').value.trim();
    const desc = el.querySelector('.fw-builder__step-desc').value.trim();
    if (key && label) steps.push({ key, label, description: desc });
  });

  if (!name) { showToast('Name is required', 'error'); return; }
  if (!steps.length) { showToast('Add at least one step', 'error'); return; }

  const saveBtn = $('#fwBuilderSave');
  saveBtn.disabled = true;
  saveBtn.textContent = 'Saving...';

  try {
    const url = _editingId ? `/api/my-frameworks/${_editingId}` : '/api/my-frameworks';
    const method = _editingId ? 'PUT' : 'POST';
    const res = await fetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, steps, notes, base_framework_id: baseId ? parseInt(baseId) : null }),
    });
    const data = await res.json();

    if (!res.ok) {
      showToast(data.error || 'Failed to save', 'error');
      return;
    }

    closeBuilder();
    await loadMyFrameworks();
    showToast(_editingId ? 'Framework updated!' : 'Framework created!', 'success');
  } catch (err) {
    showToast('Network error', 'error');
  } finally {
    saveBtn.disabled = false;
    saveBtn.textContent = 'Save Framework';
  }
}

function editMyFramework(id) {
  const fw = _myFrameworks.find(f => f.id === id);
  if (fw) openBuilder(fw);
}

async function deleteMyFramework(id) {
  if (!confirm('Delete this framework? This cannot be undone.')) return;
  try {
    const res = await fetch(`/api/my-frameworks/${id}`, { method: 'DELETE' });
    if (res.ok) {
      await loadMyFrameworks();
      showToast('Framework deleted', 'success');
    } else {
      const data = await res.json();
      showToast(data.error || 'Failed to delete', 'error');
    }
  } catch (err) {
    showToast('Network error', 'error');
  }
}


// ── Toast helper ─────────────────────────────────────
function showToast(msg, type) {
  if (window.showToast) window.showToast(msg, type);
}
