/* ══════════════════════════════════════════════════════
   INBXR — Dashboard (API-driven, sidebar layout)
   ══════════════════════════════════════════════════════ */

'use strict';

var $ = function(sel, ctx) { return (ctx || document).querySelector(sel); };
var $$ = function(sel, ctx) { return Array.from((ctx || document).querySelectorAll(sel)); };

var currentView = 'overview';
var TOOL_LABELS = {
  email_test:      'Email Test',
  domain_check:    'Sender Check',
  subject_test:    'Subject Score',
  placement_test:  'Placement Test',
  header_analysis: 'Header Analysis',
  copy_analysis:   'Copy Analysis',
  email_verify:    'Email Verify',
};
var TOOL_COLORS = {
  email_test:      '#2563eb',
  domain_check:    '#059669',
  subject_test:    '#d97706',
  placement_test:  '#7c3aed',
  header_analysis: '#0891b2',
  copy_analysis:   '#e11d48',
  email_verify:    '#4f46e5',
};

// ══════════════════════════════════════════════════════
//  NAVIGATION
// ══════════════════════════════════════════════════════
$$('.dash-nav__item').forEach(function(item) {
  item.addEventListener('click', function(e) {
    e.preventDefault();
    var view = this.dataset.view;
    if (view === currentView) return;
    switchView(view);
  });
});

function switchView(view) {
  currentView = view;
  $$('.dash-nav__item').forEach(function(el) {
    el.classList.toggle('dash-nav__item--active', el.dataset.view === view);
  });
  // Close mobile sidebar
  var sidebar = document.getElementById('dashSidebar');
  if (sidebar) sidebar.classList.remove('dash-sidebar--open');

  var main = $('#dashMain');
  main.innerHTML = '<div class="dash-loading"><div class="loading-ring"></div></div>';

  if (view === 'overview') renderOverview();
  else if (view === 'blacklist') renderBlacklistView();
  else if (view === 'warmup') renderWarmupView();
  else renderToolView(view);
}

// Mobile sidebar toggle
var toggleBtn = document.getElementById('dashSidebarToggle');
if (toggleBtn) {
  toggleBtn.addEventListener('click', function() {
    document.getElementById('dashSidebar').classList.toggle('dash-sidebar--open');
  });
}

// ══════════════════════════════════════════════════════
//  OVERVIEW
// ══════════════════════════════════════════════════════
function renderOverview() {
  var stats = window.__dashStats || {};
  var main = $('#dashMain');

  // Render with server-side stats immediately, then fetch full data
  main.innerHTML = buildOverviewShell(stats);

  apiFetch('/api/history/stats').then(function(data) {
    if (!data || data.__gated) {
      // Free tier — show upgrade hints in chart/breakdown areas
      var chart = document.getElementById('overviewChart');
      if (chart) chart.innerHTML = PRO_UPGRADE_HTML;
      var bd = document.getElementById('overviewBreakdown');
      if (bd) bd.innerHTML = '<p class="dash-empty-hint">Run tests to see breakdown</p>';
      return;
    }
    var s = data.stats || {};
    window.__dashStats = s;

    setStatCard('statTotal', s.total_checks || 0, 'Total Tests');
    setStatCard('statWeek', s.checks_this_week || 0, 'This Week');
    setStatCard('statAvg', s.avg_score != null ? s.avg_score : '--', 'Avg Score');
    setStatCard('statGrade', s.best_grade || '--', 'Best Grade');

    renderBreakdown(data.breakdown || []);
    renderTrendChart(data.trend || [], 'overviewChart');
  });

  // Recent activity
  apiFetch('/api/history?limit=15').then(function(data) {
    if (!data || data.__gated) {
      var recent = document.getElementById('overviewRecent');
      if (recent) recent.innerHTML = PRO_UPGRADE_HTML;
      return;
    }
    renderRecentList(data.results || [], 'overviewRecent');
  });
}

