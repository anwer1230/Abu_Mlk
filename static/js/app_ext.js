/**
 * app_ext.js — مركز سرعة إنجاز
 * يشمل المرحلة 1 + المرحلة 2 (مجموعات، وسائط، معرض، تحميل إضافي)
 * المراحل 1-15: تفاعلات، قوائم، ردود، توجيه، بحث، سمات، ملف شخصي، إعدادات
 */
'use strict';

/* ══════════════════════════════════════════════════════════════════
   مخزن بيانات الرسائل (يُملأ من renderMessages)
   ══════════════════════════════════════════════════════════════════ */
const MsgStore  = new Map();   // msg.id → msg object
let   _ctxMsgId = null;        // معرّف الرسالة المحددة حاليا
let   _ctxChatId = null;       // معرّف المحادثة الحالية للقائمة
let   _replyTo  = null;        // { id, text, sender_name }
let   _editId   = null;        // معرّف رسالة يجري تعديلها

/* ══════════════════════════════════════════════════════════════════
   قائمة سياق الرسائل (MsgCtx)
   ══════════════════════════════════════════════════════════════════ */
const MsgCtx = {
    el: null,

    init() {
        this.el = document.getElementById('msgCtxMenu');
        document.addEventListener('click',  () => this.hide());
        document.addEventListener('keydown', e => { if (e.key === 'Escape') this.hide(); });
    },

    show(event, wrapEl) {
        event.preventDefault();
        event.stopPropagation();
        const msgId  = wrapEl.dataset.id;
        const senderId = wrapEl.dataset.sid;
        _ctxMsgId = msgId;
        _ctxChatId = AppState?.currentChatId;

        const isMine = String(senderId) === String(AppState?.userId);
        this.el.querySelector('[data-a="edit"]').style.display   = isMine ? '' : 'none';
        this.el.querySelector('[data-a="delete"]').style.display = isMine ? '' : 'none';

        // تحديد الموضع
        const x = Math.min(event.clientX, window.innerWidth  - 220);
        const y = Math.min(event.clientY, window.innerHeight - 320);
        this.el.style.left = x + 'px';
        this.el.style.top  = y + 'px';
        this.el.style.display = 'block';
        return false;
    },

    hide() {
        if (this.el) this.el.style.display = 'none';
    },

    async act(action) {
        this.hide();
        const msg = MsgStore.get(String(_ctxMsgId));
        if (!msg && !['delete'].includes(action)) {
            if (!_ctxMsgId) return;
        }
        switch (action) {
            case 'reply':    Replies.start(msg);           break;
            case 'forward':  Forward.start(_ctxMsgId);    break;
            case 'copy':     copyText(msg?.text || '');    break;
            case 'react':    ReactPicker.show(event, _ctxMsgId); break;
            case 'pin':      await apiPinMessage(_ctxMsgId, _ctxChatId);  break;
            case 'bookmark': await apiBookmark(_ctxMsgId, msg?.text, _ctxChatId); break;
            case 'edit':     Edits.start(msg);             break;
            case 'delete':   await apiDeleteMessage(_ctxMsgId, _ctxChatId); break;
            case 'translate':await translateMsg(msg?.text || ''); break;
            case 'select':   toggleSelectMsg(_ctxMsgId);  break;
        }
    }
};

/* ══════════════════════════════════════════════════════════════════
   قائمة سياق المحادثات (ChatCtx)
   ══════════════════════════════════════════════════════════════════ */
const ChatCtx = {
    el: null,
    chatId: null,

    init() {
        this.el = document.getElementById('chatCtxMenu');
        document.addEventListener('click', () => this.hide());
    },

    show(event, chatId) {
        event.preventDefault();
        event.stopPropagation();
        this.chatId = chatId;
        const x = Math.min(event.clientX, window.innerWidth  - 200);
        const y = Math.min(event.clientY, window.innerHeight - 200);
        this.el.style.left = x + 'px';
        this.el.style.top  = y + 'px';
        this.el.style.display = 'block';
        return false;
    },

    hide() { if (this.el) this.el.style.display = 'none'; },

    async act(action) {
        this.hide();
        switch (action) {
            case 'archive': await toggleArchiveChat(this.chatId); break;
            case 'mute':    await toggleMuteChat(this.chatId);    break;
            case 'block':   await blockUser(this.chatId);          break;
            case 'pin-chat':  pinChatInList(this.chatId);         break;
        }
    }
};

/* ══════════════════════════════════════════════════════════════════
   منتقي التفاعلات (ReactPicker)
   ══════════════════════════════════════════════════════════════════ */
const ReactPicker = {
    el: null,
    targetMsgId: null,

    init() {
        this.el = document.getElementById('reactPicker');
        document.addEventListener('click', e => {
            if (this.el && !this.el.contains(e.target)) this.hide();
        });
    },

    show(event, msgId) {
        this.targetMsgId = msgId;
        const x = Math.min((event?.clientX || 200), window.innerWidth  - 220);
        const y = Math.min((event?.clientY || 200), window.innerHeight - 80);
        this.el.style.left = x + 'px';
        this.el.style.top  = (y - 60) + 'px';
        this.el.style.display = 'flex';
    },

    hide() { if (this.el) this.el.style.display = 'none'; },

    async pick(emoji) {
        this.hide();
        if (!this.targetMsgId) return;
        await toggleReaction(this.targetMsgId, emoji);
    }
};

/* ══════════════════════════════════════════════════════════════════
   نظام التفاعلات
   ══════════════════════════════════════════════════════════════════ */
