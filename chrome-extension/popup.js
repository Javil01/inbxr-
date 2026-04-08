// InbXr Chrome Extension — Popup
// Reads a domain from the input, calls the Domain Signal Score API,
// and renders the result inline. Also keeps a history of recent checks
// in chrome.storage.local so users can re-click without retyping.

(function () {
  "use strict";

  var API_BASE = "https://inbxr.us";
  var HISTORY_KEY = "inbxr_history";
  var MAX_HISTORY = 5;

  var form = document.getElementById("domainForm");
  var input = document.getElementById("domainInput");
  var submitBtn = document.getElementById("submitBtn");
  var loadingEl = document.getElementById("loading");
  var errorEl = document.getElementById("error");
  var resultEl = document.getElementById("result");
  var historyEl = document.getElementById("history");
  var historyList = document.getElementById("historyList");

  // Render history on load
  loadHistory(function (items) {
    renderHistory(items);
  });

  // Auto-focus input
  setTimeout(function () {
    input.focus();
  }, 50);

  // Auto-populate from current tab URL
  if (typeof chrome !== "undefined" && chrome.tabs && chrome.tabs.query) {
    chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
      if (tabs && tabs[0] && tabs[0].url) {
        try {
          var u = new URL(tabs[0].url);
          if (u.hostname && u.hostname !== "newtab" && !u.hostname.startsWith("chrome")) {
            input.value = u.hostname.replace(/^www\./, "");
            input.select();
          }
        } catch (e) {}
      }
    });
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    runDiagnostic(input.value);
  });

  function runDiagnostic(rawDomain) {
    var domain = normalizeDomain(rawDomain);
    if (!domain || domain.indexOf(".") === -1) {
      showError("Enter a valid sending domain (e.g. yourcompany.com).");
      return;
    }

    showLoading();

    fetch(API_BASE + "/api/badge/" + encodeURIComponent(domain) + ".json", {
      method: "GET",
      headers: { Accept: "application/json" },
    })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (data) {
        if (!data.ok) {
          showError(data.error || "Could not score that domain.");
          return;
        }
        showResult(domain, data);
        saveToHistory(domain, data.score, data.grade);
      })
      .catch(function (err) {
        showError("Network error. " + (err.message || ""));
      });
  }

  function normalizeDomain(raw) {
    if (!raw) return "";
    var s = String(raw).trim().toLowerCase();
    s = s.replace(/^https?:\/\//, "");
    s = s.replace(/\/.*$/, "");
    s = s.split(":")[0];
    s = s.replace(/^www\./, "");
    return s;
  }

  function showLoading() {
    errorEl.hidden = true;
    resultEl.hidden = true;
    historyEl.hidden = true;
    loadingEl.hidden = false;
    submitBtn.disabled = true;
  }

  function showError(msg) {
    loadingEl.hidden = true;
    resultEl.hidden = true;
    errorEl.hidden = false;
    errorEl.textContent = msg;
    submitBtn.disabled = false;
  }

  function showResult(domain, data) {
    loadingEl.hidden = true;
    errorEl.hidden = true;
    submitBtn.disabled = false;

    document.getElementById("scoreValue").textContent = data.score != null ? data.score : "—";
    var gradePill = document.getElementById("gradePill");
    var grade = data.grade || "F";
    gradePill.className = "ext-grade-pill ext-grade-pill--" + grade;
    gradePill.textContent = grade;

    // The badge JSON doesn't include auth/rep breakdown, so we hide
    // those values unless a future API upgrade exposes them. For now
    // we show the total and the link to the full report.
    document.getElementById("authValue").textContent = "—";
    document.getElementById("repValue").textContent = "—";

    document.getElementById("reportLink").href = data.report_url || (API_BASE + "/?domain=" + encodeURIComponent(domain));

    resultEl.hidden = false;

    loadHistory(function (items) { renderHistory(items); });
  }

  function loadHistory(cb) {
    if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) {
      chrome.storage.local.get([HISTORY_KEY], function (result) {
        cb(result[HISTORY_KEY] || []);
      });
    } else {
      cb([]);
    }
  }

  function saveToHistory(domain, score, grade) {
    loadHistory(function (items) {
      items = items.filter(function (i) { return i.domain !== domain; });
      items.unshift({ domain: domain, score: score, grade: grade, ts: Date.now() });
      items = items.slice(0, MAX_HISTORY);
      if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) {
        chrome.storage.local.set({ [HISTORY_KEY]: items });
      }
    });
  }

  function renderHistory(items) {
    if (!items || items.length === 0) {
      historyEl.hidden = true;
      return;
    }
    historyEl.hidden = false;
    historyList.innerHTML = "";
    items.forEach(function (i) {
      var li = document.createElement("li");
      li.innerHTML = "<span>" + escapeHtml(i.domain) + "</span><b>" + i.score + " " + i.grade + "</b>";
      li.addEventListener("click", function () {
        input.value = i.domain;
        runDiagnostic(i.domain);
      });
      historyList.appendChild(li);
    });
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
})();
