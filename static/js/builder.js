/* ══════════════════════════════════════════════════════
   INBXR — GrapesJS Page Builder
   ══════════════════════════════════════════════════════ */
'use strict';

var PAGE_NAME = document.body.dataset.page;

var editor = grapesjs.init({
  container: '#gjs',
  height: '100%',
  width: 'auto',
  fromElement: false,
  storageManager: false,
  canvas: {
    styles: [
      'https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap',
      '/static/css/style.css'
    ]
  },
  assetManager: {
    upload: '/admin/api/upload-image',
    uploadName: 'file',
    multiUpload: false,
    autoAdd: true,
  },
  deviceManager: {
    devices: [
      { name: 'Desktop', width: '' },
      { name: 'Tablet', width: '768px', widthMedia: '992px' },
      { name: 'Mobile', width: '375px', widthMedia: '480px' },
    ]
  },
  styleManager: {
    sectors: [
      {
        name: 'Typography',
        open: true,
        properties: [
          'font-family', 'font-size', 'font-weight', 'letter-spacing',
          'color', 'line-height', 'text-align', 'text-decoration', 'text-transform',
        ],
      },
      { name: 'Spacing', properties: ['padding', 'margin'] },
      { name: 'Background', properties: ['background-color', 'background-image', 'background-repeat', 'background-position', 'background-size'] },
      { name: 'Border', properties: ['border-radius', 'border', 'box-shadow'] },
      { name: 'Layout', properties: ['display', 'width', 'max-width', 'height', 'min-height', 'flex-direction', 'justify-content', 'align-items', 'gap', 'overflow'] },
    ],
  },
});

// ── Configure panels ─────────────────────────────────
// Add switcher buttons for right sidebar views
var pn = editor.Panels;

// Remove default panels we don't need
pn.removePanel('devices-c');

// Add view buttons to the options panel
pn.addButton('options', { id: 'undo', className: 'fa fa-undo', command: 'core:undo', attributes: { title: 'Undo' } });
pn.addButton('options', { id: 'redo', className: 'fa fa-repeat', command: 'core:redo', attributes: { title: 'Redo' } });
pn.addButton('options', { id: 'clear-canvas', className: 'fa fa-trash', command: 'core:canvas-clear', attributes: { title: 'Clear canvas' } });
pn.addButton('options', { id: 'preview', className: 'fa fa-eye', command: 'core:preview', attributes: { title: 'Preview' } });
pn.addButton('options', { id: 'fullscreen', className: 'fa fa-arrows-alt', command: 'core:fullscreen', attributes: { title: 'Fullscreen' } });

// Device buttons
pn.addButton('options', {
  id: 'device-desktop',
  className: 'fa fa-desktop',
  command: { run: function(e) { e.setDevice('Desktop'); } },
  active: true,
  attributes: { title: 'Desktop' }
});
pn.addButton('options', {
  id: 'device-tablet',
  className: 'fa fa-tablet',
  command: { run: function(e) { e.setDevice('Tablet'); } },
  attributes: { title: 'Tablet' }
});
pn.addButton('options', {
  id: 'device-mobile',
  className: 'fa fa-mobile',
  command: { run: function(e) { e.setDevice('Mobile'); } },
  attributes: { title: 'Mobile' }
});


// ── Open blocks panel by default ─────────────────────
editor.on('load', function() {
  var openBl = pn.getButton('views', 'open-blocks');
  if (openBl) openBl.set('active', true);
});


// ── Handle asset upload response ─────────────────────
editor.on('asset:upload:response', function(response) {
  if (response && response.ok && response.url) {
    editor.AssetManager.add({ src: response.url });
  }
});


// ── Register Basic Blocks ───────────────────────────
var bm = editor.BlockManager;

bm.add('basic-section', {
  label: 'Section',
  category: 'Basic',
  content: '<section style="padding:48px 24px;"><div style="max-width:960px;margin:0 auto;">Insert content here</div></section>',
  media: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="4" width="20" height="16" rx="2"/></svg>',
});

bm.add('basic-columns', {
  label: '2 Columns',
  category: 'Basic',
  content: '<div style="display:flex;gap:24px;padding:24px;"><div style="flex:1;min-height:60px;">Column 1</div><div style="flex:1;min-height:60px;">Column 2</div></div>',
  media: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="4" width="9" height="16" rx="1"/><rect x="13" y="4" width="9" height="16" rx="1"/></svg>',
});

bm.add('basic-3col', {
  label: '3 Columns',
  category: 'Basic',
  content: '<div style="display:flex;gap:24px;padding:24px;"><div style="flex:1;min-height:60px;">Col 1</div><div style="flex:1;min-height:60px;">Col 2</div><div style="flex:1;min-height:60px;">Col 3</div></div>',
  media: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="1" y="4" width="6" height="16" rx="1"/><rect x="9" y="4" width="6" height="16" rx="1"/><rect x="17" y="4" width="6" height="16" rx="1"/></svg>',
});