function buildCreditsBar(c) {
  if (!c || !c.daily_limit) return '';
  var pct = Math.min(100, Math.round(c.used_today / c.daily_limit * 100));
  var barColor = pct >= 90 ? 'var(--red)' : pct >= 70 ? 'var(--yellow)' : 'var(--brand)';
  return '<div class="dash-credits">' +
    '<div class="dash-credits__header">' +
      '<span class="dash-credits__tier">' + esc(c.tier_label) + ' Plan</span>' +
      '<span class="dash-credits__count">' + c.remaining + ' / ' + c.daily_limit + ' checks remaining today</span>' +
      (c.tier === 'free' ? '<a href="/pricing" class="dash-credits__upgrade">Upgrade</a>' : '') +
    '</div>' +
    '<div class="dash-credits__bar-bg">' +
      '<div class="dash-credits__bar" style="width:' + pct + '%;background:' + barColor + '"></div>' +
    '</div>' +
  '</div>';
}

function buildQuickActions() {
  return '<div class="dash-actions">' +
    '<h3 class="dash-actions__title">What would you like to do?</h3>' +
    '<div class="dash-actions__grid">' +
      quickActionBtn('/', 'M22 12h-4l-3 9L9 3l-3 9H2', 'Run Email Test', 'Test authentication, spam risk, and deliverability') +
      quickActionBtn('/sender', 'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z', 'Check Sender Auth', 'Verify SPF, DKIM, DMARC for any domain') +
      quickActionBtn('/placement', 'M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z||M22 6l-10 7L2 6', 'Inbox Placement Test', 'See where emails land across providers') +
      quickActionBtn('/subject-scorer', 'M17 10H3||M21 6H3||M21 14H3||M17 18H3', 'Score Subject Lines', 'A/B test and rank subject lines') +
      quickActionBtn('/blacklist-monitor', 'M12 2a10 10 0 100 20 10 10 0 000-20z||M4.93 4.93l14.14 14.14', 'Scan Blocklists', 'Check 110+ blocklists for your domain') +
      quickActionBtn('/email-verifier', 'M22 11.08V12a10 10 0 11-5.93-9.14||M22 4L12 14.01 9 11.01', 'Verify Emails', 'Validate email addresses before sending') +
      quickActionBtn('/header-analyzer', 'M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z||M14 2v6h6', 'Analyze Headers', 'Paste raw headers for deep analysis') +
      quickActionBtn('/warmup', 'M13 2L3 14h9l-1 8 10-12h-9l1-8z', 'Warmup Tracker', 'Track your domain warmup progress') +
    '</div>' +
  '</div>';
}

function quickActionBtn(href, paths, title, desc) {
  var svgPaths = paths.split('||').map(function(p) {
    return '<path d="' + p + '"/>';
  }).join('');
  return '<a href="' + href + '" class="dash-action-card">' +
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="22" height="22">' + svgPaths + '</svg>' +
    '<strong>' + esc(title) + '</strong>' +
    '<span>' + esc(desc) + '</span>' +
  '</a>';
}

function buildOverviewShell(s) {
  var c = window.__dashCredits || {};
  return '<div class="dash-view">' +
    buildCreditsBar(c) +
    '<h2 class="dash-view__title">Overview</h2>' +
    '<div class="db-stats">' +
      statCardHtml('statTotal', s.total_checks || 0, 'Total Tests') +
      statCardHtml('statWeek', s.checks_this_week || 0, 'This Week') +
      statCardHtml('statAvg', s.avg_score != null ? s.avg_score : '--', 'Avg Score') +
      statCardHtml('statGrade', s.best_grade || '--', 'Best Grade') +
    '</div>' +
    buildQuickActions() +
    '<div class="dash-row">' +
      '<div class="dash-card dash-card--wide">' +
        '<h3 class="dash-card__title">Score Trend (30 days)</h3>' +
        '<div id="overviewChart" class="db-chart" style="min-height:140px"><div class="dash-loading-sm"><div class="loading-ring"></div></div></div>' +
      '</div>' +
      '<div class="dash-card">' +
        '<h3 class="dash-card__title">Tests by Tool</h3>' +
        '<div id="overviewBreakdown"><div class="dash-loading-sm"><div class="loading-ring"></div></div></div>' +
      '</div>' +
    '</div>' +
    '<div class="dash-card">' +
      '<div class="dash-card__header">' +
        '<h3 class="dash-card__title">Recent Activity</h3>' +
      '</div>' +
      '<div id="overviewRecent"><div class="dash-loading-sm"><div class="loading-ring"></div></div></div>' +
    '</div>' +
  '</div>';
}

