/**
 * InbXr shared utilities.
 *
 * Single source of truth for escaping, formatting, and common UI helpers.
 * Every page-specific JS file should use these instead of local copies.
 *
 * Loaded globally via <script src="/static/js/utils.js"> before any
 * page-specific scripts. All exports are on the window.InbXr namespace.
 */
(function () {
  'use strict';

  // ── HTML / Attribute escaping ──────────────────────────

  function escHtml(str) {
    return String(str ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function escAttr(str) {
    return String(str ?? '')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  // ── Score classification ───────────────────────────────

  /** Map a 0-100 score to a CSS class suffix: 'is-good' | 'is-warn' | 'is-bad' */
  function classFor(score) {
    if (score >= 75) return 'is-good';
    if (score >= 50) return 'is-warn';
    return 'is-bad';
  }

  /** Map a 0-100 score to a hex color */
  function colorFor(score) {
    if (score >= 75) return '#16a34a';
    if (score >= 50) return '#d97706';
    return '#dc2626';
  }

  // ── Clipboard ──────────────────────────────────────────

  function copyToClipboard(text, btn) {
    if (!navigator.clipboard) return;
    navigator.clipboard.writeText(text).then(function () {
      if (!btn) return;
      var orig = btn.textContent;
      btn.textContent = 'Copied!';
      setTimeout(function () { btn.textContent = orig; }, 2000);
    });
  }

  // ── Number formatting ──────────────────────────────────

  function fmtNum(n) {
    return (n || 0).toLocaleString();
  }

  function fmtPct(n) {
    return Math.round(n || 0) + '%';
  }

  // ── Expose globally ────────────────────────────────────

  window.InbXr = window.InbXr || {};
  window.InbXr.escHtml = escHtml;
  window.InbXr.escAttr = escAttr;
  window.InbXr.classFor = classFor;
  window.InbXr.colorFor = colorFor;
  window.InbXr.copyToClipboard = copyToClipboard;
  window.InbXr.fmtNum = fmtNum;
  window.InbXr.fmtPct = fmtPct;

  // Backward-compatible globals so existing code doesn't break
  // while we migrate file-by-file.
  window.escHtml = escHtml;
  window.escAttr = escAttr;
  window.esc     = escHtml;
  window.escH    = escHtml;
})();