const _rxCache = new Map();   // msgId → [ {reaction, user_id, user_name} ]

async function toggleReaction(msgId, emoji) {
    const current  = _rxCache.get(String(msgId)) || [];
    const myReact  = current.find(r => String(r.user_id) === String(AppState?.userId));
    const action   = (myReact?.reaction === emoji) ? 'remove' : 'add';

    try {
        const res  = await fetch('/api/messages/reaction', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({
                message_id: msgId,
                reaction:   emoji,
                action,
                chat_id:    AppState?.currentChatId,
            }),
        });
        const data = await res.json();
        if (data.success) {
            _rxCache.set(String(msgId), data.reactions);
            renderReactions(msgId, data.reactions);
        }
    } catch (e) {
        showToast('❌ فشل التفاعل', 'error');
    }
}

function renderReactions(msgId, reactions) {
    const container = document.getElementById('rxn_' + msgId);
    if (!container) return;

    // تجميع حسب الإيموجي
    const groups = {};
    reactions.forEach(r => {
        if (!groups[r.reaction]) groups[r.reaction] = [];
        groups[r.reaction].push(r.user_id);
    });

    container.innerHTML = Object.entries(groups).map(([emoji, uids]) => {
        const mine = uids.includes(String(AppState?.userId));
        return `<button class="rx-badge ${mine?'mine':''} rx-pop-anim"
                        onclick="toggleReaction('${msgId}','${emoji}')"
                        title="${uids.length} تفاعل">
                    ${emoji} <span class="rx-cnt">${uids.length}</span>
                </button>`;
    }).join('');
}

async function loadVisibleReactions(msgIds) {
    if (!msgIds || !msgIds.length) return;
    try {
        const ids = msgIds.map(id => encodeURIComponent(id)).join(',');
        const res  = await fetch(`/api/messages/reactions?ids=${ids}`);
        const data = await res.json();
        if (data.success) {
            Object.entries(data.reactions).forEach(([msgId, rxns]) => {
                _rxCache.set(String(msgId), rxns);
                renderReactions(msgId, rxns);
            });
        }
    } catch (_) {}
}

/* ══════════════════════════════════════════════════════════════════
   نظام الرد على الرسائل
   ══════════════════════════════════════════════════════════════════ */
const Replies = {
    start(msg) {
        if (!msg) return;
        _replyTo = { id: msg.id, text: msg.text, sender_name: msg.sender_name || 'مستخدم' };
        const strip = document.getElementById('replyStrip');
        strip.querySelector('.rs-name').textContent = _replyTo.sender_name;
        strip.querySelector('.rs-text').textContent = (_replyTo.text || '').substring(0, 60);
        strip.style.display = 'flex';
        document.getElementById('messageInput')?.focus();
    },
    cancel() {
        _replyTo = null;
        const strip = document.getElementById('replyStrip');
        if (strip) strip.style.display = 'none';
    }
};

/* ══════════════════════════════════════════════════════════════════
   نظام إعادة التوجيه
   ══════════════════════════════════════════════════════════════════ */
const Forward = {
    msgs: [],
    start(msgId) {
        if (!this.msgs.includes(msgId)) this.msgs.push(msgId);
        showToast(`📤 ${this.msgs.length} رسالة — اختر محادثة لإرسالها`, 'info');
        document.getElementById('fwdBar').style.display = 'flex';
        document.getElementById('fwdBar').querySelector('.fwd-cnt').textContent = this.msgs.length;
    },
    cancel() {
        this.msgs = [];
        const bar = document.getElementById('fwdBar');
        if (bar) bar.style.display = 'none';
    },
    async send(toChatId) {
        if (!this.msgs.length) return;
        const chatId = toChatId || AppState?.currentChatId;
        if (!chatId) { showToast('⚠️ اختر محادثة وجهة', 'warning'); return; }
        try {
            const res  = await fetch('/api/messages/forward', {
                method:  'POST',
                headers: { 'Content-Type': 'application/json' },
                body:    JSON.stringify({
                    to_chat_id:   chatId,
                    from_chat_id: AppState?.currentChatId,
                    message_ids:  this.msgs,
                }),
            });
            const data = await res.json();
            if (data.success) {
                showToast(`✅ تم إرسال ${this.msgs.length} رسالة`, 'success');
                this.cancel();
            } else showToast('❌ ' + data.message, 'error');
        } catch (_) { showToast('❌ حدث خطأ', 'error'); }
    }
};

/* ══════════════════════════════════════════════════════════════════
   نظام تعديل الرسائل
   ══════════════════════════════════════════════════════════════════ */
const Edits = {
    start(msg) {
        if (!msg) return;
        _editId = msg.id;
        const inp = document.getElementById('messageInput');
        inp.value = msg.text || '';
        inp.focus();
        const strip = document.getElementById('editStrip');
        strip.style.display = 'flex';
        const sendBtn = document.getElementById('sendBtn');
        sendBtn.style.background = '#f9ca24';
    },
    cancel() {
        _editId = null;
        const inp = document.getElementById('messageInput');
        if (inp) inp.value = '';
        const strip = document.getElementById('editStrip');
        if (strip) strip.style.display = 'none';
        const sendBtn = document.getElementById('sendBtn');
        if (sendBtn) sendBtn.style.background = '';
    },
    async save(newText) {
        if (!_editId || !newText) return false;
        if (typeof socket !== 'undefined' && socket?.connected) {
            socket.emit('edit_message', {
                user_id:    AppState?.userId,
                chat_id:    AppState?.currentChatId,
                message_id: _editId,
                text:       newText,
            });
        }
        this.cancel();
        return true;
    }
};

