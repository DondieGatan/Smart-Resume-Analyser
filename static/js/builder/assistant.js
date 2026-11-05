/* Resume Builder, part 3 of 3: the AI assistant chat panel.

   The server owns the conversation rules. This file sends {message, history, draft} (or {action: 'review'}) to
   the chat endpoint and renders the ordered `parts` that come back: plain text, and suggestion cards that name a
   section id. It never parses model output and never decides what may be applied: a card only exists when the
   server validated it, and Apply writes through Builder.setSectionText, the same path as typing.

   Needs core.js. */
(function () {
var B = window.Builder;
var CHAT_URL = B.config.chatUrl;
var STORAGE_KEY = 'builderAiChat_' + B.config.templateId;
var MAX_STORED_TURNS = 20;
var REVIEW_LABEL = 'Review my whole resume for gaps';
var REQUEST_LIMIT_MS = 75000;   // a little over the server's own budget (40s review, 30s chat)

var panel = document.getElementById('ai-chat-panel');
var toggleBtn = document.getElementById('ai-chat-toggle');
var messagesEl = document.getElementById('ai-chat-messages');
var inputEl = document.getElementById('ai-chat-input');
var sendBtn = document.getElementById('ai-chat-send');
var reviewBtn = document.getElementById('ai-chat-gap-btn');
if (!panel || !toggleBtn || !messagesEl || !inputEl) return;

var history = loadHistory();    // [{role: 'user'|'assistant', content, parts?}]
var open = false;
var pending = false;

// ---------- Saved conversation (this browser only; optional) ----------
function loadHistory() {
    try {
        var parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
        return Array.isArray(parsed) ? parsed.filter(function (t) { return t && typeof t.content === 'string'; }) : [];
    } catch (e) {
        return [];
    }
}

function saveHistory() {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(history)); } catch (e) { /* storage unavailable */ }
}

// ---------- Panel ----------
function setOpen(next) {
    open = next;
    panel.hidden = !open;
    toggleBtn.setAttribute('aria-expanded', String(open));
    if (open) inputEl.focus(); else toggleBtn.focus();
}

// ---------- Rendering ----------
function textPart(text) {
    var p = document.createElement('div');
    p.className = 'ai-chat-text';
    p.textContent = text;
    return p;
}

function suggestionCard(part) {
    var index = B.indexOfSection(part.section_id);
    var card = document.createElement('div');
    card.className = 'ai-chat-suggestion';

    var label = document.createElement('div');
    label.className = 'ai-chat-suggestion-label';
    label.textContent = 'Suggested for: ' + part.section_name;
    card.appendChild(label);

    var body = document.createElement('div');
    body.className = 'ai-chat-suggestion-text';
    body.textContent = part.text;
    card.appendChild(body);

    var actions = document.createElement('div');
    actions.className = 'ai-chat-suggestion-actions';

    if (index) {
        var apply = document.createElement('button');
        apply.type = 'button';
        apply.className = 'ai-chat-apply-btn';
        apply.textContent = 'Apply to ' + part.section_name;
        apply.addEventListener('click', function () {
            var ta = B.setSectionText(index, part.text);
            if (!ta) return;
            apply.textContent = 'Applied';
            apply.disabled = true;
            ta.scrollIntoView({ behavior: 'smooth', block: 'center' });
            ta.classList.add('ai-chat-applied-flash');
            setTimeout(function () { ta.classList.remove('ai-chat-applied-flash'); }, 1500);
        });
        actions.appendChild(apply);
    }

    var dismiss = document.createElement('button');
    dismiss.type = 'button';
    dismiss.className = 'ai-chat-dismiss-btn';
    dismiss.textContent = 'Dismiss';
    dismiss.addEventListener('click', function () { card.remove(); });
    actions.appendChild(dismiss);

    card.appendChild(actions);
    return card;
}

/* Turns saved from before the server returned parts only have raw text; show it without any marker syntax. */
function partsOf(turn) {
    if (Array.isArray(turn.parts)) return turn.parts;
    return [{ type: 'text', text: turn.content.replace(/\[\[\/?SUGGEST[^\]]*\]\]/gi, '').trim() }];
}

function addMessage(role, parts) {
    var div = document.createElement('div');
    div.className = 'ai-chat-msg ' + (role === 'user' ? 'ai-chat-msg-user' : 'ai-chat-msg-bot');
    parts.forEach(function (part) {
        if (part.type === 'suggestion') div.appendChild(suggestionCard(part));
        else if (part.text) div.appendChild(textPart(part.text));
    });
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return div;
}

// ---------- Talking to the server ----------
function setPending(on) {
    pending = on;
    sendBtn.disabled = on;
    if (reviewBtn) reviewBtn.disabled = on;
}

function send(shown, body, storedUserText) {
    if (pending) return;
    addMessage('user', [{ type: 'text', text: shown }]);
    setPending(true);
    var isReview = body.action === 'review';
    var typing = addMessage('assistant', [{ type: 'text', text: isReview ? 'Reviewing your whole resume... this can take up to a minute.' : 'Thinking...' }]);
    typing.classList.add('ai-chat-typing');

    var payload = Object.assign({
        history: history.map(function (t) { return { role: t.role, content: t.content }; }),
        draft: B.draftByText()
    }, body);

    // The server answers within its own time budget (the AI, then a backup model, then for the review an
    // automatic check), so this limit is only a safety net for a dead connection: the panel can never spin forever.
    var controller = typeof AbortController === 'function' ? new AbortController() : null;
    var giveUp = controller ? setTimeout(function () { controller.abort(); }, REQUEST_LIMIT_MS) : null;

    fetch(CHAT_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: controller ? controller.signal : undefined
    }).then(function (res) {
        return res.json().catch(function () { return {}; }).then(function (data) { return { ok: res.ok, data: data }; });
    }).then(function (result) {
        typing.remove();
        if (result.ok && result.data.reply) {
            var parts = result.data.parts || [{ type: 'text', text: result.data.reply }];
            addMessage('assistant', parts);
            history.push({ role: 'user', content: storedUserText });
            history.push({ role: 'assistant', content: result.data.reply, parts: parts });
            if (history.length > MAX_STORED_TURNS) history = history.slice(-MAX_STORED_TURNS);
            saveHistory();
        } else {
            addMessage('assistant', [{ type: 'text', text: result.data.error || 'Something went wrong. Please try again.' }]);
        }
    }).catch(function (err) {
        typing.remove();
        var timedOut = err && err.name === 'AbortError';
        addMessage('assistant', [{ type: 'text', text: timedOut
            ? 'That took too long, so I stopped waiting. Please press the button again.'
            : 'Could not reach the AI assistant. Check your connection and try again.' }]);
    }).finally(function () {
        if (giveUp) clearTimeout(giveUp);
        setPending(false);
    });
}

function sendTyped() {
    var message = inputEl.value.trim();
    if (!message || pending) return;
    inputEl.value = '';
    send(message, { message: message }, message);
}

// ---------- Wiring ----------
toggleBtn.addEventListener('click', function () { setOpen(!open); });
var closeBtn = panel.querySelector('.ai-chat-close');
if (closeBtn) closeBtn.addEventListener('click', function () { setOpen(false); });
sendBtn.addEventListener('click', sendTyped);
if (reviewBtn) reviewBtn.addEventListener('click', function () { send(REVIEW_LABEL, { action: 'review' }, REVIEW_LABEL); });
inputEl.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendTyped(); }
});
panel.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && open) { e.stopPropagation(); setOpen(false); }
});

history.forEach(function (turn) { addMessage(turn.role, partsOf(turn)); });
})();
