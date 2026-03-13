/* ══════════════════════════════════════════════════════
   INBXR — Enhanced GrapesJS Page Builder
   ══════════════════════════════════════════════════════ */
'use strict';

var PAGE_NAME = document.body.dataset.page;

// ── GrapesJS Init ────────────────────────────────────
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
    upload: '/admin/api/media/upload',
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
var pn = editor.Panels;
pn.removePanel('devices-c');
pn.addButton('options', { id: 'undo', className: 'fa fa-undo', command: 'core:undo', attributes: { title: 'Undo' } });
pn.addButton('options', { id: 'redo', className: 'fa fa-repeat', command: 'core:redo', attributes: { title: 'Redo' } });
pn.addButton('options', { id: 'clear-canvas', className: 'fa fa-trash', command: 'core:canvas-clear', attributes: { title: 'Clear canvas' } });
pn.addButton('options', { id: 'preview', className: 'fa fa-eye', command: 'core:preview', attributes: { title: 'Preview' } });
pn.addButton('options', { id: 'fullscreen', className: 'fa fa-arrows-alt', command: 'core:fullscreen', attributes: { title: 'Fullscreen' } });
pn.addButton('options', {
  id: 'device-desktop', className: 'fa fa-desktop',
  command: { run: function(e) { e.setDevice('Desktop'); } }, active: true,
  attributes: { title: 'Desktop' }
});
pn.addButton('options', {
  id: 'device-tablet', className: 'fa fa-tablet',
  command: { run: function(e) { e.setDevice('Tablet'); } },
  attributes: { title: 'Tablet' }
});
pn.addButton('options', {
  id: 'device-mobile', className: 'fa fa-mobile',
  command: { run: function(e) { e.setDevice('Mobile'); } },
  attributes: { title: 'Mobile' }
});

editor.on('load', function() {
  var openBl = pn.getButton('views', 'open-blocks');
  if (openBl) openBl.set('active', true);
});

editor.on('asset:upload:response', function(response) {
  if (response && response.ok && response.url) {
    editor.AssetManager.add({ src: response.url });
  }
});


// ══════════════════════════════════════════════════════
//  BLOCK REGISTRATION
// ══════════════════════════════════════════════════════

var bm = editor.BlockManager;

// ── Basic Blocks ─────────────────────────────────────
bm.add('basic-section', {
  label: 'Section', category: 'Basic',
  content: '<section style="padding:48px 24px;"><div style="max-width:960px;margin:0 auto;">Insert content here</div></section>',
  media: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="4" width="20" height="16" rx="2"/></svg>',
});

bm.add('basic-columns', {
  label: '2 Columns', category: 'Basic',
  content: '<div style="display:flex;gap:24px;padding:24px;"><div style="flex:1;min-height:60px;">Column 1</div><div style="flex:1;min-height:60px;">Column 2</div></div>',
  media: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="4" width="9" height="16" rx="1"/><rect x="13" y="4" width="9" height="16" rx="1"/></svg>',
});

bm.add('basic-3col', {
  label: '3 Columns', category: 'Basic',
  content: '<div style="display:flex;gap:24px;padding:24px;"><div style="flex:1;min-height:60px;">Col 1</div><div style="flex:1;min-height:60px;">Col 2</div><div style="flex:1;min-height:60px;">Col 3</div></div>',
  media: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="1" y="4" width="6" height="16" rx="1"/><rect x="9" y="4" width="6" height="16" rx="1"/><rect x="17" y="4" width="6" height="16" rx="1"/></svg>',
});

bm.add('basic-text', {
  label: 'Text', category: 'Basic',
  content: '<p style="font-size:1rem;line-height:1.6;">Edit this text block.</p>',
  media: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 7V4h16v3"/><line x1="12" y1="4" x2="12" y2="20"/><line x1="8" y1="20" x2="16" y2="20"/></svg>',
});

bm.add('basic-heading', {
  label: 'Heading', category: 'Basic',
  content: '<h2 style="font-size:1.8rem;font-weight:800;">Your Heading</h2>',
  media: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 12h16"/><path d="M4 4v16"/><path d="M20 4v16"/></svg>',
});

bm.add('basic-image', {
  label: 'Image', category: 'Basic',
  content: { type: 'image' },
  media: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/></svg>',
});

bm.add('basic-link', {
  label: 'Link', category: 'Basic',
  content: '<a href="#" style="color:#2563eb;">Link text</a>',
  media: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71"/></svg>',
});

bm.add('basic-divider', {
  label: 'Divider', category: 'Basic',
  content: '<hr style="border:none;border-top:1px solid rgba(255,255,255,0.1);margin:24px 0;" />',
  media: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><line x1="2" y1="12" x2="22" y2="12"/></svg>',
});

bm.add('basic-spacer', {
  label: 'Spacer', category: 'Basic',
  content: '<div style="height:48px;"></div>',
  media: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><line x1="12" y1="4" x2="12" y2="20"/><polyline points="8 8 12 4 16 8"/><polyline points="8 16 12 20 16 16"/></svg>',
});

bm.add('basic-video', {
  label: 'Video', category: 'Basic',
  content: '<div style="padding:24px;text-align:center;"><video controls style="max-width:100%;border-radius:8px;"><source src="" type="video/mp4" />Your browser does not support video.</video></div>',
  media: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><polygon points="5 3 19 12 5 21 5 3"/></svg>',
});