/* ══════════════════════════════════════════════════════════════════
   عمليات API على الرسائل
   ══════════════════════════════════════════════════════════════════ */
async function apiDeleteMessage(msgId, chatId) {
    if (!confirm('هل أنت متأكد من حذف هذه الرسالة؟')) return;
    if (typeof socket !== 'undefined' && socket?.connected) {
        socket.emit('delete_message', {
            user_id:    AppState?.userId,
            chat_id:    chatId || AppState?.currentChatId,
            message_id: msgId,
        });
    }
}

async function apiPinMessage(msgId, chatId) {
    try {
        const res  = await fetch('/api/messages/pin', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ message_id: msgId, chat_id: chatId }),
        });
        const data = await res.json();
        if (data.success) showToast('📌 تم تثبيت الرسالة', 'success');
        else showToast('❌ ' + data.message, 'error');
    } catch (_) { showToast('❌ فشل التثبيت', 'error'); }
}

async function apiBookmark(msgId, text, chatId) {
    try {
        const res  = await fetch('/api/messages/bookmark', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ message_id: msgId, text, chat_id: chatId }),
        });
        const data = await res.json();
        if (data.success) showToast('⭐ تم حفظ الرسالة', 'success');
        else showToast('❌ ' + data.message, 'error');
    } catch (_) { showToast('❌ فشل الحفظ', 'error'); }
}

/* ══════════════════════════════════════════════════════════════════
   نسخ النص
   ══════════════════════════════════════════════════════════════════ */
function copyText(text) {
    if (!text) return;
    if (navigator.clipboard) {
        navigator.clipboard.writeText(text)
            .then(()  => showToast('✅ تم النسخ', 'success'))
            .catch(() => _legacyCopy(text));
    } else {
        _legacyCopy(text);
    }
}
function _legacyCopy(text) {
    const ta = document.createElement('textarea');
    ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.appendChild(ta); ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    showToast('✅ تم النسخ', 'success');
}

/* ══════════════════════════════════════════════════════════════════
   تحديد رسائل متعددة
   ══════════════════════════════════════════════════════════════════ */
const _selected = new Set();
function toggleSelectMsg(msgId) {
    if (_selected.has(msgId)) {
        _selected.delete(msgId);
        document.querySelector(`.msg-wrap[data-id="${msgId}"]`)?.classList.remove('selected');
    } else {
        _selected.add(msgId);
        document.querySelector(`.msg-wrap[data-id="${msgId}"]`)?.classList.add('selected');
    }
    showToast(`📌 محدد: ${_selected.size} رسالة`, 'info');
}

/* ══════════════════════════════════════════════════════════════════
   ترجمة نص
   ══════════════════════════════════════════════════════════════════ */
async function translateMsg(text) {
    if (!text) return;
    try {
        const res  = await fetch('/api/translate', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ text }),
        });
        const data = await res.json();
        if (data.success) showToast(`🌍 ${data.translation}`, 'info');
        else showToast('❌ فشلت الترجمة', 'error');
    } catch (_) { showToast('❌ فشلت الترجمة', 'error'); }
}

/* ══════════════════════════════════════════════════════════════════
   عمليات المحادثات (أرشفة / كتم / تثبيت)
   ══════════════════════════════════════════════════════════════════ */
const _archived = new Set();
const _muted    = new Set();

async function toggleArchiveChat(chatId) {
    const isAr = _archived.has(chatId);
    try {
        const res  = await fetch(`/api/chats/${chatId}/archive`, {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ action: isAr ? 'unarchive' : 'archive' }),
        });
        const data = await res.json();
        if (data.success) {
            if (isAr) { _archived.delete(chatId); showToast('📭 تم إلغاء الأرشفة', 'info'); }
            else       { _archived.add(chatId);   showToast('📦 تم الأرشفة', 'success'); }
            _updateChatItemClass(chatId);
        }
    } catch (_) { showToast('❌ فشلت العملية', 'error'); }
}

async function toggleMuteChat(chatId) {
    const isMuted = _muted.has(chatId);
    try {
        const res  = await fetch(`/api/chats/${chatId}/mute`, {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ action: isMuted ? 'unmute' : 'mute', hours: 8 }),
        });
        const data = await res.json();
        if (data.success) {
            if (isMuted) { _muted.delete(chatId); showToast('🔊 تم إلغاء الكتم', 'info'); }
            else          { _muted.add(chatId);   showToast('🔇 تم الكتم', 'success'); }
            _updateChatItemClass(chatId);
        }
    } catch (_) { showToast('❌ فشلت العملية', 'error'); }
}

function _updateChatItemClass(chatId) {
    const el = document.querySelector(`.chat-item[data-chat-id="${chatId}"]`);
    if (!el) return;
    el.classList.toggle('archived', _archived.has(chatId));
    el.classList.toggle('muted', _muted.has(chatId));
}

function pinChatInList(chatId) {
    const chat = AppState?.chats?.find(c => c.id == chatId);
    if (!chat) return;
    chat.is_pinned = !chat.is_pinned;
    if (typeof renderChatList === 'function') renderChatList(AppState.chats);
    showToast(chat.is_pinned ? '📌 تم تثبيت المحادثة' : '📌 تم إلغاء التثبيت', 'success');
}

async function loadChatStates() {
    try {
        const res  = await fetch('/api/chats/states');
        const data = await res.json();
        if (data.success) {
            (data.archived || []).forEach(id => _archived.add(id));
            (data.muted    || []).forEach(id => _muted.add(id));
        }
    } catch (_) {}
}