function statCardHtml(id, value, label) {
  var cls = typeof value === 'string' && value.length > 3 ? ' db-stat__num--small' : '';
  return '<div class="db-stat-card" id="' + id + '">' +
    '<span class="db-stat__num' + cls + '">' + esc(String(value)) + '</span>' +
    '<span class="db-stat__label">' + esc(label) + '</span>' +
  '</div>';
}

function setStatCard(id, value, label) {
  var el = document.getElementById(id);
  if (!el) return;
  var cls = typeof value === 'string' && value.length > 3 ? ' db-stat__num--small' : '';
  el.innerHTML = '<span class="db-stat__num' + cls + '">' + esc(String(value)) + '</span>' +
    '<span class="db-stat__label">' + esc(label) + '</span>';
}

function renderBreakdown(breakdown) {
  var container = document.getElementById('overviewBreakdown');
  if (!container) return;

  if (!breakdown.length) {
    container.innerHTML = '<p class="dash-empty-hint">No test history yet</p>';
    return;
  }

  var maxCount = Math.max.apply(null, breakdown.map(function(b) { return b.count; }));
  var html = '<div class="dash-breakdown">';
  breakdown.forEach(function(b) {
    var pct = Math.round(b.count / maxCount * 100);
    var color = TOOL_COLORS[b.tool] || '#64748b';
    var label = TOOL_LABELS[b.tool] || b.tool;
    html += '<div class="dash-breakdown__row">' +
      '<span class="dash-breakdown__label">' + esc(label) + '</span>' +
      '<div class="dash-breakdown__bar-bg">' +
        '<div class="dash-breakdown__bar" style="width:' + pct + '%;background:' + color + '"></div>' +
      '</div>' +
      '<span class="dash-breakdown__count">' + b.count + '</span>' +
    '</div>';
  });
  html += '</div>';
  container.innerHTML = html;
}

function renderTrendChart(trend, containerId) {
  var container = document.getElementById(containerId);
  if (!container) return;

  if (trend.length < 2) {
    container.innerHTML = '<p class="dash-empty-hint">Need at least 2 days of data to show trends</p>';
    return;
  }

  var maxScore = 100;
  var html = '<div class="db-chart__bars">';
  trend.forEach(function(t, i) {
    var h = ((t.avg_score || 0) / maxScore) * 100;
    var day = shortDate(t.day);
    html += '<div class="db-chart__group" style="animation-delay:' + (i * 30) + 'ms" title="' + esc(t.day) + ': avg ' + (t.avg_score || 0) + ' (' + t.count + ' tests)">' +
      '<div class="db-chart__bar-pair">' +
        '<div class="db-chart__bar db-chart__bar--score" style="height:' + h + '%"></div>' +
      '</div>' +
      '<span class="db-chart__date">' + day + '</span>' +
    '</div>';
  });
  html += '</div>';
  container.innerHTML = html;
}

// ══════════════════════════════════════════════════════
//  TOOL VIEW (generic per-tool history)
// ══════════════════════════════════════════════════════
function renderToolView(toolName) {
  var label = TOOL_LABELS[toolName] || toolName;
  var main = $('#dashMain');

  main.innerHTML = '<div class="dash-view">' +
    '<h2 class="dash-view__title">' + esc(label) + ' History</h2>' +
    '<div id="toolStats" class="db-stats"></div>' +
    '<div class="dash-card">' +
      '<h3 class="dash-card__title">Score Trend</h3>' +
      '<div id="toolChart" class="db-chart" style="min-height:140px"><div class="dash-loading-sm"><div class="loading-ring"></div></div></div>' +
    '</div>' +
    '<div class="dash-card">' +
      '<div class="dash-card__header">' +
        '<h3 class="dash-card__title">Results</h3>' +
      '</div>' +
      '<div id="toolResults"><div class="dash-loading-sm"><div class="loading-ring"></div></div></div>' +
    '</div>' +
  '</div>';

  // Fetch trend
  apiFetch('/api/history/trend?tool=' + toolName).then(function(data) {
    if (!data || data.__gated) {
      var tc = document.getElementById('toolChart');
      if (tc) tc.innerHTML = PRO_UPGRADE_HTML;
      return;
    }
    renderTrendChart(data.trend || [], 'toolChart');
  });

  // Fetch results
  apiFetch('/api/history?tool=' + toolName + '&limit=50').then(function(data) {
    if (!data || data.__gated) {
      var tr = document.getElementById('toolResults');
      if (tr) tr.innerHTML = PRO_UPGRADE_HTML;
      return;
    }
    var results = data.results || [];

    // Stats
    var total = results.length;
    var scores = results.filter(function(r) { return r.score != null; }).map(function(r) { return r.score; });
    var avg = scores.length ? Math.round(scores.reduce(function(a, b) { return a + b; }, 0) / scores.length) : '--';
    var el = document.getElementById('toolStats');
    if (el) {
      el.innerHTML = statCardHtml('', total, 'Total') +
        statCardHtml('', avg, 'Avg Score') +
        statCardHtml('', results.length && results[0].grade ? results[0].grade : '--', 'Latest Grade');
    }

    renderRecentList(results, 'toolResults');
  });
}