bm.add('basic-map', {
  label: 'Map Embed', category: 'Basic',
  content: '<div style="padding:24px;"><iframe src="https://www.google.com/maps/embed?pb=!1m18!1m12" width="100%" height="300" style="border:0;border-radius:8px;" allowfullscreen="" loading="lazy"></iframe></div>',
  media: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z"/><circle cx="12" cy="10" r="3"/></svg>',
});


// ── INBXR Blocks ─────────────────────────────────────
bm.add('inbxr-hero', {
  label: 'Hero Section', category: 'INBXR',
  content: '<div style="padding:48px 24px;text-align:center;"><div style="max-width:720px;margin:0 auto;"><span style="font-size:0.72rem;text-transform:uppercase;letter-spacing:2px;color:#2563eb;font-weight:600;">YOUR EYEBROW TEXT</span><h1 style="font-size:2.6rem;font-weight:800;margin:12px 0;">Your Main Headline Here</h1><p style="font-size:1.1rem;opacity:0.8;">Supporting subtitle text goes here.</p><a href="#" style="display:inline-block;padding:16px 36px;background:#22c55e;color:#fff;border-radius:999px;font-weight:700;text-decoration:none;margin-top:20px;">Call to Action</a></div></div>',
  media: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="4" width="20" height="16" rx="2"/><line x1="6" y1="9" x2="18" y2="9"/><line x1="8" y1="13" x2="16" y2="13"/></svg>',
});

bm.add('inbxr-checks-grid', {
  label: 'Feature Grid', category: 'INBXR',
  content: '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px 40px;max-width:600px;margin:20px auto;text-align:left;"><div style="display:flex;align-items:flex-start;gap:8px;"><span style="color:#2563eb;font-weight:700;">&#10003;</span><div><strong>Feature Title</strong><br/><span style="opacity:0.6;font-size:0.82rem;">Feature description here</span></div></div><div style="display:flex;align-items:flex-start;gap:8px;"><span style="color:#2563eb;font-weight:700;">&#10003;</span><div><strong>Feature Title</strong><br/><span style="opacity:0.6;font-size:0.82rem;">Feature description here</span></div></div><div style="display:flex;align-items:flex-start;gap:8px;"><span style="color:#2563eb;font-weight:700;">&#10003;</span><div><strong>Feature Title</strong><br/><span style="opacity:0.6;font-size:0.82rem;">Feature description here</span></div></div><div style="display:flex;align-items:flex-start;gap:8px;"><span style="color:#2563eb;font-weight:700;">&#10003;</span><div><strong>Feature Title</strong><br/><span style="opacity:0.6;font-size:0.82rem;">Feature description here</span></div></div></div>',
  media: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/></svg>',
});

bm.add('inbxr-cta-button', {
  label: 'CTA Button', category: 'INBXR',
  content: '<div style="text-align:center;padding:20px;"><a href="#" style="display:inline-block;padding:16px 36px;background:#22c55e;color:#fff;border-radius:999px;font-weight:700;font-size:1.05rem;text-decoration:none;box-shadow:0 4px 20px rgba(22,163,74,0.35);">Call to Action</a></div>',
  media: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="8" width="18" height="8" rx="4"/><line x1="8" y1="12" x2="16" y2="12"/></svg>',
});

bm.add('inbxr-value-strip', {
  label: 'Value Strip', category: 'INBXR',
  content: '<section style="padding:64px 24px;text-align:center;"><div style="display:flex;gap:32px;max-width:960px;margin:0 auto;flex-wrap:wrap;justify-content:center;"><div style="flex:1;min-width:240px;"><div style="font-size:2rem;margin-bottom:8px;">&#128737;</div><h3 style="font-size:1.05rem;font-weight:700;margin-bottom:6px;">Value Title</h3><p style="font-size:0.88rem;opacity:0.7;">Description goes here.</p></div><div style="flex:1;min-width:240px;"><div style="font-size:2rem;margin-bottom:8px;">&#127919;</div><h3 style="font-size:1.05rem;font-weight:700;margin-bottom:6px;">Value Title</h3><p style="font-size:0.88rem;opacity:0.7;">Description goes here.</p></div><div style="flex:1;min-width:240px;"><div style="font-size:2rem;margin-bottom:8px;">&#128196;</div><h3 style="font-size:1.05rem;font-weight:700;margin-bottom:6px;">Value Title</h3><p style="font-size:0.88rem;opacity:0.7;">Description goes here.</p></div></div></section>',
  media: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="1" y="5" width="6" height="14" rx="1"/><rect x="9" y="5" width="6" height="14" rx="1"/><rect x="17" y="5" width="6" height="14" rx="1"/></svg>',
});