/* ══════════════════════════════════════════════════════════════════
   حظر المستخدمين
   ══════════════════════════════════════════════════════════════════ */
async function blockUser(userId) {
    if (!confirm(`هل أنت متأكد من حظر هذا المستخدم؟`)) return;
    try {
        const res  = await fetch(`/api/users/${userId}/block`, { method: 'POST' });
        const data = await res.json();
        if (data.success) showToast('🚫 تم حظر المستخدم', 'success');
        else showToast('❌ ' + data.message, 'error');
    } catch (_) { showToast('❌ فشل الحظر', 'error'); }
}

async function unblockUser(userId) {
    try {
        const res  = await fetch(`/api/users/${userId}/block`, { method: 'DELETE' });
        const data = await res.json();
        if (data.success) showToast('✅ تم إلغاء الحظر', 'success');
        else showToast('❌ ' + data.message, 'error');
    } catch (_) {}
}

/* ══════════════════════════════════════════════════════════════════
   الملف الشخصي
   ══════════════════════════════════════════════════════════════════ */
async function showProfile(chatId) {
    const panel = document.getElementById('profilePanel');
    const overlay = document.getElementById('panelOverlay');
    if (!panel) return;

    const chat   = AppState?.chats?.find(c => c.id == chatId);
    const colors = ['#6c5ce7','#00d2ff','#ff6b6b','#f9ca24','#2ecc71','#e17055'];
    const color  = chat ? colors[Math.abs(chat.id) % colors.length] : '#3a7bd5';
    const name   = chat?.name || 'مستخدم';
    const initial = name[0].toUpperCase();

    panel.querySelector('.profile-avatar-lg').style.background = color;
    panel.querySelector('.profile-avatar-lg').textContent = initial;
    panel.querySelector('.profile-name').textContent = name;
    panel.querySelector('.profile-sub').textContent  = chat?.is_online ? '🟢 متصل الآن' : '⚪ غير متصل';
    panel.querySelector('.profile-chat-id').textContent = chatId ? 'ID: ' + chatId : '';

    // تحميل معلومات إضافية من API
    if (chatId) {
        try {
            const res  = await fetch(`/api/profile/${chatId}`);
            const data = await res.json();
            if (data.success && data.profile) {
                const p = data.profile;
                if (p.username)  panel.querySelector('.profile-sub').textContent += ` (@${p.username})`;
                if (p.phone)     panel.querySelector('.profile-phone').textContent = '📞 ' + p.phone;
                if (p.bio)       panel.querySelector('.profile-bio').textContent   = p.bio;
            }
        } catch (_) {}
    }

    panel.classList.add('open');
    if (overlay) overlay.classList.add('visible');
}

function closeProfile() {
    document.getElementById('profilePanel')?.classList.remove('open');
    document.getElementById('panelOverlay')?.classList.remove('visible');
}

/* ══════════════════════════════════════════════════════════════════
   الإعدادات
   ══════════════════════════════════════════════════════════════════ */
function showSettings() {
    const panel = document.getElementById('settingsPanel');
    const overlay = document.getElementById('panelOverlay');
    if (!panel) return;
    // حالة المفاتيح الحالية
    panel.querySelector('#sw-sound').checked   = notificationSoundEnabled ?? true;
    panel.querySelector('#sw-speech').checked  = speechEnabled ?? false;
    panel.querySelector('#sw-theme').checked   = document.documentElement.dataset.theme === 'light';
    panel.classList.add('open');
    if (overlay) overlay.classList.add('visible');
}

function closeSettings() {
    document.getElementById('settingsPanel')?.classList.remove('open');
    document.getElementById('panelOverlay')?.classList.remove('visible');
}

function onSwSound(val) {
    if (typeof notificationSoundEnabled !== 'undefined') {
        // eslint-disable-next-line no-global-assign
        notificationSoundEnabled = val;
    }
    showToast(val ? '🔊 الصوت مفعَّل' : '🔇 الصوت موقوف', 'info');
    fetch('/api/settings', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ key: 'notification_sound', value: val }),
    }).catch(() => {});
}

function onSwSpeech(val) {
    if (typeof speechEnabled !== 'undefined') {
        // eslint-disable-next-line no-global-assign
        speechEnabled = val;
    }
    showToast(val ? '🗣️ النطق مفعَّل' : '🗣️ النطق موقوف', 'info');
    fetch('/api/settings', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ key: 'tts_enabled', value: val }),
    }).catch(() => {});
}

/* ══════════════════════════════════════════════════════════════════
   السمات (Theme)
   ══════════════════════════════════════════════════════════════════ */
function toggleTheme() {
    const html  = document.documentElement;
    const light = html.dataset.theme === 'light';
    const next  = light ? 'dark' : 'light';
    applyTheme(next);
    fetch('/api/settings', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ key: 'theme', value: next }),
    }).catch(() => {});
}

function applyTheme(theme) {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem('theme', theme);
    const btn = document.getElementById('themeToggleBtn');
    if (btn) btn.innerHTML = theme === 'light'
        ? '<i class="fas fa-moon"></i>'
        : '<i class="fas fa-sun"></i>';
    const sw = document.getElementById('sw-theme');
    if (sw) sw.checked = theme === 'light';
}

/* ══════════════════════════════════════════════════════════════════
   البحث المتقدم
   ══════════════════════════════════════════════════════════════════ */
function showSearch() {
    const panel = document.getElementById('searchPanel');
    if (panel) {
        panel.style.display = 'flex';
        panel.querySelector('#searchQueryInput')?.focus();
    }
}

