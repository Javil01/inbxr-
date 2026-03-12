/* ══════════════════════════════════════════════════════
   INBXR — Visual Style Editor Panel
   Right sidebar for editing CSS properties on selected elements
   ══════════════════════════════════════════════════════ */
'use strict';

(function() {

var selectedEl = null;
var panel = null;
var styleMode = false;

var PAGE_NAME = document.body.dataset.page || 'index';

// ── Build panel HTML ──────────────────────────────────
function createPanel() {
  panel = document.createElement('div');
  panel.id = 'admin-style-panel';
  panel.className = 'asp';
  panel.innerHTML =
    '<div class="asp__header">' +
      '<span class="asp__title">Style Editor</span>' +
      '<button class="asp__close" onclick="window._aspClose()">&times;</button>' +
    '</div>' +
    '<div class="asp__body">' +
      '<div class="asp__section">' +
        '<div class="asp__label">Element</div>' +
        '<div id="aspElInfo" class="asp__info">—</div>' +
      '</div>' +

      '<div class="asp__section">' +
        '<div class="asp__label">Typography</div>' +
        '<div class="asp__row">' +
          '<label class="asp__field"><span>Size</span><input type="text" id="aspFontSize" placeholder="e.g. 1.2rem" /></label>' +
          '<label class="asp__field"><span>Weight</span><select id="aspFontWeight"><option value="">—</option><option>300</option><option>400</option><option>500</option><option>600</option><option>700</option><option>800</option></select></label>' +
        '</div>' +
        '<div class="asp__row">' +
          '<label class="asp__field"><span>Color</span><div class="asp__color-wrap"><input type="color" id="aspColor" /><input type="text" id="aspColorText" placeholder="#fff" /></div></label>' +
          '<label class="asp__field"><span>Line Height</span><input type="text" id="aspLineHeight" placeholder="1.4" /></label>' +
        '</div>' +
        '<div class="asp__row">' +
          '<label class="asp__field"><span>Align</span>' +
            '<div class="asp__align-btns">' +
              '<button data-align="left" title="Left">&#9776;</button>' +
              '<button data-align="center" title="Center">&#9776;</button>' +
              '<button data-align="right" title="Right">&#9776;</button>' +
            '</div>' +
          '</label>' +
          '<label class="asp__field"><span>Letter Spacing</span><input type="text" id="aspLetterSpacing" placeholder="0" /></label>' +
        '</div>' +
      '</div>' +

      '<div class="asp__section">' +
        '<div class="asp__label">Spacing</div>' +
        '<div class="asp__row">' +
          '<label class="asp__field"><span>Padding</span><input type="text" id="aspPadding" placeholder="16px" /></label>' +
          '<label class="asp__field"><span>Margin</span><input type="text" id="aspMargin" placeholder="0" /></label>' +
        '</div>' +
      '</div>' +

      '<div class="asp__section">' +
        '<div class="asp__label">Background</div>' +
        '<div class="asp__row">' +
          '<label class="asp__field"><span>BG Color</span><div class="asp__color-wrap"><input type="color" id="aspBgColor" /><input type="text" id="aspBgColorText" placeholder="transparent" /></div></label>' +
          '<label class="asp__field"><span>Radius</span><input type="text" id="aspBorderRadius" placeholder="8px" /></label>' +
        '</div>' +
      '</div>' +

      '<div class="asp__section">' +
        '<div class="asp__label">Border</div>' +
        '<div class="asp__row">' +
          '<label class="asp__field"><span>Border</span><input type="text" id="aspBorder" placeholder="1px solid #ccc" /></label>' +
        '</div>' +
      '</div>' +

      '<div class="asp__section">' +
        '<div class="asp__label">Size</div>' +
        '<div class="asp__row">' +
          '<label class="asp__field"><span>Width</span><input type="text" id="aspWidth" placeholder="auto" /></label>' +
          '<label class="asp__field"><span>Max Width</span><input type="text" id="aspMaxWidth" placeholder="none" /></label>' +
        '</div>' +
      '</div>' +

      '<div class="asp__section">' +
        '<button class="asp__apply-btn" id="aspApplyBtn">Apply &amp; Save Styles</button>' +
      '</div>' +
    '</div>';

  document.body.appendChild(panel);

  // Wire up color sync
  var colorPicker = document.getElementById('aspColor');
  var colorText = document.getElementById('aspColorText');
  colorPicker.addEventListener('input', function() { colorText.value = this.value; applyLive(); });
  colorText.addEventListener('change', function() { colorPicker.value = this.value; applyLive(); });

  var bgPicker = document.getElementById('aspBgColor');
  var bgText = document.getElementById('aspBgColorText');
  bgPicker.addEventListener('input', function() { bgText.value = this.value; applyLive(); });
  bgText.addEventListener('change', function() { bgPicker.value = this.value; applyLive(); });

  // Wire up all inputs for live preview
  panel.querySelectorAll('input[type="text"], select').forEach(function(inp) {
    inp.addEventListener('change', applyLive);
  });

  // Align buttons
  panel.querySelectorAll('[data-align]').forEach(function(btn) {
    btn.addEventListener('click', function() {
      if (selectedEl) {
        selectedEl.style.textAlign = this.dataset.align;
      }
    });
  });

  // Apply & Save
  document.getElementById('aspApplyBtn').addEventListener('click', saveStyles);
}

function applyLive() {
  if (!selectedEl) return;
  var s = selectedEl.style;
  var v;

  v = document.getElementById('aspFontSize').value.trim();
  if (v) s.fontSize = v;

  v = document.getElementById('aspFontWeight').value;
  if (v) s.fontWeight = v;

  v = document.getElementById('aspColorText').value.trim();
  if (v) s.color = v;

  v = document.getElementById('aspLineHeight').value.trim();
  if (v) s.lineHeight = v;

  v = document.getElementById('aspLetterSpacing').value.trim();
  if (v) s.letterSpacing = v;

  v = document.getElementById('aspPadding').value.trim();
  if (v) s.padding = v;

  v = document.getElementById('aspMargin').value.trim();
  if (v) s.margin = v;

  v = document.getElementById('aspBgColorText').value.trim();
  if (v) s.background = v;

  v = document.getElementById('aspBorderRadius').value.trim();
  if (v) s.borderRadius = v;

  v = document.getElementById('aspBorder').value.trim();
  if (v) s.border = v;

  v = document.getElementById('aspWidth').value.trim();
  if (v) s.width = v;

  v = document.getElementById('aspMaxWidth').value.trim();
  if (v) s.maxWidth = v;
}

function populatePanel(el) {
  var cs = getComputedStyle(el);
  document.getElementById('aspElInfo').textContent = el.tagName.toLowerCase() + (el.className ? '.' + el.className.split(' ')[0] : '');
  document.getElementById('aspFontSize').value = cs.fontSize;
  document.getElementById('aspFontWeight').value = cs.fontWeight;
  document.getElementById('aspLineHeight').value = cs.lineHeight;
  document.getElementById('aspLetterSpacing').value = cs.letterSpacing === 'normal' ? '' : cs.letterSpacing;
  document.getElementById('aspPadding').value = cs.padding;
  document.getElementById('aspMargin').value = cs.margin;
  document.getElementById('aspBorderRadius').value = cs.borderRadius === '0px' ? '' : cs.borderRadius;
  document.getElementById('aspBorder').value = cs.border === 'none' ? '' : '';
  document.getElementById('aspWidth').value = '';
  document.getElementById('aspMaxWidth').value = cs.maxWidth === 'none' ? '' : cs.maxWidth;

  // Colors
  try {
    document.getElementById('aspColorText').value = rgbToHex(cs.color);
    document.getElementById('aspColor').value = rgbToHex(cs.color);
  } catch(e) {}
  try {
    document.getElementById('aspBgColorText').value = cs.backgroundColor === 'rgba(0, 0, 0, 0)' ? '' : rgbToHex(cs.backgroundColor);
    document.getElementById('aspBgColor').value = cs.backgroundColor === 'rgba(0, 0, 0, 0)' ? '#000000' : rgbToHex(cs.backgroundColor);
  } catch(e) {}
}

function rgbToHex(rgb) {
  if (!rgb || rgb === 'transparent') return '';
  if (rgb.startsWith('#')) return rgb;
  var parts = rgb.match(/\d+/g);
  if (!parts || parts.length < 3) return '';
  return '#' + parts.slice(0,3).map(function(n) { return parseInt(n).toString(16).padStart(2,'0'); }).join('');
}

function getElementSelector(el) {
  // Generate a selector relative to its section
  var section = el.closest('.page-section');
  if (!section) return '';
  var tag = el.tagName.toLowerCase();
  var cls = el.className ? '.' + el.className.trim().split(/\s+/)[0] : '';
  return tag + cls;
}

function saveStyles() {
  if (!selectedEl) return;
  var section = selectedEl.closest('.page-section');
  if (!section) return;

  var styles = {};
  var fields = {
    'font-size': 'aspFontSize', 'font-weight': 'aspFontWeight', 'color': 'aspColorText',
    'line-height': 'aspLineHeight', 'letter-spacing': 'aspLetterSpacing',
    'padding': 'aspPadding', 'margin': 'aspMargin',
    'background': 'aspBgColorText', 'border-radius': 'aspBorderRadius',
    'border': 'aspBorder', 'width': 'aspWidth', 'max-width': 'aspMaxWidth'
  };
  for (var prop in fields) {
    var v = document.getElementById(fields[prop]).value.trim();
    if (v) styles[prop] = v;
  }

  var selector = getElementSelector(selectedEl);
  fetch('/admin/api/update-styles', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      page: PAGE_NAME,
      section_id: section.dataset.sectionId,
      selector: selector,
      styles: styles
    })
  }).then(function(r) { return r.json(); }).then(function(d) {
    if (d.ok && window.showToast) window.showToast('Styles saved');
    else if (window.showToast) window.showToast('Save failed', 'error');
  });
}