bm.add('inbxr-how-steps', {
  label: 'How It Works', category: 'INBXR',
  content: '<section style="padding:64px 24px;text-align:center;"><div style="max-width:720px;margin:0 auto;"><h2 style="font-size:1.6rem;font-weight:800;margin-bottom:32px;">How It Works</h2><div style="display:flex;flex-direction:column;gap:24px;text-align:left;"><div style="display:flex;gap:16px;align-items:flex-start;"><span style="background:rgba(37,99,235,0.15);color:#2563eb;width:36px;height:36px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;font-weight:800;flex-shrink:0;">1</span><div><h3 style="font-weight:700;margin-bottom:4px;">Step Title</h3><p style="opacity:0.7;font-size:0.9rem;">Step description.</p></div></div><div style="display:flex;gap:16px;align-items:flex-start;"><span style="background:rgba(37,99,235,0.15);color:#2563eb;width:36px;height:36px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;font-weight:800;flex-shrink:0;">2</span><div><h3 style="font-weight:700;margin-bottom:4px;">Step Title</h3><p style="opacity:0.7;font-size:0.9rem;">Step description.</p></div></div><div style="display:flex;gap:16px;align-items:flex-start;"><span style="background:rgba(37,99,235,0.15);color:#2563eb;width:36px;height:36px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;font-weight:800;flex-shrink:0;">3</span><div><h3 style="font-weight:700;margin-bottom:4px;">Step Title</h3><p style="opacity:0.7;font-size:0.9rem;">Step description.</p></div></div></div></div></section>',
  media: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="5" r="3"/><circle cx="12" cy="12" r="3"/><circle cx="12" cy="19" r="3"/></svg>',
});

bm.add('inbxr-comparison', {
  label: 'Comparison', category: 'INBXR',
  content: '<section style="padding:64px 24px;text-align:center;"><h2 style="font-size:1.6rem;font-weight:800;margin-bottom:32px;">Why Choose Us?</h2><div style="max-width:720px;margin:0 auto;overflow-x:auto;"><table style="width:100%;border-collapse:collapse;text-align:left;"><thead><tr style="border-bottom:2px solid rgba(255,255,255,0.1);"><th style="padding:12px 16px;">Feature</th><th style="padding:12px 16px;color:#2563eb;font-weight:700;">INBXR</th><th style="padding:12px 16px;opacity:0.6;">Others</th></tr></thead><tbody><tr style="border-bottom:1px solid rgba(255,255,255,0.06);"><td style="padding:12px 16px;">Feature 1</td><td style="padding:12px 16px;color:#2563eb;">&#10003;</td><td style="padding:12px 16px;opacity:0.4;">&times;</td></tr><tr style="border-bottom:1px solid rgba(255,255,255,0.06);"><td style="padding:12px 16px;">Feature 2</td><td style="padding:12px 16px;color:#2563eb;">&#10003;</td><td style="padding:12px 16px;opacity:0.4;">&times;</td></tr><tr><td style="padding:12px 16px;font-weight:700;">Price</td><td style="padding:12px 16px;color:#2563eb;font-weight:700;">Free</td><td style="padding:12px 16px;opacity:0.6;">$99/mo</td></tr></tbody></table></div></section>',
  media: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="9" y1="3" x2="9" y2="21"/></svg>',
});

bm.add('inbxr-social-proof', {
  label: 'Social Proof', category: 'INBXR',
  content: '<div style="display:flex;align-items:center;justify-content:center;gap:20px;padding:16px 24px;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);border-radius:12px;max-width:500px;margin:20px auto;"><div style="text-align:center;"><strong style="display:block;font-size:0.88rem;">10,000+</strong><span style="font-size:0.68rem;opacity:0.5;">users</span></div><div style="width:1px;height:28px;background:rgba(255,255,255,0.1);"></div><div style="text-align:center;"><strong style="display:block;font-size:0.88rem;">Free</strong><span style="font-size:0.68rem;opacity:0.5;">forever</span></div></div>',
  media: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/></svg>',
});

bm.add('inbxr-final-cta', {
  label: 'Final CTA', category: 'INBXR',
  content: '<section style="padding:80px 24px;text-align:center;background:linear-gradient(180deg,rgba(37,99,235,0.08),transparent);"><h2 style="font-size:1.8rem;font-weight:800;margin-bottom:8px;">Ready to get started?</h2><p style="opacity:0.7;margin-bottom:24px;">Your subtitle with urgency goes here.</p><a href="#" style="display:inline-block;padding:16px 40px;background:#22c55e;color:#fff;border-radius:999px;font-weight:700;text-decoration:none;box-shadow:0 4px 16px rgba(22,163,74,0.35);">Take Action Now</a><p style="margin-top:12px;font-size:0.78rem;opacity:0.45;">No signup required.</p></section>',
  media: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>',
});

bm.add('inbxr-footer', {
  label: 'Footer', category: 'INBXR',
  content: '<footer style="padding:32px 24px;text-align:center;border-top:1px solid rgba(255,255,255,0.06);"><p style="font-size:0.78rem;opacity:0.5;">INBXR &mdash; Free email intelligence.</p></footer>',
  media: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="4" width="20" height="16" rx="2"/><line x1="2" y1="16" x2="22" y2="16"/></svg>',
});


// ── NEW: Advanced Blocks ─────────────────────────────

bm.add('adv-contact-form', {
  label: 'Contact Form', category: 'Forms & CTAs',
  content: '<section style="padding:64px 24px;"><div style="max-width:520px;margin:0 auto;"><h2 style="font-size:1.4rem;font-weight:800;margin-bottom:24px;text-align:center;">Get in Touch</h2><form style="display:flex;flex-direction:column;gap:14px;"><input type="text" placeholder="Your Name" style="padding:12px 16px;background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.1);border-radius:8px;color:#dbeafe;font-size:0.9rem;" /><input type="email" placeholder="Your Email" style="padding:12px 16px;background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.1);border-radius:8px;color:#dbeafe;font-size:0.9rem;" /><textarea placeholder="Your Message" rows="4" style="padding:12px 16px;background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.1);border-radius:8px;color:#dbeafe;font-size:0.9rem;resize:vertical;"></textarea><button type="submit" style="padding:14px 28px;background:#2563eb;color:#fff;border:none;border-radius:999px;font-weight:700;font-size:0.95rem;cursor:pointer;">Send Message</button></form></div></section>',
  media: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>',
});