function closeSearch() {
    const panel = document.getElementById('searchPanel');
    if (panel) panel.style.display = 'none';
}

async function execSearch() {
    const q = document.getElementById('searchQueryInput')?.value?.trim();
    if (!q) return;
    const chatId = AppState?.currentChatId;
    const resContainer = document.getElementById('searchResults');
    resContainer.innerHTML = '<div class="search-empty">⏳ جاري البحث...</div>';
    try {
        const url = chatId
            ? `/api/search?q=${encodeURIComponent(q)}&chat_id=${chatId}`
            : `/api/search?q=${encodeURIComponent(q)}`;
        const res  = await fetch(url);
        const data = await res.json();
        if (data.success && data.results?.length) {
            resContainer.innerHTML = data.results.map(r => `
                <div class="search-result-item" onclick="jumpToMsg('${r.id}','${r.chat_id}')">
                    <div>
                        <span class="sr-sender">${escHtml(r.sender_name || 'مستخدم')}</span>
                        <span class="sr-time">${formatTime ? formatTime(r.timestamp) : ''}</span>
                        <div class="sr-text">${highlightQuery(escHtml(r.text || ''), q)}</div>
                    </div>
                </div>`).join('');
        } else {
            resContainer.innerHTML = '<div class="search-empty">🔍 لا توجد نتائج</div>';
        }
    } catch (_) {
        resContainer.innerHTML = '<div class="search-empty">❌ حدث خطأ في البحث</div>';
    }
}

function highlightQuery(text, q) {
    const re = new RegExp('(' + q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'gi');
    return text.replace(re, '<mark style="background:rgba(0,210,255,.3);color:#fff;padding:0 2px;border-radius:2px;">$1</mark>');
}

async function jumpToMsg(msgId, chatId) {
    closeSearch();
    if (chatId && chatId != AppState?.currentChatId) {
        await selectChat(parseInt(chatId));
    }
    setTimeout(() => {
        const el = document.querySelector(`.msg-wrap[data-id="${msgId}"]`);
        if (el) {
            el.scrollIntoView({ behavior: 'smooth', block: 'center' });
            el.style.outline = '2px solid #00d2ff';
            setTimeout(() => { el.style.outline = ''; }, 2000);
        }
    }, 600);
}

/* ══════════════════════════════════════════════════════════════════
   المساعدات العامة
   ══════════════════════════════════════════════════════════════════ */
function escHtml(str) {
    return String(str)
        .replace(/&/g,'&amp;').replace(/</g,'&lt;')
        .replace(/>/g,'&gt;').replace(/"/g,'&quot;')
        .replace(/'/g,'&#39;');
}

/* ══════════════════════════════════════════════════════════════════
   Socket.IO — أحداث إضافية
   ══════════════════════════════════════════════════════════════════ */
function setupExtSocketEvents() {
    if (typeof socket === 'undefined' || !socket) return;

    socket.on('message_reaction_update', data => {
        const { message_id, reactions } = data;
        _rxCache.set(String(message_id), reactions);
        renderReactions(message_id, reactions);
    });

    socket.on('folder_invitation', data => {
        showToast(`📁 دعوة لمجلد: ${data.folder_name}`, 'info');
    });
}

/* ══════════════════════════════════════════════════════════════════
   تهيئة الإضافات (يُستدعى من initPage)
   ══════════════════════════════════════════════════════════════════ */
/* ══════════════════════════════════════════════════════════════════
   المرحلة 2: المجموعات + الوسائط + عرض الصور + تحميل إضافي
   ══════════════════════════════════════════════════════════════════ */

// ─── إنشاء المجموعة ─────────────────────────────────────────────
function showCreateGroupModal() {
    const modal = new bootstrap.Modal(document.getElementById('createGroupModal'));
    modal.show();
}

async function submitCreateGroup() {
    const title = document.getElementById('groupNameInput')?.value?.trim();
    const type  = document.getElementById('groupTypeSelect')?.value || 'group';
    const users = document.getElementById('groupUsersInput')?.value || '';
    if (!title) { showToast('⚠️ أدخل اسم المجموعة', 'warning'); return; }

    const btn = document.querySelector('#createGroupModal .btn-primary');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ جارٍ الإنشاء...'; }

    try {
        const res  = await fetch('/api/groups/create', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ title, type, users }),
        });
        const data = await res.json();
        if (data.success) {
            showToast(`✅ تم إنشاء "${title}"`, 'success');
            bootstrap.Modal.getInstance(document.getElementById('createGroupModal'))?.hide();
            document.getElementById('groupNameInput').value  = '';
            document.getElementById('groupUsersInput').value = '';
            if (typeof refreshChats === 'function') setTimeout(refreshChats, 1500);
        } else {
            showToast('❌ ' + data.message, 'error');
        }
    } catch (_) {
        showToast('❌ فشل الإنشاء', 'error');
    } finally {
        if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-plus"></i> إنشاء'; }
    }
}

// ─── محدد الوسائط ─────────────────────────────────────────────
function toggleMediaPicker(event) {
    event?.stopPropagation();
    const picker = document.getElementById('mediaPicker');
    if (!picker) return;
    if (picker.style.display === 'none' || !picker.style.display) {
        const btn  = document.getElementById('attachBtn');
        const rect = btn?.getBoundingClientRect() || { left: 200, top: 200 };
        picker.style.left    = rect.left + 'px';
        picker.style.bottom  = (window.innerHeight - rect.top + 6) + 'px';
        picker.style.top     = 'auto';
        picker.style.display = 'block';
        setTimeout(() => document.addEventListener('click', hideMediaPicker, { once: true }), 0);
    } else {
        hideMediaPicker();
    }
}
function hideMediaPicker() {
    const p = document.getElementById('mediaPicker');
    if (p) p.style.display = 'none';
}