// ══════════════════════════════════════════════════════
//  DETAIL VIEW
// ══════════════════════════════════════════════════════
function showDetail(historyId) {
  var main = $('#dashMain');
  main.innerHTML = '<div class="dash-loading"><div class="loading-ring"></div></div>';

  apiFetch('/api/history/' + historyId).then(function(data) {
    if (!data) {
      main.innerHTML = '<div class="dash-view"><p>Result not found.</p></div>';
      return;
    }

    var toolLabel = TOOL_LABELS[data.tool] || data.tool;
    var result = data.result_json || {};

    var html = '<div class="dash-view">' +
      '<button class="dash-back-btn" id="detailBack">&larr; Back to ' + esc(toolLabel) + '</button>' +
      '<div class="dash-detail-header">' +
        '<h2 class="dash-view__title">' + esc(data.input_summary || 'Result') + '</h2>' +
        '<div class="dash-detail-meta">' +
          '<span class="dash-detail-tool">' + esc(toolLabel) + '</span>' +
          (data.grade ? '<span class="dash-detail-grade dash-grade--' + gradeClass(data.grade) + '">' + esc(data.grade) + '</span>' : '') +
          (data.score != null ? '<span class="dash-detail-score">Score: ' + data.score + '</span>' : '') +
          '<span class="dash-detail-date">' + formatDate(data.created_at) + '</span>' +
        '</div>' +
      '</div>';

    // Render tool-specific detail
    html += renderToolDetail(data.tool, result);

    // Raw JSON collapsible
    html += '<div class="dash-card">' +
      '<button class="dash-accordion-trigger" id="rawToggle">View Raw Data</button>' +
      '<pre class="dash-raw-json hidden" id="rawJson">' + esc(JSON.stringify(result, null, 2)) + '</pre>' +
    '</div>';

    html += '</div>';
    main.innerHTML = html;

    // Back button
    document.getElementById('detailBack').addEventListener('click', function() {
      switchView(data.tool);
    });

    // Raw toggle
    document.getElementById('rawToggle').addEventListener('click', function() {
      document.getElementById('rawJson').classList.toggle('hidden');
    });
  });
}