bm.add('adv-email-signup', {
  label: 'Email Signup', category: 'Forms & CTAs',
  content: '<section style="padding:48px 24px;text-align:center;"><div style="max-width:480px;margin:0 auto;"><h3 style="font-size:1.2rem;font-weight:700;margin-bottom:8px;">Stay Updated</h3><p style="font-size:0.88rem;opacity:0.7;margin-bottom:16px;">Get the latest tips straight to your inbox.</p><div style="display:flex;gap:8px;"><input type="email" placeholder="your@email.com" style="flex:1;padding:12px 16px;background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.1);border-radius:999px;color:#dbeafe;font-size:0.9rem;" /><button style="padding:12px 24px;background:#22c55e;color:#fff;border:none;border-radius:999px;font-weight:700;cursor:pointer;white-space:nowrap;">Subscribe</button></div></div></section>',
  media: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="5" width="18" height="14" rx="2"/><polyline points="3 7 12 13 21 7"/></svg>',
});

bm.add('adv-testimonials', {
  label: 'Testimonials', category: 'Forms & CTAs',
  content: '<section style="padding:64px 24px;"><div style="max-width:960px;margin:0 auto;text-align:center;"><h2 style="font-size:1.6rem;font-weight:800;margin-bottom:32px;">What People Say</h2><div style="display:flex;gap:24px;flex-wrap:wrap;justify-content:center;"><div style="flex:1;min-width:280px;max-width:360px;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);border-radius:12px;padding:24px;text-align:left;"><p style="font-size:0.92rem;line-height:1.6;opacity:0.85;margin-bottom:16px;">"This tool completely changed how we handle email deliverability. Worth every penny."</p><div style="display:flex;align-items:center;gap:10px;"><div style="width:36px;height:36px;border-radius:50%;background:rgba(37,99,235,0.2);display:flex;align-items:center;justify-content:center;font-weight:700;color:#2563eb;">J</div><div><strong style="font-size:0.82rem;">Jane Doe</strong><br/><span style="font-size:0.72rem;opacity:0.5;">Marketing Director</span></div></div></div><div style="flex:1;min-width:280px;max-width:360px;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);border-radius:12px;padding:24px;text-align:left;"><p style="font-size:0.92rem;line-height:1.6;opacity:0.85;margin-bottom:16px;">"We reduced our spam complaint rate by 80% within a month of using INBXR."</p><div style="display:flex;align-items:center;gap:10px;"><div style="width:36px;height:36px;border-radius:50%;background:rgba(34,197,94,0.2);display:flex;align-items:center;justify-content:center;font-weight:700;color:#22c55e;">M</div><div><strong style="font-size:0.82rem;">Mike Smith</strong><br/><span style="font-size:0.72rem;opacity:0.5;">Email Specialist</span></div></div></div></div></div></section>',
  media: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>',
});

bm.add('adv-pricing-table', {
  label: 'Pricing Table', category: 'Forms & CTAs',
  content: '<section style="padding:64px 24px;text-align:center;"><h2 style="font-size:1.6rem;font-weight:800;margin-bottom:32px;">Simple Pricing</h2><div style="display:flex;gap:24px;max-width:900px;margin:0 auto;flex-wrap:wrap;justify-content:center;"><div style="flex:1;min-width:260px;max-width:300px;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);border-radius:16px;padding:32px 24px;"><h3 style="font-size:1rem;font-weight:600;opacity:0.7;">Free</h3><div style="font-size:2.4rem;font-weight:800;margin:12px 0;">$0<span style="font-size:0.8rem;opacity:0.5;">/mo</span></div><ul style="list-style:none;padding:0;margin:20px 0;text-align:left;font-size:0.88rem;"><li style="padding:6px 0;">&#10003; 3 checks/day</li><li style="padding:6px 0;">&#10003; Basic reports</li></ul><a href="#" style="display:block;padding:12px;background:rgba(255,255,255,0.08);color:#dbeafe;border-radius:999px;text-decoration:none;font-weight:600;">Get Started</a></div><div style="flex:1;min-width:260px;max-width:300px;background:rgba(37,99,235,0.08);border:2px solid #2563eb;border-radius:16px;padding:32px 24px;position:relative;"><div style="position:absolute;top:-12px;left:50%;transform:translateX(-50%);background:#2563eb;color:#fff;padding:4px 16px;border-radius:999px;font-size:0.68rem;font-weight:700;">POPULAR</div><h3 style="font-size:1rem;font-weight:600;color:#2563eb;">Pro</h3><div style="font-size:2.4rem;font-weight:800;margin:12px 0;">$29<span style="font-size:0.8rem;opacity:0.5;">/mo</span></div><ul style="list-style:none;padding:0;margin:20px 0;text-align:left;font-size:0.88rem;"><li style="padding:6px 0;">&#10003; Unlimited checks</li><li style="padding:6px 0;">&#10003; AI features</li><li style="padding:6px 0;">&#10003; Priority support</li></ul><a href="#" style="display:block;padding:12px;background:#2563eb;color:#fff;border-radius:999px;text-decoration:none;font-weight:600;">Upgrade Now</a></div></div></section>',
  media: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6"/></svg>',
});