// ─── إرسال الوسائط ─────────────────────────────────────────────
async function handleMediaSend(files) {
    if (!files?.length) return;
    const chatId = AppState?.currentChatId;
    if (!chatId) { showToast('⚠️ اختر محادثة أولاً', 'warning'); return; }

    showToast(`⏳ جارٍ إرسال ${files.length} ملف...`, 'info');

    const form = new FormData();
    form.append('chat_id', chatId);
    for (const f of files) form.append('files', f);

    try {
        const res  = await fetch('/api/messages/send-media', { method: 'POST', body: form });
        const data = await res.json();
        if (data.success) {
            showToast(`✅ تم إرسال ${data.message_ids?.length || 1} ملف`, 'success');
            // تحديث الرسائل
            setTimeout(() => {
                if (typeof loadMessages === 'function') loadMessages(chatId);
            }, 1000);
        } else {
            showToast('❌ ' + data.message, 'error');
        }
    } catch (_) {
        showToast('❌ فشل الإرسال', 'error');
    }
}

// ─── عارض الوسائط (Lightbox) ─────────────────────────────────
function openLightbox(src, isVideo = false, caption = '') {
    const lb  = document.getElementById('mediaLightbox');
    const img = document.getElementById('lbImage');
    const vid = document.getElementById('lbVideo');
    const cap = document.getElementById('lbCaption');
    if (!lb) return;

    img.style.display = vid.style.display = 'none';
    if (isVideo) {
        vid.src = src; vid.style.display = 'block'; vid.play().catch(() => {});
    } else {
        img.src = src; img.style.display = 'block';
    }
    if (cap) cap.textContent = caption;
    lb.style.display = 'flex';
    document.addEventListener('keydown', _lbEsc);
}
function closeLightbox() {
    const lb = document.getElementById('mediaLightbox');
    if (lb) lb.style.display = 'none';
    const vid = document.getElementById('lbVideo');
    if (vid) { vid.pause(); vid.src = ''; }
    document.removeEventListener('keydown', _lbEsc);
}
function _lbEsc(e) { if (e.key === 'Escape') closeLightbox(); }

// تحميل وعرض وسائط رسالة
async function loadAndShowMedia(chatId, msgId, isVideo) {
    showToast('⏳ جارٍ تحميل الوسيط...', 'info');
    try {
        const res  = await fetch(`/api/media/${chatId}/${msgId}`);
        const data = await res.json();
        if (data.success) {
            const src = `data:${data.mime};base64,${data.data}`;
            openLightbox(src, isVideo);
        } else {
            showToast('❌ ' + data.message, 'error');
        }
    } catch (_) {
        showToast('❌ فشل تحميل الوسيط', 'error');
    }
}

// ─── إرسال الموقع ─────────────────────────────────────────────
function sendCurrentLocation() {
    if (!navigator.geolocation) { showToast('❌ المتصفح لا يدعم الموقع', 'error'); return; }
    navigator.geolocation.getCurrentPosition(pos => {
        const { latitude: lat, longitude: lng } = pos.coords;
        const text = `📍 موقعي: https://maps.google.com/?q=${lat},${lng}`;
        const inp  = document.getElementById('messageInput');
        if (inp) { inp.value = text; }
        showToast('📍 تم إدراج الموقع — اضغط إرسال', 'info');
    }, () => showToast('❌ لم يتم السماح بالوصول للموقع', 'error'));
}

// ─── تحميل رسائل إضافية (Infinite Scroll) ─────────────────────
let _loadingMore = false;

function setupInfiniteScroll() {
    const area = document.getElementById('messagesArea');
    if (!area) return;
    area.addEventListener('scroll', async () => {
        if (area.scrollTop > 80 || _loadingMore) return;
        const oldest = AppState?.messages?.[0];
        if (!oldest || !AppState?.currentChatId) return;
        _loadingMore = true;
        try {
            const res  = await fetch(
                `/api/chats/${AppState.currentChatId}/messages/more?offset_id=${oldest.id}&limit=30`
            );
            const data = await res.json();
            if (data.success && data.messages?.length) {
                // دمج الرسائل القديمة في البداية
                AppState.messages = [...data.messages.reverse(), ...AppState.messages];
                // حفظ موضع التمرير
                const oldH = area.scrollHeight;
                if (typeof MsgStore !== 'undefined')
                    data.messages.forEach(m => MsgStore.set(String(m.id), m));
                renderMessages(AppState.messages);
                area.scrollTop = area.scrollHeight - oldH;
            }
        } catch (_) {} finally {
            _loadingMore = false;
        }
    });
}

/* ══════════════════════════════════════════════════════════════════
   المرحلة 3: الجلسات النشطة + التحقق بخطوتين + مزامنة
   ══════════════════════════════════════════════════════════════════ */

