/**
 * InbXr Signal Score result rendering.
 *
 * Shared by the homepage hero (email_test_hero.html) and the
 * standalone /signal-score page (signal/anonymous.html).
 *
 * Depends on utils.js being loaded first (escHtml, classFor, etc.).
 */
(function () {
  'use strict';

  var esc = window.escHtml || function(s){ return String(s||''); };

  // ── Auth protocol pills (SPF / DKIM / DMARC) ──────────

  function renderAuthPills(meta) {
    if (!meta || !meta.authentication_standing) return '';
    var a = meta.authentication_standing;
    function pill(label, status) {
      var pass = status === 'pass' || status === 'valid';
      var icon = pass ? '\u2713' : '\u2717';
      var cls = pass ? 'sig-pill-pass' : 'sig-pill-fail';
      return '<span class="sig-auth-pill ' + cls + '">' + icon + ' ' + label + '</span>';
    }
    var dmarcExtra = '';
    if ((a.dmarc === 'pass' || a.dmarc === 'valid') && a.dmarc_policy === 'none') {
      dmarcExtra = ' <span class="sig-auth-pill sig-pill-warn" title="DMARC policy is monitoring only">\u26A0 p=none</span>';
    }
    return '<div class="sig-auth-pills">' + pill('SPF', a.spf) + pill('DKIM', a.dkim) + pill('DMARC', a.dmarc) + dmarcExtra + '</div>';
  }

  // ── Quick Wins (top recommendations) ───────────────────

  function renderQuickWins(d) {
    var recs = d.recommendations;
    if (!recs || !recs.length) return '';
    var severityOrder = {critical: 0, high: 1, medium: 2, low: 3};
    recs = recs.slice().sort(function(a, b) {
      return (severityOrder[a.severity] || 3) - (severityOrder[b.severity] || 3);
    }).slice(0, 3);

    var items = recs.map(function(r) {
      var urgent = r.severity === 'critical' || r.severity === 'high';
      var sevLabel = urgent ? 'Fix now' : r.severity === 'medium' ? 'Improve' : 'Optional';
      return '<div class="qw-item ' + (urgent ? 'qw-item--urgent' : 'qw-item--info') + '">' +
        '<span class="qw-item__sev">' + sevLabel + '</span>' +
        '<div class="qw-item__body">' +
          '<strong>' + esc(r.item) + '</strong>' +
          '<p>' + esc(r.recommendation) + '</p>' +
        '</div>' +
      '</div>';
    }).join('');

    return '<div class="sig-card sig-card--quickwins">' +
      '<span class="sig-card__label sig-card__label--amber">Quick wins \u00b7 Fix these before your next send</span>' +
      '<div class="qw-list">' + items + '</div>' +
    '</div>';
  }

  // ── Ghost Opens teaser card ────────────────────────────

  function renderGhostOpensCard() {
    return '<div class="sig-card sig-card--ghost">' +
      '<span class="sig-card__label sig-card__label--purple">MPP Engagement Analysis</span>' +
      '<h3 class="sig-card__h">Your ESP says 45% open rate. The real number might be 28%.</h3>' +
      '<p class="sig-card__p">The difference? <strong>Ghost Opens.</strong> Apple Mail Privacy Protection creates fake "opens" that your ESP counts as real engagement. Over 55% of US email users have it enabled. Upload your list and our MPP Engagement Analysis strips them out \u2014 so you see the number that actually matters.</p>' +
      '<a href="/signal-score#csvUploadArea" class="sig-card__cta sig-card__cta--purple">Upload your list to find out \u2192</a>' +
    '</div>';
  }

  // ── Domain check result card (2 of 7 signals) ─────────

  function renderDomainCard(d) {
    var grade = d.grade || 'F';
    var score = Math.round(d.score || 0);
    var classFor = window.InbXr ? window.InbXr.classFor : function(s){ return s >= 75 ? 'is-good' : s >= 50 ? 'is-warn' : 'is-bad'; };

    var auth = d.scores && d.scores.authentication_standing != null
      ? Math.round(d.scores.authentication_standing * 100 / 5) : 0;
    var rep = d.scores && d.scores.domain_reputation != null
      ? Math.round(d.scores.domain_reputation * 100 / 15) : 0;

    var summary;
    if (grade === 'A' || grade === 'B') {
      summary = "Your domain side is in solid shape. Most senders find their real problems in the 5 list-side signals below.";
    } else if (grade === 'C') {
      summary = "Your domain has at least one issue. Your 5 list-side signals likely have more.";
    } else {
      summary = "Your domain has significant issues. Your 5 list-side signals almost certainly have more.";
    }

    return '<div class="sig-card sig-card--domain">' +
      '<span class="sig-card__label">Domain analysis</span>' +
      '<div class="sig-hero">' +
        '<div>' +
          '<div class="sig-hero__num sig-hero__num--' + grade + '">' + score + '</div>' +
          '<div class="sig-hero__grade">Grade ' + grade + '</div>' +
        '</div>' +
        '<div class="sig-hero__summary">' +
          '<h3>' + esc(d.domain) + ' \u00b7 Partial Signal Score</h3>' +
          '<p>' + summary + '</p>' +
        '</div>' +
      '</div>' +
      renderAuthPills(d.metadata) +
      '<div class="sig-signals">' +
        '<div class="sig-row"><span class="sig-row__name">06 Authentication Standing</span><span class="sig-row__val ' + classFor(auth) + '">' + auth + '/100</span></div>' +
        '<div class="sig-row"><span class="sig-row__name">04 Domain Reputation</span><span class="sig-row__val ' + classFor(rep) + '">' + rep + '/100</span></div>' +
      '</div>' +
    '</div>';
  }

  // ── Locked signal teasers ──────────────────────────────

  function renderLockedSignals() {
    return '<div class="sig-signals">' +
      '<div class="sig-row sig-row--locked"><span class="sig-row__name">01 Bounce Exposure</span><span class="sig-row__val sig-row__val--locked">Predictive bounce risk</span></div>' +
      '<div class="sig-row sig-row--locked sig-row--purple"><span class="sig-row__name">02 Engagement Trajectory</span><span class="sig-row__val sig-row__val--locked">Ghost Opens removed</span></div>' +
      '<div class="sig-row sig-row--locked"><span class="sig-row__name">03 Acquisition Quality</span><span class="sig-row__val sig-row__val--locked">Not read by any other tool</span></div>' +
      '<div class="sig-row sig-row--locked"><span class="sig-row__name">05 Spam Trap Exposure</span><span class="sig-row__val sig-row__val--locked">Probabilistic trap risk</span></div>' +
      '<div class="sig-row sig-row--locked"><span class="sig-row__name">07 Decay Velocity</span><span class="sig-row__val sig-row__val--locked">Score trend direction</span></div>' +
    '</div>';
  }

  // ── Final CTA (signup prompt) ──────────────────────────

  function renderFinalCta(domain) {
    return '<div class="sig-final-cta">' +
      '<h4>5 more signals are waiting in your list.</h4>' +
      renderLockedSignals() +
      '<a href="/signup?from=signal-score&domain=' + encodeURIComponent(domain || '') + '" class="sig-final-cta__btn">Sign up free to see all 7 signals \u2192</a>' +
    '</div>' +
    '<div class="sig-share">' +
      '<button type="button" class="sig-share__btn" data-domain="' + esc(domain || '') + '">Share your Signal Score</button>' +
    '</div>';
  }

  // ── CSV result (full 7-signal) ─────────────────────────

  function renderCsvResult(d) {
    var grade = d.grade || 'F';
    var score = Math.round(d.score || 0);
    var total = d.total_contacts || d.rows_parsed || 0;
    var skipped = d.rows_skipped || 0;
    var segs = d.segments || {};
    var meta = d.metadata || {};
    var scores = d.scores || {};
    var classFor = window.InbXr ? window.InbXr.classFor : function(s){ return s >= 75 ? 'is-good' : s >= 50 ? 'is-warn' : 'is-bad'; };

    var verdict;
    if (grade === 'A') verdict = 'Your list is healthy. Keep doing what you\u2019re doing and monitor for drift.';
    else if (grade === 'B') verdict = 'Your list is in good shape with minor issues. The fixes below will push you to an A.';
    else if (grade === 'C') verdict = 'Your list has real problems that are likely hurting your deliverability right now. Fix the red signals below before your next send.';
    else verdict = 'Your list is in critical condition. Sending to it as-is risks serious domain reputation damage. Address the issues below immediately.';

    // Per-signal card builder
    function sigCard(label, key, max, explainFn) {
      var raw = scores[key] != null ? scores[key] : null;
      var m = meta[key] || {};
      var isLocked = m.locked === true;
      var pct = raw !== null ? Math.round(raw * 100 / max) : 0;

      if (isLocked) {
        return '<div class="csv-sig csv-sig--locked">' +
          '<div class="csv-sig__head"><strong>' + label + '</strong><span class="csv-sig__pro">PRO</span></div>' +
          '<p class="csv-sig__explain">' +
            (key === 'engagement_trajectory' ? 'Ghost Opens removed \u2014 see your real engagement rate. Available on Pro.' :
             key === 'acquisition_quality' ? 'Day-1 cohort analysis \u2014 which acquisition channels are dragging your list down. Available on Pro.' :
             'Available on Pro.') +
          '</p></div>';
      }

      var status = pct >= 75 ? 'good' : pct >= 50 ? 'warn' : 'bad';
      var explanation = explainFn(pct, m, segs);

      return '<div class="csv-sig csv-sig--' + status + '">' +
        '<div class="csv-sig__head"><strong>' + label + '</strong><span class="csv-sig__score csv-sig__score--' + status + '">' + pct + '/100</span></div>' +
        '<p class="csv-sig__explain">' + explanation + '</p>' +
      '</div>';
    }

    function explainBounce(pct, m) {
      if (pct >= 90) return 'Low bounce risk. Your list is clean of role addresses, disposable domains, and catch-all traps.';
      var parts = [];
      if (m.bounce_rate > 1) parts.push(Math.round(m.bounce_rate) + '% historical bounce rate');
      if (m.disposable_rate > 0.5) parts.push(Math.round(m.disposable_rate) + '% disposable email addresses');
      if (m.role_rate > 1) parts.push(Math.round(m.role_rate) + '% role addresses (info@, support@, etc.)');
      if (m.catch_all_rate > 5) parts.push(Math.round(m.catch_all_rate) + '% catch-all domains');
      if (!parts.length) return 'Some predictive bounce risk detected. Consider running the list through email verification before sending.';
      return parts.join('. ') + '. <strong>Fix:</strong> Remove these contacts or verify them individually before your next send.';
    }

    function explainDomainRep(pct, m) {
      if (pct >= 90) return 'Your sending domain has a clean reputation. No blocklist hits detected.';
      if (m.blacklisted) return 'Your domain is listed on ' + (m.blacklists_count || 'one or more') + ' blocklist(s). This is actively hurting your inbox placement. <strong>Fix:</strong> Run <a href="/sender">Sender Check</a> to see which lists and how to delist.';
      var parts = [];
      if (m.yahoo_aol_risk === 'high') parts.push('High concentration of Yahoo/AOL recipients');
      if (m.free_email_rate > 50) parts.push(Math.round(m.free_email_rate) + '% free email addresses');
      if (!parts.length) return 'Some reputation signals are below ideal. Run <a href="/sender">Sender Check</a> for a detailed breakdown.';
      return parts.join('. ') + '.';
    }

    function explainDormancy(pct, m) {
      if (pct >= 80) return 'Low dormancy risk. Most of your list has recent engagement signals.';
      var parts = [];
      if (m.very_old_inactive_count > 0) parts.push(m.very_old_inactive_count.toLocaleString() + ' contacts haven\u2019t engaged in over a year');
      if (m.old_inactive_count > 0) parts.push(m.old_inactive_count.toLocaleString() + ' contacts haven\u2019t engaged in 6\u201312 months');
      if (!parts.length) return 'Significant dormancy detected. Sending to inactive contacts degrades your sender reputation over time.';
      return parts.join('. ') + '. <strong>Fix:</strong> Run a re-engagement campaign to the dormant segment. Remove anyone who doesn\u2019t respond within 30 days.';
    }

    function explainAuth(pct, m) {
      if (pct >= 90) return 'SPF, DKIM, and DMARC are all passing. Your authentication is solid.';
      if (!m || m.locked) return 'Authentication data not available. Run <a href="/sender">Sender Check</a> for a full auth audit.';
      var parts = [];
      if (m.spf && m.spf !== 'pass' && m.spf !== 'valid') parts.push('SPF is ' + m.spf);
      if (m.dkim && m.dkim !== 'pass' && m.dkim !== 'valid') parts.push('DKIM is ' + m.dkim);
      if (m.dmarc && m.dmarc !== 'pass' && m.dmarc !== 'valid') parts.push('DMARC is ' + m.dmarc);
      else if (m.dmarc_policy === 'none') parts.push('DMARC policy is p=none (monitoring only)');
      if (!parts.length) return 'Mostly passing but has room for improvement. Run <a href="/sender">Sender Check</a> for specifics.';
      return parts.join('. ') + '. <strong>Fix:</strong> Run <a href="/sender">Sender Check</a> for exact DNS records to copy-paste.';
    }

    function explainDecay(pct) {
      if (pct >= 80) return 'Your list health is stable or improving. No concerning trends.';
      var dir = d.trajectory_direction || 'unknown';
      if (dir === 'declining') return 'Your list health is trending downward. <strong>Fix:</strong> Identify what changed \u2014 new acquisition source, sending frequency, or content shift.';
      return 'Not enough historical data to calculate a trend. Sign up to track this over time.';
    }

    var signalsHtml =
      sigCard('01 Bounce Exposure', 'bounce_exposure', 25, explainBounce) +
      sigCard('02 Engagement Trajectory', 'engagement_trajectory', 25, function(){return '';}) +
      sigCard('03 Acquisition Quality', 'acquisition_quality', 15, function(){return '';}) +
      sigCard('04 Domain Reputation', 'domain_reputation', 15, explainDomainRep) +
      sigCard('05 Spam Trap Exposure', 'dormancy_risk', 10, explainDormancy) +
      sigCard('06 Authentication Standing', 'authentication_standing', 5, explainAuth) +
      sigCard('07 Decay Velocity', 'decay_velocity', 5, explainDecay);

    // Segments
    var segHtml = '';
    if (segs.total > 0) {
      var sp = function(count, label, cls) {
        if (!count) return '';
        var pct = Math.round(count / segs.total * 100);
        return '<span class="seg-pill seg-pill--' + cls + '">' + count.toLocaleString() + ' ' + label + ' (' + pct + '%)</span>';
      };
      segHtml = '<div class="seg-pills">' +
        sp(segs.active, 'Active', 'green') + sp(segs.warm, 'Warm', 'blue') +
        sp(segs.at_risk, 'At Risk', 'amber') + sp(segs.dormant, 'Dormant', 'red') +
      '</div>';
      if (segs.dormant === segs.total) {
        segHtml += '<div class="seg-warning">' +
          '<strong>100% of your list is classified as dormant.</strong> This usually means the CSV doesn\u2019t include engagement date columns (last_open_date, last_click_date). Without that data, every contact defaults to dormant. To get an accurate reading, export your list from your ESP with engagement dates included, or connect your ESP directly.' +
        '</div>';
      }
    }

    return {
      hero: '<div class="sig-hero">' +
        '<div>' +
          '<div class="sig-hero__num sig-hero__num--' + grade + '">' + score + '</div>' +
          '<div class="sig-hero__grade">Grade ' + grade + '</div>' +
        '</div>' +
        '<div class="sig-hero__summary">' +
          '<h3>Your Signal Score</h3>' +
          '<p>' + verdict + '</p>' +
          '<span class="sig-hero__meta">' + total.toLocaleString() + ' contacts analyzed' + (skipped > 0 ? ' \u00b7 ' + skipped.toLocaleString() + ' skipped' : '') + '</span>' +
        '</div>' +
      '</div>',
      segments: segHtml,
      signals: '<div class="csv-signals">' + signalsHtml + '</div>',
      cta: '<div class="sig-final-cta">' +
        '<h4>This is a one-time snapshot. Your list changes every day.</h4>' +
        '<p>Sign up to save this score, get alerted when signals degrade, and connect your ESP for automatic recalculation every 6 hours.</p>' +
        '<a href="/signup?from=csv-signal-score" class="sig-final-cta__btn">Sign up free to start monitoring \u2192</a>' +
      '</div>',
    };
  }

  // ── Expose globally ────────────────────────────────────

  window.InbXr = window.InbXr || {};
  window.InbXr.renderAuthPills = renderAuthPills;
  window.InbXr.renderQuickWins = renderQuickWins;
  window.InbXr.renderGhostOpensCard = renderGhostOpensCard;
  window.InbXr.renderDomainCard = renderDomainCard;
  window.InbXr.renderLockedSignals = renderLockedSignals;
  window.InbXr.renderFinalCta = renderFinalCta;
  window.InbXr.renderCsvResult = renderCsvResult;
})();