function renderToolDetail(tool, result) {
  var html = '';

  if (tool === 'email_test') {
    var p = result.placement || {};
    var hg = result.header_grades || [];
    html += '<div class="dash-card">' +
      '<h3 class="dash-card__title">Placement</h3>' +
      '<div class="dash-detail-placement">' +
        '<span class="dash-detail-placement__badge dash-placement--' + (p.placement || 'unknown') + '">' + esc(p.placement || '?') + '</span>' +
        '<span>Folder: ' + esc(p.folder || '?') + '</span>' +
        '<span>Provider: ' + esc(p.provider || '?') + '</span>' +
      '</div>' +
    '</div>';
    if (hg.length) {
      html += '<div class="dash-card"><h3 class="dash-card__title">Authentication</h3>' + renderAuthTable(hg) + '</div>';
    }
  }

  else if (tool === 'domain_check') {
    var auth = result.authentication || {};
    var items = [];
    if (auth.spf)   items.push({ name: 'SPF',   status: auth.spf.status || '?',   detail: auth.spf.record || '' });
    if (auth.dkim)  items.push({ name: 'DKIM',  status: auth.dkim.status || '?',  detail: '' });
    if (auth.dmarc) items.push({ name: 'DMARC', status: auth.dmarc.status || '?', detail: auth.dmarc.record || '' });
    if (items.length) {
      html += '<div class="dash-card"><h3 class="dash-card__title">Authentication Records</h3>' + renderAuthTable(items) + '</div>';
    }
    if (result.reputation) {
      html += '<div class="dash-card"><h3 class="dash-card__title">Reputation</h3>' +
        '<p class="dash-detail-text">Score: ' + (result.reputation.score || '?') + ' / 100</p>' +
      '</div>';
    }
  }

  else if (tool === 'subject_test') {
    var subjects = result.results || [];
    if (subjects.length) {
      html += '<div class="dash-card"><h3 class="dash-card__title">Scored Subjects</h3><div class="dash-subject-list">';
      subjects.forEach(function(s, i) {
        html += '<div class="dash-subject-item">' +
          '<span class="dash-subject-rank">#' + (i + 1) + '</span>' +
          '<span class="dash-subject-text">' + esc(s.subject || '') + '</span>' +
          '<span class="dash-subject-score">' + (s.score || '?') + '</span>' +
          '<span class="dash-subject-grade dash-grade--' + gradeClass(s.grade) + '">' + esc(s.grade || '?') + '</span>' +
        '</div>';
      });
      html += '</div></div>';
    }
  }

  else if (tool === 'placement_test') {
    var summary = result.summary || {};
    html += '<div class="dash-card"><h3 class="dash-card__title">Placement Summary</h3>' +
      '<div class="dash-placement-grid">' +
        placementStatHtml('Inbox', summary.inbox || 0, 'green') +
        placementStatHtml('Spam', summary.spam || 0, 'red') +
        placementStatHtml('Not Found', summary.not_found || 0, 'yellow') +
      '</div>' +
    '</div>';
  }

  else if (tool === 'header_analysis') {
    var auth2 = result.authentication_results || {};
    var items2 = [];
    for (var key in auth2) {
      items2.push({ name: key.toUpperCase(), status: auth2[key] || 'none', detail: '' });
    }
    if (items2.length) {
      html += '<div class="dash-card"><h3 class="dash-card__title">Auth Results</h3>' + renderAuthTable(items2) + '</div>';
    }
    var s = result.summary || {};
    html += '<div class="dash-card"><h3 class="dash-card__title">Summary</h3>' +
      '<p class="dash-detail-text">Hops: ' + (s.total_hops || 0) +
      ' | All encrypted: ' + (s.all_encrypted ? 'Yes' : 'No') +
      ' | Auth pass: ' + (s.auth_pass_count || 0) +
      ' | Auth fail: ' + (s.auth_fail_count || 0) +
      ' | Delay: ' + (s.total_delay_seconds || 0) + 's</p>' +
    '</div>';
  }

  else if (tool === 'email_verify') {
    html += '<div class="dash-card"><h3 class="dash-card__title">Verification Result</h3>' +
      '<p class="dash-detail-text">' +
        'Verdict: <strong>' + esc(result.verdict || '?') + '</strong>' +
        (result.reason ? ' — ' + esc(result.reason) : '') +
      '</p>' +
    '</div>';
  }

  else if (tool === 'copy_analysis') {
    var spam = result.spam || {};
    var copy = result.copy || {};
    html += '<div class="dash-card"><h3 class="dash-card__title">Scores</h3>' +
      '<div class="dash-placement-grid">' +
        placementStatHtml('Spam Risk', spam.score != null ? spam.score : '?', spam.score > 50 ? 'red' : 'green') +
        placementStatHtml('Copy Score', copy.score != null ? copy.score : '?', copy.score >= 70 ? 'green' : 'yellow') +
      '</div>' +
    '</div>';
  }

  return html;
}