bm.add('basic-text', {
  label: 'Text',
  category: 'Basic',
  content: '<p style="font-size:1rem;line-height:1.6;">Edit this text block.</p>',
  media: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 7V4h16v3"/><line x1="12" y1="4" x2="12" y2="20"/><line x1="8" y1="20" x2="16" y2="20"/></svg>',
});

bm.add('basic-heading', {
  label: 'Heading',
  category: 'Basic',
  content: '<h2 style="font-size:1.8rem;font-weight:800;">Your Heading</h2>',
  media: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 12h16"/><path d="M4 4v16"/><path d="M20 4v16"/></svg>',
});

bm.add('basic-image', {
  label: 'Image',
  category: 'Basic',
  content: { type: 'image' },
  media: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/></svg>',
});

bm.add('basic-link', {
  label: 'Link',
  category: 'Basic',
  content: '<a href="#" style="color:#2563eb;">Link text</a>',
  media: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71"/></svg>',
});

bm.add('basic-divider', {
  label: 'Divider',
  category: 'Basic',
  content: '<hr style="border:none;border-top:1px solid rgba(255,255,255,0.1);margin:24px 0;" />',
  media: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><line x1="2" y1="12" x2="22" y2="12"/></svg>',
});

bm.add('basic-spacer', {
  label: 'Spacer',
  category: 'Basic',
  content: '<div style="height:48px;"></div>',
  media: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><line x1="12" y1="4" x2="12" y2="20"/><polyline points="8 8 12 4 16 8"/><polyline points="8 16 12 20 16 16"/></svg>',
});


// ── Register INBXR Custom Blocks ─────────────────────

bm.add('inbxr-hero', {
  label: 'Hero Section',
  category: 'INBXR',
  content: '<div style="padding:48px 24px;text-align:center;">' +
    '<div style="max-width:720px;margin:0 auto;">' +
      '<span style="font-size:0.72rem;text-transform:uppercase;letter-spacing:2px;color:#2563eb;font-weight:600;">YOUR EYEBROW TEXT</span>' +
      '<h1 style="font-size:2.6rem;font-weight:800;margin:12px 0;">Your Main Headline Here</h1>' +
      '<p style="font-size:1.1rem;opacity:0.8;">Supporting subtitle text goes here.</p>' +
      '<a href="#" style="display:inline-block;padding:16px 36px;background:#22c55e;color:#fff;border-radius:999px;font-weight:700;text-decoration:none;margin-top:20px;">Call to Action</a>' +
    '</div>' +
  '</div>',
  media: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="4" width="20" height="16" rx="2"/><line x1="6" y1="9" x2="18" y2="9"/><line x1="8" y1="13" x2="16" y2="13"/></svg>',
});

bm.add('inbxr-checks-grid', {
  label: 'Feature Grid',
  category: 'INBXR',
  content: '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px 40px;max-width:600px;margin:20px auto;text-align:left;">' +
    '<div style="display:flex;align-items:flex-start;gap:8px;"><span style="color:#2563eb;font-weight:700;">&#10003;</span><div><strong>Feature Title</strong><br/><span style="opacity:0.6;font-size:0.82rem;">Feature description here</span></div></div>' +
    '<div style="display:flex;align-items:flex-start;gap:8px;"><span style="color:#2563eb;font-weight:700;">&#10003;</span><div><strong>Feature Title</strong><br/><span style="opacity:0.6;font-size:0.82rem;">Feature description here</span></div></div>' +
    '<div style="display:flex;align-items:flex-start;gap:8px;"><span style="color:#2563eb;font-weight:700;">&#10003;</span><div><strong>Feature Title</strong><br/><span style="opacity:0.6;font-size:0.82rem;">Feature description here</span></div></div>' +
    '<div style="display:flex;align-items:flex-start;gap:8px;"><span style="color:#2563eb;font-weight:700;">&#10003;</span><div><strong>Feature Title</strong><br/><span style="opacity:0.6;font-size:0.82rem;">Feature description here</span></div></div>' +
  '</div>',
  media: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/></svg>',
});

bm.add('inbxr-cta-button', {
  label: 'CTA Button',
  category: 'INBXR',
  content: '<div style="text-align:center;padding:20px;">' +
    '<a href="#" style="display:inline-block;padding:16px 36px;background:#22c55e;color:#fff;border-radius:999px;font-weight:700;font-size:1.05rem;text-decoration:none;box-shadow:0 4px 20px rgba(22,163,74,0.35);">Call to Action</a>' +
  '</div>',
  media: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="8" width="18" height="8" rx="4"/><line x1="8" y1="12" x2="16" y2="12"/></svg>',
});

