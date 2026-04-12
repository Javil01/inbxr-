/* ══════════════════════════════════════════════════════
   InbXr — Support Chat Panel
   ══════════════════════════════════════════════════════ */

'use strict';

(function() {

var panel = document.getElementById('scPanel');
var messagesEl = document.getElementById('scMessages');
var inputEl = document.getElementById('scInput');
var sendBtn = document.getElementById('scSend');
var closeBtn = document.getElementById('scClose');
var agentNameEl = document.getElementById('scAgentName');

var currentAgent = 'support';
var messages = []; // conversation history
var isLoading = false;

var GREETINGS = {
  support: "Hi! I'm the InbXr Technical Support assistant. How can I help you today?",
  sales: "Hi! I'm the InbXr Sales assistant. I can help with questions about plans, pricing, and features. What would you like to know?"
};

var AGENT_LABELS = {
  support: 'Technical Support',
  sales: 'Sales & Plans'
};

// ── Open / Close ──
function openChat(agent) {
  currentAgent = agent;
  messages = [];
  agentNameEl.textContent = AGENT_LABELS[agent] || 'Support';
  panel.classList.add('sc-panel--open');
  messagesEl.innerHTML = '';
  addMessage('assistant', GREETINGS[agent]);
  inputEl.focus();
}

function closeChat() {
  panel.classList.remove('sc-panel--open');
}

document.getElementById('openSupportAgent').addEventListener('click', function() {
  openChat('support');
});

document.getElementById('openSalesAgent').addEventListener('click', function() {
  openChat('sales');
});

closeBtn.addEventListener('click', closeChat);

// ── Send Message ──
function sendMessage() {
  var text = inputEl.value.trim();
  if (!text || isLoading) return;

  inputEl.value = '';
  addMessage('user', text);
  messages.push({ role: 'user', content: text });

  isLoading = true;
  var loadingEl = addLoading();

  fetch('/api/support/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ agent: currentAgent, messages: messages })
  })
  .then(function(res) { return res.json(); })
  .then(function(data) {
    removeLoading(loadingEl);
    if (data.error) {
      addMessage('assistant', 'Sorry, I ran into an issue: ' + data.error);
    } else {
      var reply = data.reply || 'Sorry, I could not generate a response.';
      addMessage('assistant', reply);
      messages.push({ role: 'assistant', content: reply });
    }
  })
  .catch(function() {
    removeLoading(loadingEl);
    addMessage('assistant', 'Sorry, something went wrong. Please try again.');
  })
  .finally(function() {
    isLoading = false;
  });
}

sendBtn.addEventListener('click', sendMessage);
inputEl.addEventListener('keydown', function(e) {
  if (e.key === 'Enter') sendMessage();
});

// ── DOM Helpers ──
function addMessage(role, text) {
  var div = document.createElement('div');
  div.className = 'sc-msg sc-msg--' + role;

  // Simple markdown: **bold**, `code`, links
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
  div.className = 'sc-msg sc-msg--assistant sc-msg--loading';
  div.innerHTML = '<span class="sc-typing"><span></span><span></span><span></span></span>';
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return div;
}

function removeLoading(el) {
  if (el && el.parentNode) el.parentNode.removeChild(el);
}


// ── FAQ Accordion ──
document.querySelectorAll('.faq-item__q').forEach(function(btn) {
  btn.addEventListener('click', function() {
    var item = this.parentElement;
    var isOpen = item.classList.contains('faq-item--open');
    // Close all others in same section
    item.parentElement.querySelectorAll('.faq-item--open').forEach(function(el) {
      el.classList.remove('faq-item--open');
    });
    if (!isOpen) item.classList.add('faq-item--open');
  });
});

})();