bm.add('adv-faq', {
  label: 'FAQ', category: 'Forms & CTAs',
  content: '<section style="padding:64px 24px;"><div style="max-width:720px;margin:0 auto;"><h2 style="font-size:1.6rem;font-weight:800;margin-bottom:32px;text-align:center;">Frequently Asked Questions</h2><div style="display:flex;flex-direction:column;gap:12px;"><details style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);border-radius:8px;padding:16px 20px;"><summary style="font-weight:600;cursor:pointer;font-size:0.95rem;">How does this work?</summary><p style="margin-top:12px;font-size:0.88rem;opacity:0.7;line-height:1.6;">Answer goes here. Explain the feature or process clearly.</p></details><details style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);border-radius:8px;padding:16px 20px;"><summary style="font-weight:600;cursor:pointer;font-size:0.95rem;">Is it really free?</summary><p style="margin-top:12px;font-size:0.88rem;opacity:0.7;line-height:1.6;">Yes! Our free tier includes generous limits. Upgrade anytime for more.</p></details><details style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);border-radius:8px;padding:16px 20px;"><summary style="font-weight:600;cursor:pointer;font-size:0.95rem;">Can I cancel anytime?</summary><p style="margin-top:12px;font-size:0.88rem;opacity:0.7;line-height:1.6;">Absolutely. No contracts, no cancellation fees.</p></details></div></div></section>',
  media: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
});

bm.add('adv-countdown', {
  label: 'Countdown', category: 'Forms & CTAs',
  content: '<section style="padding:48px 24px;text-align:center;"><h3 style="font-size:1.1rem;font-weight:600;margin-bottom:16px;opacity:0.8;">Offer Ends In</h3><div style="display:flex;gap:16px;justify-content:center;"><div style="background:rgba(255,255,255,0.06);border-radius:12px;padding:16px 20px;min-width:70px;"><div style="font-size:1.8rem;font-weight:800;">07</div><div style="font-size:0.65rem;text-transform:uppercase;opacity:0.5;margin-top:4px;">Days</div></div><div style="background:rgba(255,255,255,0.06);border-radius:12px;padding:16px 20px;min-width:70px;"><div style="font-size:1.8rem;font-weight:800;">12</div><div style="font-size:0.65rem;text-transform:uppercase;opacity:0.5;margin-top:4px;">Hours</div></div><div style="background:rgba(255,255,255,0.06);border-radius:12px;padding:16px 20px;min-width:70px;"><div style="font-size:1.8rem;font-weight:800;">45</div><div style="font-size:0.65rem;text-transform:uppercase;opacity:0.5;margin-top:4px;">Minutes</div></div><div style="background:rgba(255,255,255,0.06);border-radius:12px;padding:16px 20px;min-width:70px;"><div style="font-size:1.8rem;font-weight:800;">30</div><div style="font-size:0.65rem;text-transform:uppercase;opacity:0.5;margin-top:4px;">Seconds</div></div></div></section>',
  media: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>',
});

bm.add('adv-stats-bar', {
  label: 'Stats Bar', category: 'Forms & CTAs',
  content: '<section style="padding:48px 24px;background:rgba(37,99,235,0.06);"><div style="display:flex;gap:32px;max-width:800px;margin:0 auto;flex-wrap:wrap;justify-content:center;text-align:center;"><div style="flex:1;min-width:150px;"><div style="font-size:2rem;font-weight:800;color:#2563eb;">50K+</div><div style="font-size:0.82rem;opacity:0.6;">Emails Analyzed</div></div><div style="flex:1;min-width:150px;"><div style="font-size:2rem;font-weight:800;color:#22c55e;">99.2%</div><div style="font-size:0.82rem;opacity:0.6;">Accuracy Rate</div></div><div style="flex:1;min-width:150px;"><div style="font-size:2rem;font-weight:800;color:#eab308;">2.5s</div><div style="font-size:0.82rem;opacity:0.6;">Avg Analysis Time</div></div></div></section>',
  media: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>',
});

bm.add('adv-logo-strip', {
  label: 'Logo Strip', category: 'Forms & CTAs',
  content: '<section style="padding:32px 24px;text-align:center;"><p style="font-size:0.72rem;text-transform:uppercase;letter-spacing:2px;opacity:0.4;margin-bottom:20px;">Trusted By</p><div style="display:flex;gap:40px;align-items:center;justify-content:center;flex-wrap:wrap;opacity:0.4;"><span style="font-size:1.2rem;font-weight:700;">Company 1</span><span style="font-size:1.2rem;font-weight:700;">Company 2</span><span style="font-size:1.2rem;font-weight:700;">Company 3</span><span style="font-size:1.2rem;font-weight:700;">Company 4</span></div></section>',
  media: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="7" width="20" height="10" rx="2"/><line x1="7" y1="7" x2="7" y2="17"/><line x1="12" y1="7" x2="12" y2="17"/><line x1="17" y1="7" x2="17" y2="17"/></svg>',
});


// ══════════════════════════════════════════════════════
//  LOAD PAGE CONTENT
// ══════════════════════════════════════════════════════

fetch('/admin/api/builder-load/' + PAGE_NAME)
  .then(function(r) { return r.json(); })
  .then(function(d) {
    if (d.ok) {
      editor.setComponents(d.html || '');
      if (d.css) editor.setStyle(d.css);
    }
  })
  .catch(function(err) { console.error('Failed to load page:', err); });