// ─── الجلسات النشطة ────────────────────────────────────────────
async function showActiveSessions() {
    closeSettings();
    const el = document.getElementById('sessionsModal');
    if (el) {
        new bootstrap.Modal(el).show();
        await loadSessions();
        return;
    }
    // إنشاء نافذة الجلسات ديناميكياً
    const modal = document.createElement('div');
    modal.id = 'sessionsModal';
    modal.className = 'modal fade';
    modal.tabIndex  = -1;
    modal.innerHTML = `
        <div class="modal-dialog modal-dialog-centered modal-lg">
            <div class="modal-content" style="background:#1a1a2e;color:#e0e0e0;border:1px solid rgba(255,255,255,.05);">
                <div class="modal-header" style="border-bottom:1px solid rgba(255,255,255,.05);">
                    <h5 class="modal-title"><i class="fas fa-shield-alt" style="color:#00d2ff;"></i> الجلسات النشطة</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal" style="filter:invert(1);"></button>
                </div>
                <div class="modal-body" style="max-height:460px;overflow-y:auto;">
                    <div id="sessionsListEl" style="display:flex;flex-direction:column;gap:10px;">
                        <div style="text-align:center;color:#555;padding:20px;">⏳ جارٍ التحميل...</div>
                    </div>
                </div>
                <div class="modal-footer" style="border-top:1px solid rgba(255,255,255,.05);justify-content:space-between;">
                    <button class="btn btn-sm" style="background:#ff4757;border:none;color:#fff;border-radius:8px;padding:6px 14px;"
                            onclick="revokeAllSessions()">
                        <i class="fas fa-sign-out-alt"></i> إنهاء جميع الجلسات الأخرى
                    </button>
                    <button class="btn btn-secondary" data-bs-dismiss="modal"
                            style="background:rgba(255,255,255,.05);border:none;">إغلاق</button>
                </div>
            </div>
        </div>`;
    document.body.appendChild(modal);
    new bootstrap.Modal(modal).show();
    await loadSessions();
}

async function loadSessions() {
    const container = document.getElementById('sessionsListEl');
    if (!container) return;
    try {
        const res  = await fetch('/api/auth/sessions');
        const data = await res.json();
        if (!data.success) { container.innerHTML = `<div style="color:#ff4757;">${data.message}</div>`; return; }
        const sessions = data.sessions || [];
        container.innerHTML = sessions.map(s => {
            const isNow = s.current;
            const date  = s.date_active ? new Date(s.date_active * 1000).toLocaleDateString('ar') : 'الآن';
            return `
                <div style="background:rgba(255,255,255,.04);border-radius:10px;padding:12px 16px;
                            display:flex;align-items:center;gap:12px;border:1px solid rgba(255,255,255,.04)
                            ${isNow?';border-color:rgba(0,210,255,.3)':''};">
                    <i class="fas fa-${isNow?'mobile-alt':'laptop'}" style="font-size:24px;color:${isNow?'#00d2ff':'#666'};width:32px;text-align:center;"></i>
                    <div style="flex:1;">
                        <div style="font-weight:600;color:${isNow?'#00d2ff':'#ccc'};font-size:14px;">
                            ${s.device || 'Unknown'} ${isNow?'<span style="font-size:11px;background:rgba(0,210,255,.15);padding:1px 6px;border-radius:8px;">هذا الجهاز</span>':''}
                        </div>
                        <div style="font-size:12px;color:#666;margin-top:2px;">
                            ${s.app || 'Telegram'} · ${s.platform||''} · ${s.country||''} · آخر نشاط: ${date}
                        </div>
                        ${s.ip ? `<div style="font-size:11px;color:#555;">IP: ${s.ip}</div>` : ''}
                    </div>
                    ${!isNow ? `<button onclick="revokeSession(${s.hash},this)"
                                        style="background:rgba(255,71,87,.15);border:1px solid rgba(255,71,87,.3);
                                               color:#ff4757;border-radius:8px;padding:5px 12px;cursor:pointer;
                                               font-family:Tajawal,sans-serif;font-size:13px;">
                                    إنهاء
                                </button>` : ''}
                </div>`;
        }).join('') || '<div style="text-align:center;color:#555;padding:20px;">لا توجد جلسات</div>';
    } catch (_) {
        if (container) container.innerHTML = '<div style="color:#ff4757;">❌ فشل تحميل الجلسات</div>';
    }
}

async function revokeSession(hash, btn) {
    if (btn) btn.disabled = true;
    try {
        const res  = await fetch('/api/auth/sessions/revoke', {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body:   JSON.stringify({hash}),
        });
        const data = await res.json();
        if (data.success) { showToast('✅ تم إنهاء الجلسة', 'success'); loadSessions(); }
        else showToast('❌ ' + data.message, 'error');
    } catch (_) { showToast('❌ فشل', 'error'); }
    if (btn) btn.disabled = false;
}

async function revokeAllSessions() {
    if (!confirm('هل أنت متأكد من إنهاء جميع الجلسات الأخرى؟')) return;
    try {
        const res  = await fetch('/api/auth/sessions/revoke-all', {method:'POST'});
        const data = await res.json();
        if (data.success) { showToast('✅ تم إنهاء جميع الجلسات', 'success'); loadSessions(); }
        else showToast('❌ ' + data.message, 'error');
    } catch (_) { showToast('❌ فشل', 'error'); }
}