function renderAuthTable(items) {
  var html = '<div class="dash-auth-table">';
  items.forEach(function(item) {
    var status = (item.status || item.result || '').toLowerCase();
    var cls = status === 'pass' ? 'green' : status === 'fail' ? 'red' : 'yellow';
    html += '<div class="dash-auth-row">' +
      '<span class="dash-auth-name">' + esc(item.name || item.protocol || '') + '</span>' +
      '<span class="dash-auth-status dash-auth-status--' + cls + '">' + esc(status || '?') + '</span>' +
      (item.detail ? '<span class="dash-auth-detail">' + esc(String(item.detail).substring(0, 80)) + '</span>' : '') +
    '</div>';
  });
  html += '</div>';
  return html;
}

function placementStatHtml(label, value, color) {
  return '<div class="dash-placement-stat">' +
    '<span class="dash-placement-stat__num dash-placement-stat--' + color + '">' + value + '</span>' +
    '<span class="dash-placement-stat__label">' + esc(label) + '</span>' +
  '</div>';
}

// ══════════════════════════════════════════════════════
//  BLACKLIST VIEW
// ══════════════════════════════════════════════════════
function renderBlacklistView() {
  var main = $('#dashMain');
  main.innerHTML = '<div class="dash-view">' +
    '<h2 class="dash-view__title">Blacklist Monitor</h2>' +
    '<p class="dash-view__sub">Monitor your domains across 110+ blocklists.</p>' +
    '<div id="blContent"><div class="dash-loading-sm"><div class="loading-ring"></div></div></div>' +
    '<a href="/blacklist-monitor" class="dash-tool-link">Open Blacklist Monitor &rarr;</a>' +
  '</div>';

  apiFetch('/api/monitors').then(function(data) {
    var container = document.getElementById('blContent');
    if (!container) return;
    if (!data || !data.monitors || !data.monitors.length) {
      container.innerHTML = '<p class="dash-empty-hint">No domains monitored yet. <a href="/blacklist-monitor">Add one</a></p>';
      return;
    }
    var html = '<div class="dash-monitor-list">';
    data.monitors.forEach(function(m) {
      var last = m.last_scan || {};
      var listed = last.listed_count || 0;
      var cls = listed === 0 ? 'green' : listed <= 2 ? 'yellow' : 'red';
      html += '<div class="dash-monitor-item">' +
        '<div class="dash-monitor-item__info">' +
          '<strong>' + esc(m.domain) + '</strong>' +
          '<span>' + (m.ip || '') + '</span>' +
        '</div>' +
        '<span class="dash-monitor-item__status dash-monitor-item--' + cls + '">' +
          (listed === 0 ? 'Clean' : listed + ' listed') +
        '</span>' +
        '<span class="dash-monitor-item__date">' + formatDate(last.checked_at || m.last_checked_at) + '</span>' +
      '</div>';
    });
    html += '</div>';
    container.innerHTML = html;
  }).catch(function() {
    var c = document.getElementById('blContent');
    if (c) c.innerHTML = '<p class="dash-empty-hint">Could not load monitors.</p>';
  });
}

// ══════════════════════════════════════════════════════
//  WARMUP VIEW
// ══════════════════════════════════════════════════════
function renderWarmupView() {
  var main = $('#dashMain');
  main.innerHTML = '<div class="dash-view">' +
    '<h2 class="dash-view__title">Warmup Tracker</h2>' +
    '<p class="dash-view__sub">Track your email warmup campaigns.</p>' +
    '<div id="warmupContent"><div class="dash-loading-sm"><div class="loading-ring"></div></div></div>' +
    '<a href="/warmup" class="dash-tool-link">Open Warmup Tracker &rarr;</a>' +
  '</div>';

  apiFetch('/api/warmup/campaigns').then(function(data) {
    var container = document.getElementById('warmupContent');
    if (!container) return;
    if (!data || !data.campaigns || !data.campaigns.length) {
      container.innerHTML = '<p class="dash-empty-hint">No warmup campaigns yet. <a href="/warmup">Start one</a></p>';
      return;
    }
    var html = '<div class="dash-monitor-list">';
    data.campaigns.forEach(function(c) {
      var statusCls = c.status === 'active' ? 'green' : c.status === 'paused' ? 'yellow' : 'default';
      html += '<div class="dash-monitor-item">' +
        '<div class="dash-monitor-item__info">' +
          '<strong>' + esc(c.domain) + '</strong>' +
          '<span>' + esc(c.esp || '') + ' &middot; Day ' + (c.current_day || '?') + '</span>' +
        '</div>' +
        '<span class="dash-monitor-item__status dash-monitor-item--' + statusCls + '">' + esc(c.status || '?') + '</span>' +
      '</div>';
    });
    html += '</div>';
    container.innerHTML = html;
  }).catch(function() {
    var c = document.getElementById('warmupContent');
    if (c) c.innerHTML = '<p class="dash-empty-hint">Could not load campaigns.</p>';
  });
}

