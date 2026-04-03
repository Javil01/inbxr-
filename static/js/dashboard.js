/* ══════════════════════════════════════════════════════
   InbXr — Dashboard (API-driven, sidebar layout)
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
var TOOL_URLS = {
  email_test:      '/',
  domain_check:    '/sender',
  subject_test:    '/subject-scorer',
  placement_test:  '/placement',
  header_analysis: '/header-analyzer',
  copy_analysis:   '/analyzer',
  email_verify:    '/email-verifier',
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
function setActiveNav(el) {
  $$('.dash-nav__item').forEach(function(n) {
    n.classList.remove('dash-nav__item--active');
  });
  if (el) el.classList.add('dash-nav__item--active');
  // Close mobile sidebar
  var sidebar = document.getElementById('dashSidebar');
  if (sidebar) sidebar.classList.remove('dash-sidebar--open');
}

// Overview link
$$('.dash-nav__item[data-view]').forEach(function(item) {
  item.addEventListener('click', function(e) {
    e.preventDefault();
    if (currentView === 'overview') return;
    currentView = 'overview';
    setActiveNav(this);
    var main = $('#dashMain');
    main.innerHTML = '<div class="dash-loading"><div class="loading-ring"></div></div>';
    renderOverview();
  });
});

// Tool links — load in iframe
$$('.dash-nav__item[data-tool]').forEach(function(item) {
  item.addEventListener('click', function(e) {
    e.preventDefault();
    var toolUrl = this.dataset.tool;
    currentView = toolUrl;
    setActiveNav(this);
    loadToolInDashboard(toolUrl);
  });
});

// ══════════════════════════════════════════════════════
//  LOAD TOOL IN DASHBOARD (iframe)
// ══════════════════════════════════════════════════════
function loadToolInDashboard(url) {
  var main = $('#dashMain');
  // Add ?embed=1 so tool pages can optionally hide their own header/footer
  var embedUrl = url + (url.indexOf('?') > -1 ? '&' : '?') + 'embed=1';
  main.innerHTML = '<iframe class="dash-tool-frame" src="' + embedUrl + '" frameborder="0" allowfullscreen></iframe>';
}

// Quick action cards — intercept to load in dashboard instead of navigating
document.addEventListener('click', function(e) {
  var card = e.target.closest('.dash-action-card');
  if (!card) return;
  e.preventDefault();
  var href = card.getAttribute('href');
  if (!href) return;
  currentView = href;
  // Highlight matching sidebar item
  var match = document.querySelector('.dash-nav__item[data-tool="' + href + '"]');
  setActiveNav(match);
  loadToolInDashboard(href);
});

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

  // Last scan results (all tiers)
  loadLastScan();

  // Domain health
  loadDomainHealth();

  // ESP deliverability health
  loadEspHealth();

  // Trend filter buttons
  setTimeout(function() {
    var filters = document.getElementById('trendFilters');
    if (filters) {
      filters.addEventListener('click', function(e) {
        var btn = e.target.closest('.dash-trend-btn');
        if (!btn) return;
        $$('.dash-trend-btn', filters).forEach(function(b) { b.classList.remove('dash-trend-btn--active'); });
        btn.classList.add('dash-trend-btn--active');
        var days = parseInt(btn.dataset.days) || 30;
        var chart = document.getElementById('overviewChart');
        if (chart) chart.innerHTML = '<div class="dash-loading-sm"><div class="loading-ring"></div></div>';
        apiFetch('/api/history/trend?days=' + days).then(function(d) {
          if (d && d.trend) renderTrendChart(d.trend, 'overviewChart');
        });
      });
    }
  }, 0);
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

function buildAssistantTeaser() {
  if (window.__userTier !== 'free') return '';
  return '<div class="dash-assistant-teaser">' +
    '<div class="dash-assistant-teaser__icon">' +
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="32" height="32"><path d="M12 2a4 4 0 014 4v1a1 1 0 01-1 1H9a1 1 0 01-1-1V6a4 4 0 014-4z"/><path d="M9 8v1a3 3 0 006 0V8"/><path d="M12 14v3"/><path d="M7 17h10a2 2 0 012 2v1H5v-1a2 2 0 012-2z"/></svg>' +
    '</div>' +
    '<div class="dash-assistant-teaser__content">' +
      '<h3 class="dash-assistant-teaser__title">Need Expert Help With Your Results?</h3>' +
      '<p class="dash-assistant-teaser__text">Our AI Email Expert reads your test results and gives you personalized, step-by-step guidance to fix deliverability issues, improve your sender reputation, and land in the inbox.</p>' +
      '<a href="/pricing" class="dash-assistant-teaser__cta">Unlock Email Expert &rarr;</a>' +
    '</div>' +
  '</div>';
}

function buildOverviewShell(s) {
  var c = window.__dashCredits || {};
  return '<div class="dash-view">' +
    buildCreditsBar(c) +
    buildOnboardingCard() +
    '<h2 class="dash-view__title">Overview</h2>' +
    '<div class="db-stats">' +
      statCardHtml('statTotal', s.total_checks || 0, 'Total Tests') +
      statCardHtml('statWeek', s.checks_this_week || 0, 'This Week') +
      statCardHtml('statAvg', s.avg_score != null ? s.avg_score : '--', 'Avg Score') +
      statCardHtml('statGrade', s.best_grade || '--', 'Best Grade') +
    '</div>' +
    buildQuickActions() +
    buildLastScanCard() +
    buildAssistantTeaser() +
    buildDomainHealthCard() +
    buildEspHealthCard() +
    '<div class="dash-row">' +
      '<div class="dash-card dash-card--wide">' +
        '<div class="dash-card__header dash-card__header--row">' +
          '<h3 class="dash-card__title">Score Trend</h3>' +
          '<div class="dash-trend-filters" id="trendFilters">' +
            '<button class="dash-trend-btn dash-trend-btn--active" data-days="7">7d</button>' +
            '<button class="dash-trend-btn" data-days="30">30d</button>' +
            '<button class="dash-trend-btn" data-days="90">90d</button>' +
          '</div>' +
        '</div>' +
        '<div id="overviewChart" class="db-chart" style="min-height:160px"><div class="dash-loading-sm"><div class="loading-ring"></div></div></div>' +
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
  var scores = trend.map(function(t) { return t.avg_score || 0; });
  var avg = Math.round(scores.reduce(function(a, b) { return a + b; }, 0) / scores.length);
  var latest = scores[scores.length - 1];
  var prev = scores.length > 1 ? scores[scores.length - 2] : latest;
  var diff = latest - prev;
  var diffLabel = diff > 0 ? '+' + diff : '' + diff;
  var diffColor = diff >= 0 ? '#22c55e' : '#ef4444';

  var html = '<div class="db-trend-summary">' +
    '<span class="db-trend-avg">Avg: <strong>' + avg + '</strong></span>' +
    '<span class="db-trend-latest">Latest: <strong>' + latest + '</strong></span>' +
    (diff !== 0 ? '<span class="db-trend-diff" style="color:' + diffColor + '">' + diffLabel + ' vs prior day</span>' : '') +
  '</div>';

  html += '<div class="db-chart__bars">';
  trend.forEach(function(t, i) {
    var score = t.avg_score || 0;
    var h = (score / maxScore) * 100;
    var day = shortDate(t.day);
    var barColor = score >= 70 ? '#22c55e' : score >= 40 ? '#f59e0b' : '#ef4444';
    html += '<div class="db-chart__group" style="animation-delay:' + (i * 30) + 'ms">' +
      '<div class="db-chart__tooltip">' + score + '<br><small>' + t.count + ' test' + (t.count !== 1 ? 's' : '') + '</small></div>' +
      '<div class="db-chart__bar-pair">' +
        '<div class="db-chart__bar db-chart__bar--score" style="height:' + h + '%;background:' + barColor + '"></div>' +
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

// ══════════════════════════════════════════════════════
//  EMAIL EXPERT ASSISTANT (Pro/Agency)
// ══════════════════════════════════════════════════════
(function() {
  var panel = document.getElementById('eaPanel');
  if (!panel) return; // not rendered for free tier

  var messagesEl = document.getElementById('eaMessages');
  var inputEl = document.getElementById('eaInput');
  var sendBtn = document.getElementById('eaSend');
  var closeBtn = document.getElementById('eaClose');
  var openBtn = document.getElementById('openAssistant');

  var messages = [];
  var isLoading = false;

  var GREETING = "Hi! I'm your InbXr Email Expert. I have access to your test results and can help you improve your email deliverability.\n\nAsk me anything — like **\"Why are my emails going to spam?\"** or **\"How do I fix my DMARC?\"** and I'll give you specific advice based on your data.";

  function openAssistant() {
    messages = [];
    panel.classList.add('ea-panel--open');
    messagesEl.innerHTML = '';
    addMsg('assistant', GREETING);
    inputEl.focus();
  }

  function closeAssistant() {
    panel.classList.remove('ea-panel--open');
  }

  if (openBtn) {
    openBtn.addEventListener('click', function(e) {
      e.preventDefault();
      openAssistant();
    });
  }

  closeBtn.addEventListener('click', closeAssistant);

  function sendMessage() {
    var text = inputEl.value.trim();
    if (!text || isLoading) return;

    inputEl.value = '';
    addMsg('user', text);
    messages.push({ role: 'user', content: text });

    isLoading = true;
    var loadingEl = addLoading();

    fetch('/api/assistant/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages: messages })
    })
    .then(function(res) {
      var is429 = res.status === 429;
      return res.json().then(function(data) {
        data.__is429 = is429;
        return data;
      });
    })
    .then(function(data) {
      removeLoading(loadingEl);
      if (data.__is429) {
        var msg = data.error || 'Daily limit reached.';
        addMsg('assistant', msg + (data.upgrade_url ? '\n\nUpgrade to **Agency** for unlimited monthly conversations.' : ''));
      } else if (data.error) {
        addMsg('assistant', 'Sorry, I ran into an issue: ' + data.error);
      } else {
        var reply = data.reply || 'Sorry, I could not generate a response.';
        addMsg('assistant', reply);
        messages.push({ role: 'assistant', content: reply });
        // Update remaining counter for Pro users
        if (data.remaining != null && data.monthly_limit) {
          updateRemainingCounter(data.remaining, data.monthly_limit);
        }
      }
    })
    .catch(function() {
      removeLoading(loadingEl);
      addMsg('assistant', 'Sorry, something went wrong. Please try again.');
    })
    .finally(function() {
      isLoading = false;
    });
  }

  sendBtn.addEventListener('click', sendMessage);
  inputEl.addEventListener('keydown', function(e) {
    if (e.key === 'Enter') sendMessage();
  });

  function addMsg(role, text) {
    var div = document.createElement('div');
    div.className = 'ea-msg ea-msg--' + role;
    var html = esc(text)
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/`(.*?)`/g, '<code>$1</code>')
      .replace(/\n/g, '<br>');
    div.innerHTML = html;
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return div;
  }

  function addLoading() {
    var div = document.createElement('div');
    div.className = 'ea-msg ea-msg--assistant ea-msg--loading';
    div.innerHTML = '<span class="ea-typing"><span></span><span></span><span></span></span>';
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return div;
  }

  function removeLoading(el) {
    if (el && el.parentNode) el.parentNode.removeChild(el);
  }

  function updateRemainingCounter(remaining, limit) {
    var counter = document.getElementById('eaCounter');
    if (!counter) {
      // Create counter element below header
      counter = document.createElement('div');
      counter.id = 'eaCounter';
      counter.className = 'ea-counter';
      panel.querySelector('.ea-panel__header').insertAdjacentElement('afterend', counter);
    }
    var used = limit - remaining;
    counter.innerHTML = '<span>' + used + ' of ' + limit + ' conversations used this month</span>' +
      (remaining <= 3 ? '<a href="/account">Upgrade for unlimited</a>' : '');
    counter.classList.toggle('ea-counter--low', remaining <= 3);
  }
})();

// ══════════════════════════════════════════════════════
//  ONBOARDING SYSTEM
// ══════════════════════════════════════════════════════

var OB_ICONS = {
  mail:   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18"><rect x="2" y="5" width="20" height="14" rx="2"/><path d="M2 5l10 8 10-8"/></svg>',
  zap:    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>',
  shield: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>',
  eye:    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>',
  type:   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18"><polyline points="4 7 4 4 20 4 20 7"/><line x1="9" y1="20" x2="15" y2="20"/><line x1="12" y1="4" x2="12" y2="20"/></svg>',
  check:  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><polyline points="20 6 9 17 4 12"/></svg>'
};

function buildOnboardingCard() {
  var ob = window.__onboarding;
  if (!ob || ob.all_complete || ob.dismissed) return '';

  var stepsHtml = '';
  ob.steps.forEach(function(step) {
    var done = step.completed;
    stepsHtml += '<div class="ob-step ' + (done ? 'ob-step--done' : 'ob-step--pending') + '">' +
      '<span class="ob-step__icon">' + (done ? OB_ICONS.check : (OB_ICONS[step.icon] || OB_ICONS.zap)) + '</span>' +
      '<div class="ob-step__body">' +
        '<strong>' + esc(step.title) + '</strong>' +
        '<p>' + esc(step.desc) + '</p>' +
      '</div>' +
      (done ? '' : '<a href="' + step.href + '" class="ob-step__cta ob-step__link">' + esc(step.cta) + ' &rarr;</a>') +
    '</div>';
  });

  return '<div class="ob-card" id="obCard">' +
    '<div class="ob-card__header">' +
      '<div>' +
        '<h3 class="ob-card__title">Getting Started</h3>' +
        '<span class="ob-card__progress">' + ob.done + ' of ' + ob.total + ' complete</span>' +
      '</div>' +
      '<button class="ob-card__dismiss" id="obDismiss" title="Dismiss">&times;</button>' +
    '</div>' +
    '<div class="ob-card__bar"><div class="ob-card__bar-fill" style="width:' + ob.pct + '%"></div></div>' +
    '<div class="ob-card__steps">' + stepsHtml + '</div>' +
  '</div>';
}

function wireOnboardingCard() {
  var dismissBtn = document.getElementById('obDismiss');
  if (dismissBtn) {
    dismissBtn.addEventListener('click', function() {
      fetch('/api/onboarding/dismiss', { method: 'POST' });
      var card = document.getElementById('obCard');
      if (card) { card.style.opacity = '0'; setTimeout(function() { card.remove(); }, 300); }
    });
  }
  // Wire CTA links to load tools in dashboard
  document.querySelectorAll('.ob-step__link').forEach(function(btn) {
    btn.addEventListener('click', function(e) {
      e.preventDefault();
      var href = this.getAttribute('href');
      var match = document.querySelector('.dash-nav__item[data-tool="' + href + '"]');
      if (match) {
        setActiveNav(match);
        loadToolInDashboard(href);
      } else {
        window.location.href = href;
      }
    });
  });
}

function showWelcomeModal() {
  if (!window.__isNewUser) return;
  var ob = window.__onboarding;
  if (!ob) return;

  var overlay = document.createElement('div');
  overlay.className = 'onboard-overlay';
  overlay.innerHTML =
    '<div class="onboard-modal">' +
      '<button class="onboard-close" id="obWelcomeClose">&times;</button>' +
      '<div class="onboard-header">' +
        '<svg viewBox="0 0 24 24" fill="none" stroke="#15c182" stroke-width="2" width="44" height="44"><path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>' +
        '<h2>Welcome to InbXr!</h2>' +
        '<p>Your email deliverability command center. Here\'s how to get the most out of it:</p>' +
      '</div>' +
      '<div class="onboard-steps">' +
        '<div class="onboard-step onboard-step--active">' +
          '<span class="onboard-step__num">1</span>' +
          '<div class="onboard-step__body">' +
            '<h3>Run an Email Test</h3>' +
            '<p>Send a real email and get instant SPF, DKIM, DMARC, spam risk, and content analysis.</p>' +
          '</div>' +
        '</div>' +
        '<div class="onboard-step">' +
          '<span class="onboard-step__num">2</span>' +
          '<div class="onboard-step__body">' +
            '<h3>Check Your Domain</h3>' +
            '<p>Verify your authentication setup and get an A-F sender health grade with fix instructions.</p>' +
          '</div>' +
        '</div>' +
        '<div class="onboard-step">' +
          '<span class="onboard-step__num">3</span>' +
          '<div class="onboard-step__body">' +
            '<h3>Set Up Monitoring</h3>' +
            '<p>Get automated alerts when you land on a blocklist or your DNS auth records change.</p>' +
          '</div>' +
        '</div>' +
      '</div>' +
      '<div class="onboard-footer">' +
        '<a href="/" class="ob-welcome__cta" id="obWelcomeStart">Start Email Test &rarr;</a>' +
        '<button class="onboard-skip" id="obWelcomeSkip">I\'ll explore on my own</button>' +
      '</div>' +
    '</div>';

  document.body.appendChild(overlay);

  function dismiss() {
    overlay.classList.add('onboard-overlay--exit');
    setTimeout(function() { overlay.remove(); }, 300);
  }

  document.getElementById('obWelcomeClose').addEventListener('click', dismiss);
  document.getElementById('obWelcomeSkip').addEventListener('click', dismiss);
  overlay.addEventListener('click', function(e) { if (e.target === overlay) dismiss(); });

  document.getElementById('obWelcomeStart').addEventListener('click', function(e) {
    e.preventDefault();
    dismiss();
    var match = document.querySelector('.dash-nav__item[data-tool="/"]');
    if (match) { setActiveNav(match); loadToolInDashboard('/'); }
    else { window.location.href = '/'; }
  });
}

// ══════════════════════════════════════════════════════
//  LAST SCAN CARD (all tiers)
// ══════════════════════════════════════════════════════
function buildLastScanCard() {
  return '<div class="dash-card" id="lastScanCard">' +
    '<div class="dash-card__header">' +
      '<h3 class="dash-card__title">Last Scan Results</h3>' +
    '</div>' +
    '<div id="lastScanContent"><div class="dash-loading-sm"><div class="loading-ring"></div></div></div>' +
  '</div>';
}

function loadLastScan() {
  apiFetch('/api/dashboard/last-scan').then(function(data) {
    var container = document.getElementById('lastScanContent');
    if (!container) return;

    if (!data || !data.scan) {
      container.innerHTML = '<div class="dash-lastscan-empty">' +
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="32" height="32"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>' +
        '<p>No scans yet. Run your first test to see results here.</p>' +
        '<a href="/" class="dash-lastscan__cta">Run Your First Test &rarr;</a>' +
      '</div>';
      return;
    }

    var s = data.scan;
    var toolLabel = TOOL_LABELS[s.tool] || s.tool;
    var toolUrl = TOOL_URLS[s.tool] || '/';
    var color = TOOL_COLORS[s.tool] || '#64748b';
    var gradeCls = gradeClass(s.grade);

    var html = '<div class="dash-lastscan">' +
      '<div class="dash-lastscan__main">' +
        '<div class="dash-lastscan__tool" style="color:' + color + '">' +
          '<span class="dash-lastscan__tool-dot" style="background:' + color + '"></span>' +
          esc(toolLabel) +
        '</div>' +
        '<div class="dash-lastscan__subject">' + esc(s.input_summary || 'Untitled') + '</div>' +
        '<div class="dash-lastscan__time">' + formatDate(s.created_at) + '</div>' +
      '</div>' +
      '<div class="dash-lastscan__scores">' +
        (s.grade ? '<span class="dash-lastscan__grade dash-grade dash-grade--' + gradeCls + '">' + esc(s.grade) + '</span>' : '') +
        (s.score != null ? '<span class="dash-lastscan__score">' + s.score + '<small>/100</small></span>' : '') +
      '</div>' +
      '<a href="' + toolUrl + '" class="dash-lastscan__cta">Run New Test &rarr;</a>' +
    '</div>';

    container.innerHTML = html;
  });
}

// ══════════════════════════════════════════════════════
//  DOMAIN HEALTH CARD (Feature 3)
// ══════════════════════════════════════════════════════
function buildDomainHealthCard() {
  return '<div class="dash-card">' +
    '<div class="dash-card__header">' +
      '<h3 class="dash-card__title">Domain Health</h3>' +
    '</div>' +
    '<div id="domainHealthOverview"><div class="dash-loading-sm"><div class="loading-ring"></div></div></div>' +
  '</div>';
}

function buildEspHealthCard() {
  var tier = window.__userTier || 'free';
  if (tier === 'free') {
    return '<div class="dash-card">' +
      '<div class="dash-card__header"><h3 class="dash-card__title">Deliverability Dashboard</h3></div>' +
      '<div style="padding:16px 0;text-align:center;">' +
        '<p style="font-size:0.85rem;color:var(--text-3);margin:0 0 12px;">Connect your email platform for always-on health monitoring.</p>' +
        '<a href="/pricing" class="dash-tool-link" style="color:var(--brand);">Upgrade to Pro &rarr;</a>' +
      '</div>' +
    '</div>';
  }
  return '<div class="dash-card">' +
    '<div class="dash-card__header">' +
      '<h3 class="dash-card__title">Deliverability Health</h3>' +
      '<a href="/deliverability" class="dash-tool-link" style="font-size:0.78rem;">View Dashboard &rarr;</a>' +
    '</div>' +
    '<div id="espHealthOverview"><div class="dash-loading-sm"><div class="loading-ring"></div></div></div>' +
  '</div>';
}

function loadEspHealth() {
  var tier = window.__userTier || 'free';
  if (tier === 'free') return;
  var container = document.getElementById('espHealthOverview');
  if (!container) return;

  apiFetch('/api/integrations/health').then(function(data) {
    if (!data || !data.has_data) {
      container.innerHTML = '<div style="padding:12px 0;text-align:center;">' +
        '<p style="font-size:0.85rem;color:var(--text-3);margin:0 0 10px;">No platforms connected yet.</p>' +
        '<a href="/account/integrations" class="dash-tool-link" style="color:var(--brand);">Connect a Platform &rarr;</a>' +
      '</div>';
      return;
    }

    var sc = data.overall_score;
    var gr = data.overall_grade;
    var color = sc >= 75 ? '#16a34a' : sc >= 50 ? '#ca8a04' : '#ef4444';
    var intgCount = data.integrations ? data.integrations.length : 0;

    var html = '<div style="display:flex;align-items:center;gap:16px;padding:8px 0;">' +
      '<div style="text-align:center;min-width:60px;">' +
        '<div style="font-size:1.8rem;font-weight:800;color:' + color + ';line-height:1;">' + sc + '</div>' +
        '<div style="font-size:0.75rem;font-weight:700;color:' + color + ';">' + esc(gr) + '</div>' +
      '</div>' +
      '<div style="flex:1;font-size:0.82rem;">' +
        '<div style="color:var(--text-2);margin-bottom:4px;">' + intgCount + ' platform' + (intgCount !== 1 ? 's' : '') + ' connected</div>' +
        '<div style="display:flex;gap:14px;flex-wrap:wrap;">' +
          '<span style="color:' + (data.avg_bounce_rate > 2 ? '#ef4444' : '#16a34a') + ';">Bounce: ' + data.avg_bounce_rate + '%</span>' +
          '<span style="color:' + (data.avg_complaint_rate > 0.1 ? '#ef4444' : '#16a34a') + ';">Complaints: ' + data.avg_complaint_rate + '%</span>' +
          '<span style="color:' + (data.avg_open_rate > 20 ? '#16a34a' : '#ca8a04') + ';">Opens: ' + data.avg_open_rate + '%</span>' +
        '</div>' +
      '</div>' +
    '</div>';

    if (data.warmup_accounts && data.warmup_accounts.length > 0) {
      html += '<div style="border-top:1px solid var(--border,#e5e7eb);padding-top:8px;margin-top:8px;font-size:0.78rem;color:var(--text-3);">';
      data.warmup_accounts.forEach(function(w) {
        var wc = w.score >= 70 ? '#16a34a' : w.score >= 40 ? '#ca8a04' : '#ef4444';
        html += '<div style="display:flex;justify-content:space-between;align-items:center;padding:3px 0;">' +
          '<span>' + esc(w.provider) + ' warmup</span>' +
          '<span style="font-weight:700;color:' + wc + ';">' + w.score + '/100</span>' +
        '</div>';
      });
      html += '</div>';
    }

    container.innerHTML = html;
  }).catch(function() {
    container.innerHTML = '<p style="font-size:0.82rem;color:var(--text-4);padding:8px 0;">Unable to load health data.</p>';
  });
}

function loadDomainHealth() {
  apiFetch('/api/monitors').then(function(data) {
    var container = document.getElementById('domainHealthOverview');
    if (!container) return;
    if (!data || !data.monitors || !data.monitors.length) {
      container.innerHTML = '<div class="dash-domain-health-empty">' +
        '<p>No domains monitored yet.</p>' +
        '<a href="/blacklist-monitor" class="dash-tool-link">Add a domain to track health &rarr;</a>' +
      '</div>';
      return;
    }

    var html = '<div class="dash-domain-grid">';
    data.monitors.forEach(function(m) {
      var last = m.last_scan || {};
      var listed = last.listed_count || 0;
      var total = last.total_checked || 0;
      var clean = total - listed;
      var pct = total > 0 ? Math.round((clean / total) * 100) : 100;
      var color = listed === 0 ? '#22c55e' : listed <= 2 ? '#f59e0b' : '#ef4444';
      var label = listed === 0 ? 'Healthy' : listed <= 2 ? 'Warning' : 'Critical';

      html += '<div class="dash-domain-card">' +
        '<div class="dash-domain-card__header">' +
          '<strong>' + esc(m.domain) + '</strong>' +
          '<span class="dash-domain-badge" style="background:' + color + '20;color:' + color + '">' + label + '</span>' +
        '</div>' +
        '<div class="dash-domain-score">' +
          '<svg viewBox="0 0 36 36" class="dash-domain-ring" width="52" height="52">' +
            '<path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="rgba(255,255,255,0.08)" stroke-width="3"/>' +
            '<path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="' + color + '" stroke-width="3" stroke-dasharray="' + pct + ', 100" stroke-linecap="round"/>' +
          '</svg>' +
          '<span class="dash-domain-pct" style="color:' + color + '">' + pct + '%</span>' +
        '</div>' +
        '<div class="dash-domain-meta">' +
          '<span>' + (listed === 0 ? 'Clean on all blocklists' : listed + ' blocklist' + (listed > 1 ? 's' : '')) + '</span>' +
          '<span>' + formatDate(last.checked_at || m.last_checked_at) + '</span>' +
        '</div>' +
      '</div>';
    });
    html += '</div>';
    container.innerHTML = html;
  });
}

// ── Boot ──
renderOverview();
wireOnboardingCard();
showWelcomeModal();