// Check for draft
fetch('/admin/api/builder-load-draft/' + PAGE_NAME)
  .then(function(r) { return r.json(); })
  .then(function(d) {
    if (d.ok && d.draft_data) {
      var status = document.getElementById('draftStatus');
      status.textContent = 'Unsaved Draft';
      status.className = 'bt-status';
      if (confirm('A draft exists (saved ' + (d.updated_at || 'recently') + '). Load it?')) {
        try {
          var dd = JSON.parse(d.draft_data);
          editor.setComponents(dd.html || '');
          if (dd.css) editor.setStyle(dd.css);
        } catch(e) { console.error('Invalid draft data'); }
      }
    }
  });


// ══════════════════════════════════════════════════════
//  SAVE DRAFT
// ══════════════════════════════════════════════════════

document.getElementById('saveDraftBtn').addEventListener('click', function() {
  var btn = this;
  btn.disabled = true;
  btn.textContent = 'Saving\u2026';

  var draftData = JSON.stringify({
    html: editor.getHtml(),
    css: editor.getCss({ avoidProtected: true })
  });

  fetch('/admin/api/builder-save-draft/' + PAGE_NAME, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ draft_data: draftData })
  })
  .then(function(r) { return r.json(); })
  .then(function(d) {
    btn.disabled = false;
    if (d.ok) {
      btn.textContent = 'Draft Saved!';
      var status = document.getElementById('draftStatus');
      status.textContent = 'Draft';
      status.className = 'bt-status';
      setTimeout(function() { btn.textContent = 'Save Draft'; }, 1500);
    } else {
      btn.textContent = 'Save Failed';
      setTimeout(function() { btn.textContent = 'Save Draft'; }, 2000);
    }
  })
  .catch(function() {
    btn.disabled = false;
    btn.textContent = 'Save Failed';
    setTimeout(function() { btn.textContent = 'Save Draft'; }, 2000);
  });
});


// ══════════════════════════════════════════════════════
//  PUBLISH
// ══════════════════════════════════════════════════════

document.getElementById('publishBtn').addEventListener('click', function() {
  var btn = this;
  if (!confirm('Publish this page? The current live version will be saved to history.')) return;
  btn.disabled = true;
  btn.textContent = 'Publishing\u2026';

  // First save as draft, then publish
  var draftData = JSON.stringify({
    html: editor.getHtml(),
    css: editor.getCss({ avoidProtected: true })
  });

  fetch('/admin/api/builder-save-draft/' + PAGE_NAME, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ draft_data: draftData })
  })
  .then(function() {
    return fetch('/admin/api/builder-publish/' + PAGE_NAME, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });
  })
  .then(function(r) { return r.json(); })
  .then(function(d) {
    btn.disabled = false;
    if (d.ok) {
      btn.textContent = 'Published!';
      var status = document.getElementById('draftStatus');
      status.textContent = 'Published';
      status.className = 'bt-status published';
      setTimeout(function() { btn.textContent = 'Publish'; }, 1500);
    } else {
      btn.textContent = 'Publish Failed';
      setTimeout(function() { btn.textContent = 'Publish'; }, 2000);
    }
  })
  .catch(function() {
    btn.disabled = false;
    btn.textContent = 'Publish Failed';
    setTimeout(function() { btn.textContent = 'Publish'; }, 2000);
  });
});


// ══════════════════════════════════════════════════════
//  RESET
// ══════════════════════════════════════════════════════

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


// ══════════════════════════════════════════════════════
//  SIDEBAR PANELS
// ══════════════════════════════════════════════════════

var activePanel = null;

function openPanel(name) {
  var sidebar = document.getElementById('builder-sidebar');
  var panels = sidebar.querySelectorAll('.bs-panel');
  var tabs = document.querySelectorAll('.bt-tab');

  if (activePanel === name) {
    closeSidebar();
    return;
  }

  panels.forEach(function(p) { p.style.display = 'none'; });
  tabs.forEach(function(t) { t.classList.remove('active'); });

  var target = document.getElementById('panel-' + name);
  if (target) {
    target.style.display = 'flex';
    sidebar.classList.remove('bs-hidden');
    activePanel = name;
    // Highlight tab
    var tab = document.querySelector('.bt-tab[data-panel="' + name + '"]');
    if (tab) tab.classList.add('active');
    // Load data for panel
    if (name === 'versions') loadVersions();
    if (name === 'templates') loadTemplates();
    if (name === 'media') loadMedia();
    if (name === 'seo') loadSeo();
    if (name === 'analytics') loadAnalytics();
  }
}

function closeSidebar() {
  document.getElementById('builder-sidebar').classList.add('bs-hidden');
  document.querySelectorAll('.bt-tab').forEach(function(t) { t.classList.remove('active'); });
  activePanel = null;
}

// Tab clicks
document.querySelectorAll('.bt-tab').forEach(function(tab) {
  tab.addEventListener('click', function() {
    var panel = this.dataset.panel;
    if (panel === 'blocks') {
      closeSidebar();
      var openBl = pn.getButton('views', 'open-blocks');
      if (openBl) openBl.set('active', true);
    } else {
      openPanel(panel);
    }
  });
});


// ══════════════════════════════════════════════════════
//  VERSION HISTORY
// ══════════════════════════════════════════════════════