bm.add('inbxr-value-strip', {
  label: 'Value Strip',
  category: 'INBXR',
  content: '<section style="padding:64px 24px;text-align:center;">' +
    '<div style="display:flex;gap:32px;max-width:960px;margin:0 auto;flex-wrap:wrap;justify-content:center;">' +
      '<div style="flex:1;min-width:240px;"><div style="font-size:2rem;margin-bottom:8px;">&#128737;</div><h3 style="font-size:1.05rem;font-weight:700;margin-bottom:6px;">Value Title</h3><p style="font-size:0.88rem;opacity:0.7;">Description goes here.</p></div>' +
      '<div style="flex:1;min-width:240px;"><div style="font-size:2rem;margin-bottom:8px;">&#127919;</div><h3 style="font-size:1.05rem;font-weight:700;margin-bottom:6px;">Value Title</h3><p style="font-size:0.88rem;opacity:0.7;">Description goes here.</p></div>' +
      '<div style="flex:1;min-width:240px;"><div style="font-size:2rem;margin-bottom:8px;">&#128196;</div><h3 style="font-size:1.05rem;font-weight:700;margin-bottom:6px;">Value Title</h3><p style="font-size:0.88rem;opacity:0.7;">Description goes here.</p></div>' +
    '</div>' +
  '</section>',
  media: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="1" y="5" width="6" height="14" rx="1"/><rect x="9" y="5" width="6" height="14" rx="1"/><rect x="17" y="5" width="6" height="14" rx="1"/></svg>',
});

bm.add('inbxr-how-steps', {
  label: 'How It Works',
  category: 'INBXR',
  content: '<section style="padding:64px 24px;text-align:center;">' +
    '<div style="max-width:720px;margin:0 auto;">' +
      '<h2 style="font-size:1.6rem;font-weight:800;margin-bottom:32px;">How It Works</h2>' +
      '<div style="display:flex;flex-direction:column;gap:24px;text-align:left;">' +
        '<div style="display:flex;gap:16px;align-items:flex-start;"><span style="background:rgba(37,99,235,0.15);color:#2563eb;width:36px;height:36px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;font-weight:800;flex-shrink:0;">1</span><div><h3 style="font-weight:700;margin-bottom:4px;">Step Title</h3><p style="opacity:0.7;font-size:0.9rem;">Step description.</p></div></div>' +
        '<div style="display:flex;gap:16px;align-items:flex-start;"><span style="background:rgba(37,99,235,0.15);color:#2563eb;width:36px;height:36px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;font-weight:800;flex-shrink:0;">2</span><div><h3 style="font-weight:700;margin-bottom:4px;">Step Title</h3><p style="opacity:0.7;font-size:0.9rem;">Step description.</p></div></div>' +
        '<div style="display:flex;gap:16px;align-items:flex-start;"><span style="background:rgba(37,99,235,0.15);color:#2563eb;width:36px;height:36px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;font-weight:800;flex-shrink:0;">3</span><div><h3 style="font-weight:700;margin-bottom:4px;">Step Title</h3><p style="opacity:0.7;font-size:0.9rem;">Step description.</p></div></div>' +
      '</div>' +
    '</div>' +
  '</section>',
  media: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="5" r="3"/><circle cx="12" cy="12" r="3"/><circle cx="12" cy="19" r="3"/></svg>',
});

bm.add('inbxr-comparison', {
  label: 'Comparison',
  category: 'INBXR',
  content: '<section style="padding:64px 24px;text-align:center;">' +
    '<h2 style="font-size:1.6rem;font-weight:800;margin-bottom:32px;">Why Choose Us?</h2>' +
    '<div style="max-width:720px;margin:0 auto;overflow-x:auto;">' +
      '<table style="width:100%;border-collapse:collapse;text-align:left;">' +
        '<thead><tr style="border-bottom:2px solid rgba(255,255,255,0.1);"><th style="padding:12px 16px;">Feature</th><th style="padding:12px 16px;color:#2563eb;font-weight:700;">INBXR</th><th style="padding:12px 16px;opacity:0.6;">Others</th></tr></thead>' +
        '<tbody>' +
          '<tr style="border-bottom:1px solid rgba(255,255,255,0.06);"><td style="padding:12px 16px;">Feature 1</td><td style="padding:12px 16px;color:#2563eb;">&#10003;</td><td style="padding:12px 16px;opacity:0.4;">&times;</td></tr>' +
          '<tr style="border-bottom:1px solid rgba(255,255,255,0.06);"><td style="padding:12px 16px;">Feature 2</td><td style="padding:12px 16px;color:#2563eb;">&#10003;</td><td style="padding:12px 16px;opacity:0.4;">&times;</td></tr>' +
          '<tr><td style="padding:12px 16px;font-weight:700;">Price</td><td style="padding:12px 16px;color:#2563eb;font-weight:700;">Free</td><td style="padding:12px 16px;opacity:0.6;">$99/mo</td></tr>' +
        '</tbody>' +
      '</table>' +
    '</div>' +
  '</section>',
  media: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="9" y1="3" x2="9" y2="21"/></svg>',
});