// ─── التحقق بخطوتين ────────────────────────────────────────────
async function show2FASettings() {
    closeSettings();
    let hasFA = false;
    try {
        const r = await fetch('/api/auth/2fa/status');
        const d = await r.json();
        hasFA = d.has_2fa;
    } catch (_) {}

    const el = document.createElement('div');
    el.className = 'modal fade';
    el.tabIndex = -1;
    el.innerHTML = `
        <div class="modal-dialog modal-dialog-centered modal-sm">
            <div class="modal-content" style="background:#1a1a2e;color:#e0e0e0;border:1px solid rgba(255,255,255,.05);">
                <div class="modal-header" style="border-bottom:1px solid rgba(255,255,255,.05);">
                    <h5 class="modal-title"><i class="fas fa-lock" style="color:${hasFA?'#2ecc71':'#f9ca24'};"></i> التحقق بخطوتين</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal" style="filter:invert(1);"></button>
                </div>
                <div class="modal-body">
                    <div style="text-align:center;margin-bottom:16px;">
                        <div style="font-size:40px;">${hasFA?'🔒':'🔓'}</div>
                        <div style="color:${hasFA?'#2ecc71':'#f9ca24'};font-weight:600;margin-top:8px;">
                            ${hasFA?'التحقق بخطوتين مفعَّل':'التحقق بخطوتين غير مفعَّل'}
                        </div>
                    </div>
                    ${hasFA ? `
                        <div class="mb-3">
                            <label style="color:#aaa;font-size:13px;">كلمة المرور الحالية</label>
                            <input type="password" id="fa_cur_pwd" class="form-control"
                                   style="background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.08);color:#e0e0e0;border-radius:10px;padding:10px;"
                                   placeholder="أدخل كلمة المرور الحالية">
                        </div>
                        <button class="btn btn-danger w-100" onclick="disable2FA()" style="border-radius:10px;">
                            <i class="fas fa-lock-open"></i> تعطيل التحقق بخطوتين
                        </button>` : `
                        <div class="mb-3">
                            <label style="color:#aaa;font-size:13px;">كلمة المرور الجديدة</label>
                            <input type="password" id="fa_new_pwd" class="form-control"
                                   style="background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.08);color:#e0e0e0;border-radius:10px;padding:10px;"
                                   placeholder="6 أحرف على الأقل">
                        </div>
                        <div class="mb-3">
                            <label style="color:#aaa;font-size:13px;">تلميح (اختياري)</label>
                            <input type="text" id="fa_hint" class="form-control"
                                   style="background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.08);color:#e0e0e0;border-radius:10px;padding:10px;"
                                   placeholder="تلميح لتتذكر كلمة المرور">
                        </div>
                        <button class="btn btn-success w-100" onclick="enable2FA()" style="border-radius:10px;background:linear-gradient(135deg,#00d2ff,#3a7bd5);border:none;">
                            <i class="fas fa-lock"></i> تفعيل التحقق بخطوتين
                        </button>`}
                </div>
            </div>
        </div>`;
    document.body.appendChild(el);
    new bootstrap.Modal(el).show();
}

async function enable2FA() {
    const pwd  = document.getElementById('fa_new_pwd')?.value?.trim();
    const hint = document.getElementById('fa_hint')?.value?.trim() || 'كلمة المرور';
    if (!pwd || pwd.length < 6) { showToast('⚠️ كلمة المرور يجب 6 أحرف على الأقل', 'warning'); return; }
    try {
        const res  = await fetch('/api/auth/2fa/enable', {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body:   JSON.stringify({password: pwd, hint}),
        });
        const data = await res.json();
        showToast(data.success ? '🔒 تم تفعيل التحقق بخطوتين' : '❌ '+data.message,
                  data.success ? 'success' : 'error');
        if (data.success) document.querySelector('.modal.show')?.querySelector('[data-bs-dismiss]')?.click();
    } catch (_) { showToast('❌ فشل', 'error'); }
}

async function disable2FA() {
    const pwd = document.getElementById('fa_cur_pwd')?.value?.trim();
    if (!pwd) { showToast('⚠️ أدخل كلمة المرور الحالية', 'warning'); return; }
    try {
        const res  = await fetch('/api/auth/2fa/disable', {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body:   JSON.stringify({current_password: pwd}),
        });
        const data = await res.json();
        showToast(data.success ? '🔓 تم تعطيل التحقق بخطوتين' : '❌ '+data.message,
                  data.success ? 'success' : 'error');
        if (data.success) document.querySelector('.modal.show')?.querySelector('[data-bs-dismiss]')?.click();
    } catch (_) { showToast('❌ فشل', 'error'); }
}

// ─── مزامنة GitHub ────────────────────────────────────────────
async function manualSync() {
    const btn = document.getElementById('syncBtn');
    if (btn) { btn.innerHTML = '<i class="fas fa-sync fa-spin"></i>'; btn.disabled = true; }
    try {
        const res  = await fetch('/api/sync/github', {method: 'POST'});
        const data = await res.json();
        showToast(data.success ? '☁️ بدأت المزامنة مع GitHub' : '❌ '+data.message,
                  data.success ? 'success' : 'error');
    } catch (_) { showToast('❌ فشل', 'error'); }
    setTimeout(() => {
        if (btn) { btn.innerHTML = '<i class="fas fa-cloud-upload-alt"></i> مزامنة'; btn.disabled = false; }
    }, 3000);
}

async function initExt() {
    // السمة المحفوظة
    const savedTheme = localStorage.getItem('theme') || 'dark';
    applyTheme(savedTheme);

    // تهيئة القوائم
    MsgCtx.init();
    ChatCtx.init();
    ReactPicker.init();

    // تحميل حالات المحادثات
    await loadChatStates();

    // أحداث Socket.IO الإضافية
    setupExtSocketEvents();

    // تفعيل Infinite Scroll
    setupInfiniteScroll();

    // اختصار لوحة المفاتيح: Ctrl+F للبحث
    document.addEventListener('keydown', e => {
        if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
            e.preventDefault();
            showSearch();
        }
    });

    // إغلاق اللوحات بالنقر على الـ overlay
    document.getElementById('panelOverlay')?.addEventListener('click', () => {
        closeProfile();
        closeSettings();
    });
}
