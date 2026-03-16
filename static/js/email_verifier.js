/* ================================================================
   INBXR — Email Verifier  (email_verifier.js)
   ================================================================ */
(function () {
  "use strict";

  const form         = document.getElementById("verifyForm");
  const emailInput   = document.getElementById("verifyEmail");
  const submitBtn    = document.getElementById("verifyBtn");
  const formCard     = document.getElementById("formCard");
  const loading      = document.getElementById("verifyLoading");
  const results      = document.getElementById("verifyResults");
  const againBtn     = document.getElementById("verifyAgainBtn");

  if (!form) return;

  // ── Loading messages ──────────────────────────────────
  const MESSAGES = [
    "Checking email syntax…",
    "Looking up DNS records…",
    "Detecting disposable domains…",
    "Connecting to mail server…",
    "Verifying mailbox…",
  ];

  let msgInterval;
  function startLoadingMessages() {
    let i = 0;
    const el = document.getElementById("loadingMsg");
    msgInterval = setInterval(() => {
      i = (i + 1) % MESSAGES.length;
      el.textContent = MESSAGES[i];
    }, 2500);
  }
  function stopLoadingMessages() { clearInterval(msgInterval); }

  // ── Form submit ───────────────────────────────────────
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const email = emailInput.value.trim();
    if (!email) { emailInput.focus(); return; }

    // Show loading
    formCard.classList.add("hidden");
    results.classList.add("hidden");
    loading.classList.remove("hidden");
    submitBtn.querySelector(".btn-text").textContent = "Verifying…";
    submitBtn.querySelector(".btn-spinner").classList.remove("hidden");
    submitBtn.disabled = true;
    startLoadingMessages();

    try {
      const res = await fetch("/api/verify-email", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Verification failed");
      renderResults(data);
    } catch (err) {
      showToast(err.message || "Something went wrong. Please try again.", 'error');
      resetForm();
    } finally {
      stopLoadingMessages();
    }
  });

  // ── Reset ─────────────────────────────────────────────
  function resetForm() {
    loading.classList.add("hidden");
    results.classList.add("hidden");
    formCard.classList.remove("hidden");
    submitBtn.querySelector(".btn-text").textContent = "Verify Email";
    submitBtn.querySelector(".btn-spinner").classList.add("hidden");
    submitBtn.disabled = false;
    emailInput.focus();
  }

  againBtn.addEventListener("click", resetForm);

  // ── Render results ────────────────────────────────────
  function renderResults(data) {
    loading.classList.add("hidden");
    results.classList.remove("hidden");

    renderVerdict(data);
    renderMeta(data);
    renderChecks(data);
    renderRisks(data);
    renderMx(data);
    renderNextSteps(data);
  }

  // ── Verdict banner ────────────────────────────────────
  function renderVerdict(data) {
    const el = document.getElementById("evVerdict");
    const icon = document.getElementById("evVerdictIcon");
    const label = document.getElementById("evVerdictLabel");
    const detail = document.getElementById("evVerdictDetail");
    const scoreNum = el.querySelector(".ev-verdict__score-num");

    // Remove old classes
    el.className = "ev-verdict";

    const v = data.verdict;
    el.classList.add("ev-verdict--" + v);

    const icons = {
      valid:   "&#10003;",
      invalid: "&#10007;",
      risky:   "&#9888;",
      unknown: "&#63;",
    };
    const labels = {
      valid:   "Valid & Deliverable",
      invalid: "Invalid",
      risky:   "Risky",
      unknown: "Unknown",
    };

    icon.innerHTML = icons[v] || "?";
    label.textContent = labels[v] || v;
    detail.textContent = data.verdict_detail || "";
    scoreNum.textContent = data.score;

    // Color the score
    const s = data.score;
    scoreNum.className = "ev-verdict__score-num";
    if (s >= 80) scoreNum.classList.add("score--good");
    else if (s >= 50) scoreNum.classList.add("score--warn");
    else scoreNum.classList.add("score--bad");
  }

  // ── Meta info ─────────────────────────────────────────
  function renderMeta(data) {
    const el = document.getElementById("evMeta");
    const free = data.checks.free_provider;
    const domain = data.domain || "—";

    el.innerHTML = `
      <div class="ev-meta__item">
        <span class="ev-meta__label">Email</span>
        <span class="ev-meta__value">${esc(data.email)}</span>
      </div>
      <div class="ev-meta__item">
        <span class="ev-meta__label">Domain</span>
        <span class="ev-meta__value">${esc(domain)}</span>
      </div>
      <div class="ev-meta__item">
        <span class="ev-meta__label">Type</span>
        <span class="ev-meta__value">${free && free.is_free ? "Free Provider" : "Business Domain"}</span>
      </div>
    `;
  }

  // ── Checks grid ───────────────────────────────────────
  function renderChecks(data) {
    const el = document.getElementById("evChecks");
    const c = data.checks;
    const checks = [
      { label: "Syntax",        pass: c.syntax.pass,         detail: c.syntax.detail },
      { label: "Domain / MX",   pass: c.domain.pass,         detail: c.domain.detail },
      { label: "Disposable",    pass: c.disposable.pass,     detail: c.disposable.detail },
      { label: "Catch-All",     pass: !c.catch_all.is_catch_all, detail: c.catch_all.detail },
      { label: "Mailbox",       pass: c.mailbox.exists === true, detail: c.mailbox.detail,
        neutral: c.mailbox.exists === null },
    ];

    el.innerHTML = checks.map(ch => {
      let cls = "ev-check";
      let icon;
      if (ch.neutral) {
        cls += " ev-check--neutral";
        icon = "—";
      } else if (ch.pass) {
        cls += " ev-check--pass";
        icon = "&#10003;";
      } else {
        cls += " ev-check--fail";
        icon = "&#10007;";
      }
      return `
        <div class="${cls}">
          <span class="ev-check__icon">${icon}</span>
          <div class="ev-check__body">
            <span class="ev-check__label">${esc(ch.label)}</span>
            <span class="ev-check__detail">${esc(ch.detail)}</span>
          </div>
        </div>`;
    }).join("");
  }

  // ── Risk factors ──────────────────────────────────────
  function renderRisks(data) {
    const section = document.getElementById("evRiskSection");
    const el = document.getElementById("evRisks");
    const risks = data.risk_factors || [];
    if (!risks.length) { section.classList.add("hidden"); return; }

    section.classList.remove("hidden");
    const labels = {
      disposable_domain: "Disposable / temporary email domain — high bounce risk",
      catch_all:         "Catch-all server — mailbox existence cannot be confirmed",
      greylisted:        "Server greylisted the verification attempt — result may be inconclusive",
    };
    el.innerHTML = risks.map(r =>
      `<div class="ev-risk"><span class="ev-risk__icon">&#9888;</span> ${esc(labels[r] || r)}</div>`
    ).join("");
  }

  // ── MX records table ──────────────────────────────────
  function renderMx(data) {
    const section = document.getElementById("evMxSection");
    const body = document.getElementById("evMxBody");
    const mx = data.checks.mx_records || [];
    if (!mx.length) { section.classList.add("hidden"); return; }

    section.classList.remove("hidden");
    body.innerHTML = mx.map(r =>
      `<tr><td>${r.priority}</td><td>${esc(r.host)}</td></tr>`
    ).join("");
  }

  // ── Next steps CTAs ───────────────────────────────
  function renderNextSteps(data) {
    const el = document.getElementById("evNextSteps");
    if (!el) return;

    const actions = [];
    const domain = data.domain || "";

    // Valid email → check domain reputation
    if (data.verdict === "valid" && domain) {
      actions.push({
        icon: "&#10003;",
        title: "Email is Valid",
        desc: "Now check if the sending domain has reputation issues that could affect delivery.",
        href: "/sender?domain=" + encodeURIComponent(domain),
        btn: "Check Domain Reputation",
        color: "green",
      });
    }

    // Risky → specific guidance
    if (data.verdict === "risky") {
      if (data.checks.disposable.is_disposable) {
        actions.push({
          icon: "&#9888;",
          title: "Disposable Email Detected",
          desc: "This is a temporary email that will stop working. Remove it from your list to protect your bounce rate.",
          href: null,
          btn: null,
          color: "orange",
        });
      }
      if (data.checks.catch_all.is_catch_all && domain) {
        actions.push({
          icon: "&#9888;",
          title: "Catch-All Domain",
          desc: "This server accepts all addresses — the mailbox may not actually exist. Check domain reputation for more signals.",
          href: "/sender?domain=" + encodeURIComponent(domain),
          btn: "Check Domain Reputation",
          color: "orange",
        });
      }
    }

    // Invalid → suggest sender check for the domain
    if (data.verdict === "invalid" && domain && data.checks.domain.pass) {
      actions.push({
        icon: "&#10007;",
        title: "Mailbox Doesn't Exist",
        desc: "The domain is valid but this specific mailbox was rejected. Remove this address from your list.",
        href: null,
        btn: null,
        color: "red",
      });
    }

    // Always offer to check another or check domain if we have one
    if (domain && data.verdict !== "valid") {
      actions.push({
        icon: "&#128269;",
        title: "Check Domain Health",
        desc: "Run a full sender check on " + domain + " to see authentication records, blocklist status, and ESP detection.",
        href: "/sender?domain=" + encodeURIComponent(domain),
        btn: "Open Sender Check",
        color: "blue",
      });
    }

    if (!actions.length) { el.classList.add("hidden"); return; }

    el.classList.remove("hidden");
    el.innerHTML = '<div class="et-next-steps">' +
      actions.map(function(a) {
        if (!a.href) {
          return '<div class="et-next-step et-next-step--' + a.color + '">' +
            '<span class="et-next-step__icon">' + a.icon + '</span>' +
            '<div class="et-next-step__body">' +
              '<strong class="et-next-step__title">' + esc(a.title) + '</strong>' +
              '<p class="et-next-step__desc">' + esc(a.desc) + '</p>' +
            '</div></div>';
        }
        return '<a href="' + a.href + '" class="et-next-step et-next-step--' + a.color + '">' +
          '<span class="et-next-step__icon">' + a.icon + '</span>' +
          '<div class="et-next-step__body">' +
            '<strong class="et-next-step__title">' + esc(a.title) + '</strong>' +
            '<p class="et-next-step__desc">' + esc(a.desc) + '</p>' +
          '</div>' +
          '<span class="et-next-step__btn">' + esc(a.btn) + ' &rarr;</span></a>';
      }).join("") + '</div>';
  }

  // ── Helpers ───────────────────────────────────────────
  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s || "";
    return d.innerHTML;
  }

  // ── Auto-run from URL params ──────────────────────────
  const params = new URLSearchParams(window.location.search);
  const autoEmail = params.get("email");
  if (autoEmail) {
    emailInput.value = autoEmail;
    form.dispatchEvent(new Event("submit"));
  }
})();