function loadVersions() {
  fetch('/admin/api/builder-versions/' + PAGE_NAME)
    .then(function(r) { return r.json(); })
    .then(function(d) {
      var list = document.getElementById('versionList');
      if (!d.ok || !d.versions.length) {
        list.innerHTML = '<p style="text-align:center;color:#64748b;font-size:0.78rem;padding:20px;">No versions saved yet.</p>';
        return;
      }
      list.innerHTML = d.versions.map(function(v) {
        return '<div class="bs-version-item">' +
          '<div class="bs-item-title">' + (v.label || 'Unnamed') + '</div>' +
          '<div class="bs-item-meta">' + v.created_at + '</div>' +
          '<div class="bs-item-actions">' +
            '<button class="bs-item-btn" onclick="rollbackVersion(' + v.id + ')">Restore</button>' +
          '</div>' +
        '</div>';
      }).join('');
    });
}

function saveVersion() {
  var label = document.getElementById('versionLabel').value.trim() || 'Manual save';
  fetch('/admin/api/builder-save-version/' + PAGE_NAME, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ label: label })
  })
  .then(function(r) { return r.json(); })
  .then(function(d) {
    if (d.ok) {
      document.getElementById('versionLabel').value = '';
      loadVersions();
    }
  });
}

function rollbackVersion(id) {
  if (!confirm('Restore this version? Current content will be saved as a new version first.')) return;
  fetch('/admin/api/builder-rollback/' + PAGE_NAME + '/' + id, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' }
  })
  .then(function(r) { return r.json(); })
  .then(function(d) {
    if (d.ok) window.location.reload();
  });
}


// ══════════════════════════════════════════════════════
//  TEMPLATES
// ══════════════════════════════════════════════════════

function loadTemplates() {
  fetch('/admin/api/templates')
    .then(function(r) { return r.json(); })
    .then(function(d) {
      var list = document.getElementById('templateList');
      if (!d.ok || !d.templates.length) {
        list.innerHTML = '<p style="text-align:center;color:#64748b;font-size:0.78rem;padding:20px;">No templates saved yet.</p>';
        return;
      }
      list.innerHTML = d.templates.map(function(t) {
        return '<div class="bs-template-item">' +
          '<div class="bs-item-title">' + t.name + '</div>' +
          '<div class="bs-item-meta">' + (t.description || '') + ' &middot; ' + t.created_at + '</div>' +
          '<div class="bs-item-actions">' +
            '<button class="bs-item-btn" onclick="loadTemplate(' + t.id + ')">Load</button>' +
            '<button class="bs-item-btn bs-item-btn--danger" onclick="deleteTemplate(' + t.id + ')">Delete</button>' +
          '</div>' +
        '</div>';
      }).join('');
    });
}

function saveAsTemplate() {
  var name = document.getElementById('templateName').value.trim();
  if (!name) { alert('Enter a template name.'); return; }
  var desc = document.getElementById('templateDesc').value.trim();
  var templateData = JSON.stringify({
    html: editor.getHtml(),
    css: editor.getCss({ avoidProtected: true })
  });
  fetch('/admin/api/templates', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: name, description: desc, template_data: templateData })
  })
  .then(function(r) { return r.json(); })
  .then(function(d) {
    if (d.ok) {
      document.getElementById('templateName').value = '';
      document.getElementById('templateDesc').value = '';
      loadTemplates();
    }
  });
}

function loadTemplate(id) {
  if (!confirm('Load this template? Current unsaved changes will be lost.')) return;
  fetch('/admin/api/templates/' + id)
    .then(function(r) { return r.json(); })
    .then(function(d) {
      if (d.ok && d.template) {
        try {
          var td = JSON.parse(d.template.template_data);
          editor.setComponents(td.html || '');
          if (td.css) editor.setStyle(td.css);
        } catch(e) { alert('Invalid template data.'); }
      }
    });
}

function deleteTemplate(id) {
  if (!confirm('Delete this template?')) return;
  fetch('/admin/api/templates/' + id, { method: 'DELETE' })
    .then(function(r) { return r.json(); })
    .then(function(d) { if (d.ok) loadTemplates(); });
}


// ══════════════════════════════════════════════════════
//  MEDIA LIBRARY
// ══════════════════════════════════════════════════════

function loadMedia(query) {
  var url = '/admin/api/media';
  if (query) url += '?q=' + encodeURIComponent(query);
  fetch(url)
    .then(function(r) { return r.json(); })
    .then(function(d) {
      var grid = document.getElementById('mediaGrid');
      if (!d.ok || !d.media.length) {
        grid.innerHTML = '<p style="text-align:center;color:#64748b;font-size:0.78rem;padding:20px;grid-column:1/-1;">No media found.</p>';
        return;
      }
      grid.innerHTML = d.media.map(function(m) {
        return '<div class="bs-media-item" onclick="insertMedia(\'' + m.url + '\')">' +
          '<img src="' + m.url + '" alt="' + (m.alt_text || m.filename) + '" loading="lazy" />' +
          '<div class="bs-media-item-info"><div class="bs-media-item-name">' + m.filename + '</div></div>' +
          '<div class="bs-media-item-actions"><button class="bs-media-item-del" onclick="event.stopPropagation();deleteMedia(' + m.id + ')" title="Delete">&times;</button></div>' +
        '</div>';
      }).join('');
    });
}

var _mediaTimer;
function searchMedia() {
  clearTimeout(_mediaTimer);
  _mediaTimer = setTimeout(function() {
    loadMedia(document.getElementById('mediaSearch').value.trim());
  }, 300);
}