// ══════════════════════════════════════════════════════
//  RECENT LIST (shared by overview + tool views)
// ══════════════════════════════════════════════════════
function renderRecentList(results, containerId) {
  var container = document.getElementById(containerId);
  if (!container) return;

  if (!results.length) {
    container.innerHTML = '<p class="dash-empty-hint">No results yet. Run a test to see history here.</p>';
    return;
  }

  var html = '<div class="db-recent-list">';
  results.forEach(function(r, i) {
    var toolLabel = TOOL_LABELS[r.tool] || r.tool;
    var color = TOOL_COLORS[r.tool] || '#64748b';
    var gradeCls = gradeClass(r.grade);
    html += '<div class="db-recent-item" style="animation-delay:' + (i * 25) + 'ms" data-id="' + r.id + '">' +
      '<div class="db-recent-item__tool" style="color:' + color + '">' +
        '<span class="db-recent-item__tool-dot" style="background:' + color + '"></span>' +
        esc(toolLabel) +
      '</div>' +
      '<div class="db-recent-item__main">' +
        '<span class="db-recent-item__subject">' + esc(r.input_summary || 'Untitled') + '</span>' +
        '<span class="db-recent-item__meta">' + formatDate(r.created_at) + '</span>' +
      '</div>' +
      '<div class="db-recent-item__scores">' +
        (r.grade ? '<span class="dash-grade dash-grade--' + gradeCls + '">' + esc(r.grade) + '</span>' : '') +
        (r.score != null ? '<span class="db-recent-score">' + r.score + '</span>' : '') +
      '</div>' +
    '</div>';
  });
  html += '</div>';
  container.innerHTML = html;

  // Click to view detail
  container.querySelectorAll('.db-recent-item').forEach(function(item) {
    item.addEventListener('click', function() {
      var id = this.dataset.id;
      if (id) showDetail(parseInt(id));
    });
  });
}

// ══════════════════════════════════════════════════════
//  API HELPER
// ══════════════════════════════════════════════════════
var PRO_UPGRADE_HTML = '<div class="dash-upgrade-inline">' +
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>' +
  '<span>Upgrade to <strong>Pro</strong> to save test history and track trends.</span>' +
  '<a href="/pricing">View Plans &rarr;</a>' +
'</div>';

function apiFetch(url) {
  return fetch(url).then(function(res) {
    if (res.status === 403) return { __gated: true };
    if (!res.ok) return null;
    return res.json();
  }).catch(function() { return null; });
}

// ══════════════════════════════════════════════════════
//  UTILITIES
// ══════════════════════════════════════════════════════
function esc(str) {
  return String(str == null ? '' : str)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function formatDate(dateStr) {
  if (!dateStr) return '';
  try {
    var d = new Date(dateStr);
    var now = new Date();
    var diff = now - d;
    if (diff < 60000) return 'Just now';
    if (diff < 3600000) return Math.floor(diff / 60000) + 'm ago';
    if (diff < 86400000) return Math.floor(diff / 3600000) + 'h ago';
    if (diff < 604800000) return Math.floor(diff / 86400000) + 'd ago';
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  } catch(e) { return ''; }
}

function shortDate(dateStr) {
  if (!dateStr) return '';
  try {
    var parts = dateStr.split('-');
    return parseInt(parts[1]) + '/' + parseInt(parts[2]);
  } catch(e) { return ''; }
}

function gradeClass(grade) {
  if (!grade) return 'default';
  var g = grade.toUpperCase();
  if (g === 'A' || g === 'A+') return 'green';
  if (g === 'B' || g === 'B+') return 'blue';
  if (g === 'C') return 'yellow';
  return 'red';
}

// ── Boot ──
renderOverview();