bm.add('inbxr-social-proof', {
  label: 'Social Proof',
  category: 'INBXR',
  content: '<div style="display:flex;align-items:center;justify-content:center;gap:20px;padding:16px 24px;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);border-radius:12px;max-width:500px;margin:20px auto;">' +
    '<div style="text-align:center;"><strong style="display:block;font-size:0.88rem;">10,000+</strong><span style="font-size:0.68rem;opacity:0.5;">users</span></div>' +
    '<div style="width:1px;height:28px;background:rgba(255,255,255,0.1);"></div>' +
    '<div style="text-align:center;"><strong style="display:block;font-size:0.88rem;">Free</strong><span style="font-size:0.68rem;opacity:0.5;">forever</span></div>' +
  '</div>',
  media: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/></svg>',
});

bm.add('inbxr-final-cta', {
  label: 'Final CTA',
  category: 'INBXR',
  content: '<section style="padding:80px 24px;text-align:center;background:linear-gradient(180deg,rgba(37,99,235,0.08),transparent);">' +
    '<h2 style="font-size:1.8rem;font-weight:800;margin-bottom:8px;">Ready to get started?</h2>' +
    '<p style="opacity:0.7;margin-bottom:24px;">Your subtitle with urgency goes here.</p>' +
    '<a href="#" style="display:inline-block;padding:16px 40px;background:#22c55e;color:#fff;border-radius:999px;font-weight:700;text-decoration:none;box-shadow:0 4px 16px rgba(22,163,74,0.35);">Take Action Now</a>' +
    '<p style="margin-top:12px;font-size:0.78rem;opacity:0.45;">No signup required.</p>' +
  '</section>',
  media: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>',
});

bm.add('inbxr-footer', {
  label: 'Footer',
  category: 'INBXR',
  content: '<footer style="padding:32px 24px;text-align:center;border-top:1px solid rgba(255,255,255,0.06);">' +
    '<p style="font-size:0.78rem;opacity:0.5;">INBXR &mdash; Free email intelligence.</p>' +
  '</footer>',
  media: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="4" width="20" height="16" rx="2"/><line x1="2" y1="16" x2="22" y2="16"/></svg>',
});


// ── Load page content ────────────────────────────────
fetch('/admin/api/builder-load/' + PAGE_NAME)
  .then(function(r) { return r.json(); })
  .then(function(d) {
    if (d.ok) {
      editor.setComponents(d.html || '');
      if (d.css) editor.setStyle(d.css);
    }
  })
  .catch(function(err) {
    console.error('Failed to load page:', err);
  });


// ── Save button ──────────────────────────────────────
document.getElementById('saveBtn').addEventListener('click', function() {
  var btn = this;
  btn.disabled = true;
  btn.textContent = 'Saving\u2026';

  var html = editor.getHtml();
  var css = editor.getCss({ avoidProtected: true });

  fetch('/admin/api/builder-save/' + PAGE_NAME, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ html: html, css: css })
  })
  .then(function(r) { return r.json(); })
  .then(function(d) {
    btn.disabled = false;
    if (d.ok) {
      btn.textContent = 'Saved!';
      setTimeout(function() { btn.textContent = 'Save Page'; }, 1500);
    } else {
      btn.textContent = 'Save Failed';
      setTimeout(function() { btn.textContent = 'Save Page'; }, 2000);
    }
  })
  .catch(function() {
    btn.disabled = false;
    btn.textContent = 'Save Failed';
    setTimeout(function() { btn.textContent = 'Save Page'; }, 2000);
  });
});


// ── Clear / Reset button ─────────────────────────────
document.getElementById('clearBtn').addEventListener('click', function() {
  if (!confirm('Reset to default section-based layout? This removes all builder changes.')) return;
  var btn = this;
  btn.disabled = true;

  fetch('/admin/api/builder-clear/' + PAGE_NAME, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' }
  })
  .then(function(r) { return r.json(); })
  .then(function(d) {
    btn.disabled = false;
    if (d.ok) window.location.reload();
  })
  .catch(function() { btn.disabled = false; });
});