// ── Style mode toggle ────────────────────────────────
function enableStyleMode() {
  styleMode = true;
  document.body.classList.add('admin-style-mode');
  if (!panel) createPanel();
  panel.classList.add('asp--open');
}

function disableStyleMode() {
  styleMode = false;
  document.body.classList.remove('admin-style-mode');
  if (panel) panel.classList.remove('asp--open');
  deselectEl();
}

function selectEl(el) {
  deselectEl();
  selectedEl = el;
  el.classList.add('asp-selected');
  populatePanel(el);
}

function deselectEl() {
  if (selectedEl) {
    selectedEl.classList.remove('asp-selected');
    selectedEl = null;
  }
}

// ── Click handler for style selection ─────────────────
document.addEventListener('click', function(e) {
  if (!styleMode) return;
  if (panel && panel.contains(e.target)) return;
  if (e.target.closest('.admin-toolbar') || e.target.closest('.admin-save-bar')) return;

  var el = e.target.closest('h1, h2, h3, h4, h5, h6, p, span, a, button, div, section, img, li, strong, td, th, label, footer');
  if (!el || !el.closest('.page-section')) return;

  e.preventDefault();
  e.stopPropagation();
  selectEl(el);
}, true);

// ── Add style toggle to admin toolbar ─────────────────
var toolbar = document.querySelector('.admin-toolbar');
if (toolbar) {
  var sep = document.createElement('span');
  sep.className = 'admin-toolbar__sep';
  toolbar.appendChild(sep);

  var btn = document.createElement('button');
  btn.textContent = 'Style Editor';
  btn.className = 'admin-toolbar__style-btn';
  btn.style.cssText = 'background:none;border:1px solid rgba(255,255,255,0.2);color:#c7d2fe;padding:4px 12px;border-radius:6px;font-size:0.75rem;font-weight:600;cursor:pointer;';
  btn.addEventListener('click', function() {
    if (styleMode) disableStyleMode();
    else enableStyleMode();
    this.classList.toggle('active');
  });
  toolbar.appendChild(btn);
}

// Expose close function
window._aspClose = function() { disableStyleMode(); };

})();