function uploadMedia() {
  var input = document.getElementById('mediaUpload');
  if (!input.files.length) return;
  var fd = new FormData();
  fd.append('file', input.files[0]);
  fetch('/admin/api/media/upload', { method: 'POST', body: fd })
    .then(function(r) { return r.json(); })
    .then(function(d) {
      if (d.ok) {
        loadMedia();
        editor.AssetManager.add({ src: d.url });
      }
    });
  input.value = '';
}

function insertMedia(url) {
  var selected = editor.getSelected();
  if (selected && selected.is('image')) {
    selected.set('src', url);
  } else {
    editor.addComponents('<img src="' + url + '" style="max-width:100%;" />');
  }
}

function deleteMedia(id) {
  if (!confirm('Delete this media file?')) return;
  fetch('/admin/api/media/' + id, { method: 'DELETE' })
    .then(function(r) { return r.json(); })
    .then(function(d) { if (d.ok) loadMedia(); });
}


// ══════════════════════════════════════════════════════
//  SEO PANEL
// ══════════════════════════════════════════════════════

function loadSeo() {
  fetch('/admin/api/seo/' + PAGE_NAME)
    .then(function(r) { return r.json(); })
    .then(function(d) {
      if (!d.ok || !d.seo) return;
      var s = d.seo;
      document.getElementById('seoTitle').value = s.meta_title || '';
      document.getElementById('seoDesc').value = s.meta_description || '';
      document.getElementById('ogTitle').value = s.og_title || '';
      document.getElementById('ogDesc').value = s.og_description || '';
      document.getElementById('ogImage').value = s.og_image || '';
      document.getElementById('canonicalUrl').value = s.canonical_url || '';
      document.getElementById('jsonLd').value = s.json_ld || '';
      document.getElementById('noindex').checked = !!s.noindex;
      updateCharCounts();
    });
}

function saveSeo() {
  var data = {
    meta_title: document.getElementById('seoTitle').value,
    meta_description: document.getElementById('seoDesc').value,
    og_title: document.getElementById('ogTitle').value,
    og_description: document.getElementById('ogDesc').value,
    og_image: document.getElementById('ogImage').value,
    canonical_url: document.getElementById('canonicalUrl').value,
    json_ld: document.getElementById('jsonLd').value,
    noindex: document.getElementById('noindex').checked ? 1 : 0,
  };
  fetch('/admin/api/seo/' + PAGE_NAME, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data)
  })
  .then(function(r) { return r.json(); })
  .then(function(d) {
    if (d.ok) alert('SEO settings saved!');
  });
}

function updateCharCounts() {
  var title = document.getElementById('seoTitle').value;
  var desc = document.getElementById('seoDesc').value;
  var tc = document.getElementById('seoTitleCount');
  var dc = document.getElementById('seoDescCount');
  tc.textContent = title.length + '/60';
  tc.className = 'bs-char-count' + (title.length > 60 ? ' over' : '');
  dc.textContent = desc.length + '/160';
  dc.className = 'bs-char-count' + (desc.length > 160 ? ' over' : '');
}

document.getElementById('seoTitle').addEventListener('input', updateCharCounts);
document.getElementById('seoDesc').addEventListener('input', updateCharCounts);


// ══════════════════════════════════════════════════════
//  PAGE ANALYTICS
// ══════════════════════════════════════════════════════

function loadAnalytics() {
  var container = document.getElementById('analyticsContent');
  container.innerHTML = '<p style="text-align:center;color:#64748b;padding:20px;">Loading...</p>';

  fetch('/admin/api/page-analytics/' + PAGE_NAME)
    .then(function(r) { return r.json(); })
    .then(function(d) {
      if (!d.ok) {
        container.innerHTML = '<p style="text-align:center;color:#64748b;padding:20px;">No data available.</p>';
        return;
      }

      var html = '<div class="bs-stat-row">' +
        '<div class="bs-stat-card"><div class="bs-stat-val">' + d.total + '</div><div class="bs-stat-label">Total Views</div></div>' +
        '<div class="bs-stat-card"><div class="bs-stat-val">' + d.today + '</div><div class="bs-stat-label">Today</div></div>' +
        '<div class="bs-stat-card"><div class="bs-stat-val">' + d.week + '</div><div class="bs-stat-label">This Week</div></div>' +
      '</div>';

      // Daily chart
      if (d.daily && d.daily.length) {
        var maxV = Math.max.apply(null, d.daily.map(function(x) { return x.cnt; })) || 1;
        html += '<h4 style="font-size:0.78rem;color:#94a3b8;margin-bottom:8px;">Last 30 Days</h4>';
        html += '<div class="bs-chart-bar">';
        d.daily.forEach(function(day) {
          var h = Math.max(2, (day.cnt / maxV) * 100);
          html += '<div class="bs-chart-bar-col" style="height:' + h + '%;" title="' + day.day + ': ' + day.cnt + ' views"></div>';
        });
        html += '</div>';
      }

      // Referrers
      if (d.referrers && d.referrers.length) {
        html += '<h4 style="font-size:0.78rem;color:#94a3b8;margin:16px 0 8px;">Top Referrers</h4>';
        d.referrers.forEach(function(r) {
          html += '<div class="bs-referrer-item"><span class="bs-referrer-url">' + r.referrer + '</span><span class="bs-referrer-cnt">' + r.cnt + '</span></div>';
        });
      }

      container.innerHTML = html;
    })
    .catch(function() {
      container.innerHTML = '<p style="text-align:center;color:#64748b;padding:20px;">Failed to load analytics.</p>';
    });
}
