/* ══════════════════════════════════════════════════════
   INBXR — DNS Record Generator
   ══════════════════════════════════════════════════════ */

'use strict';

const $ = (sel, ctx = document) => ctx.querySelector(sel);
const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

// ── Copy-to-clipboard ────────────────────────────────
function initCopyButtons() {
  $$('.dns-copy-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const targetId = btn.dataset.target;
      const el = document.getElementById(targetId);
      if (!el) return;
      const text = el.textContent.trim();
      navigator.clipboard.writeText(text).then(() => {
        const orig = btn.textContent;
        btn.textContent = 'Copied!';
        btn.classList.add('dns-copy-btn--ok');
        setTimeout(() => {
          btn.textContent = orig;
          btn.classList.remove('dns-copy-btn--ok');
        }, 1500);
      });
    });
  });
}

// ── Gather selected ESPs ─────────────────────────────
function getSelectedEsps() {
  return $$('input[name="esps"]:checked').map(cb => cb.value);
}

// ── Parse comma-separated IPs ────────────────────────
function parseIps(raw) {
  return raw.split(',').map(s => s.trim()).filter(Boolean);
}

// ══════════════════════════════════════════════════════
//  FORM SUBMIT
// ══════════════════════════════════════════════════════
$('#dnsForm').addEventListener('submit', async e => {
  e.preventDefault();

  const domain = $('#dnsDomain').value.trim();
  if (!domain) {
    $('#dnsDomain').focus();
    $('#dnsDomain').style.borderColor = 'var(--color-red)';
    return;
  }
  $('#dnsDomain').style.borderColor = '';

  const esps = getSelectedEsps();
  const dmarcPolicy = $('#dmarcPolicy').value;
  const spfMechanism = $('#spfMechanism').value;
  const ruaEmail = $('#ruaEmail').value.trim();
  const extraIps = parseIps($('#extraIps').value);
  const dkimSelector = $('#dkimSelector').value.trim();

  // Show spinner
  const btn = $('#dnsSubmitBtn');
  const btnText = btn.querySelector('.btn-text');
  const btnSpinner = btn.querySelector('.btn-spinner');
  btn.disabled = true;
  btnText.classList.add('hidden');
  btnSpinner.classList.remove('hidden');

  try {
    const resp = await fetch('/generate-dns', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        domain,
        type: 'all',
        esps,
        ips: extraIps,
        dmarc_policy: dmarcPolicy,
        spf_mechanism: spfMechanism,
        rua_email: ruaEmail || undefined,
        dkim_selector: dkimSelector || undefined,
        tls_rpt_email: ruaEmail || undefined,
      }),
    });

    const data = await resp.json();
    if (!resp.ok) {
      showToast(data.error || 'Generation failed.', 'error');
      return;
    }

    renderResults(data);
  } catch (err) {
    showToast('Request failed: ' + err.message, 'error');
  } finally {
    btn.disabled = false;
    btnText.classList.remove('hidden');
    btnSpinner.classList.add('hidden');
  }
});

// ══════════════════════════════════════════════════════
//  RENDER RESULTS
// ══════════════════════════════════════════════════════
function renderResults(data) {
  const records = data.records || {};
  const domain = data.domain;

  // SPF
  if (records.spf) {
    const spf = records.spf;
    $('#spfHost').textContent = domain;
    $('#spfValue').textContent = spf.value || spf.record || '';
    $('#spfNote').textContent = spf.note || '';
    $('#spfCard').classList.remove('hidden');
  }

  // DKIM
  if (records.dkim) {
    const dkim = records.dkim;
    const body = $('#dkimBody');
    body.innerHTML = '';

    if (dkim.instructions && dkim.instructions.length) {
      dkim.instructions.forEach(instr => {
        const div = document.createElement('div');
        div.className = 'dns-record-card__instruction';
        div.innerHTML = `<p>${escHtml(instr)}</p>`;
        body.appendChild(div);
      });
    }

    if (dkim.records && dkim.records.length) {
      dkim.records.forEach(rec => {
        const card = document.createElement('div');
        card.className = 'dns-dkim-sub';
        card.innerHTML = `
          <div class="dns-record-card__header">
            <span class="dns-record-card__type">${escHtml(rec.type || 'CNAME')}</span>
            <span class="dns-record-card__host">${escHtml(rec.host || '')}</span>
            <button type="button" class="dns-copy-btn" title="Copy to clipboard">Copy</button>
          </div>
          <pre class="dns-record-card__value">${escHtml(rec.value || '')}</pre>`;
        body.appendChild(card);

        // Bind copy
        const copyBtn = card.querySelector('.dns-copy-btn');
        const valueEl = card.querySelector('.dns-record-card__value');
        copyBtn.addEventListener('click', () => {
          navigator.clipboard.writeText(valueEl.textContent.trim()).then(() => {
            copyBtn.textContent = 'Copied!';
            copyBtn.classList.add('dns-copy-btn--ok');
            setTimeout(() => {
              copyBtn.textContent = 'Copy';
              copyBtn.classList.remove('dns-copy-btn--ok');
            }, 1500);
          });
        });
      });
    }

    if (dkim.note) {
      const note = document.createElement('p');
      note.className = 'dns-record-card__note';
      note.textContent = dkim.note;
      body.appendChild(note);
    }

    $('#dkimHost').textContent = dkim.host || '';
    $('#dkimCard').classList.remove('hidden');
  }

  // DMARC
  if (records.dmarc) {
    const dmarc = records.dmarc;
    $('#dmarcHost').textContent = `_dmarc.${domain}`;
    $('#dmarcValue').textContent = dmarc.value || dmarc.record || '';
    $('#dmarcNote').textContent = dmarc.note || '';
    $('#dmarcCard').classList.remove('hidden');
  }

  // MTA-STS
  if (records.mta_sts) {
    const mta = records.mta_sts;
    $('#mtaStsHost').textContent = `_mta-sts.${domain}`;
    $('#mtaStsValue').textContent = mta.value || mta.record || mta.dns_record || '';
    $('#mtaStsNote').textContent = mta.note || '';
    if (mta.policy_file) {
      $('#mtaStsNote').textContent += '\n\nPolicy file (host at https://mta-sts.' + domain + '/.well-known/mta-sts.txt):\n' + mta.policy_file;
    }
    $('#mtaStsCard').classList.remove('hidden');
  }

  // TLS-RPT
  if (records.tls_rpt) {
    const tls = records.tls_rpt;
    $('#tlsRptHost').textContent = `_smtp._tls.${domain}`;
    $('#tlsRptValue').textContent = tls.value || tls.record || '';
    $('#tlsRptNote').textContent = tls.note || '';
    $('#tlsRptCard').classList.remove('hidden');
  }

  // Show results, hide form
  $('#dnsFormCard').classList.add('hidden');
  $('#dnsResults').classList.remove('hidden');

  initCopyButtons();

  // Scroll to results
  $('#dnsResults').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function escHtml(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

// ── Run Again ────────────────────────────────────────
$('#dnsRunAgainBtn').addEventListener('click', () => {
  $('#dnsResults').classList.add('hidden');
  $('#dnsFormCard').classList.remove('hidden');
  $('#dnsFormCard').scrollIntoView({ behavior: 'smooth', block: 'start' });
});

// ── ESP chip toggle visual ───────────────────────────
$$('.dns-esp-chip input').forEach(cb => {
  cb.addEventListener('change', () => {
    cb.closest('.dns-esp-chip').classList.toggle('dns-esp-chip--active', cb.checked);
  });
});
