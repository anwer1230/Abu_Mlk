// static/js/privacy.js — مركز سرعة إنجاز
// المرحلة 11: إعدادات الخصوصية + إدارة المستخدمين المحظورين

// ─── أدوات مساعدة ────────────────────────────────────────────────

function showToast(msg, type = 'info') {
    const c = document.getElementById('toastContainer');
    if (!c) return;
    const t = document.createElement('div');
    t.className = 'toast-msg';
    const colors = { success: '#2ecc71', error: '#ff4757', info: '#00d2ff', warning: '#f9ca24' };
    t.style.borderLeft = `3px solid ${colors[type] || colors.info}`;
    t.textContent = msg;
    c.appendChild(t);
    setTimeout(() => t.style.opacity = '0', 2500);
    setTimeout(() => t.remove(), 2900);
}

// ─── تحميل عند بدء الصفحة ──────────────────────────────────────

document.addEventListener('DOMContentLoaded', function () {
    loadPrivacySettings();
    loadBlockedUsers();
    loadSyncStatus();
});

// ─── إعدادات الخصوصية ──────────────────────────────────────────

async function loadPrivacySettings() {
    try {
        const res = await fetch('/api/privacy/settings');
        const data = await res.json();
        if (data.success) {
            const p = data.privacy || {};
            const set = (id, key, def) => {
                const el = document.getElementById(id);
                if (el) el.value = p['privacy_' + key] || p[key] || def;
            };
            set('lastSeenPrivacy', 'last_seen', 'everyone');
            set('photoPrivacy', 'photo', 'everyone');
            set('phonePrivacy', 'phone', 'everyone');
            set('readReceiptPrivacy', 'read_receipts', 'everyone');
        }
    } catch (e) {
        console.error('❌ فشل تحميل إعدادات الخصوصية:', e);
    }
}

async function updatePrivacy(setting, value) {
    try {
        const res = await fetch('/api/privacy/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ key: setting, value })
        });
        const data = await res.json();
        if (data.success) {
            showToast('✅ تم حفظ الإعداد', 'success');
        } else {
            showToast('❌ فشل الحفظ', 'error');
        }
    } catch (e) {
        showToast('❌ خطأ في الاتصال', 'error');
    }
}

// ─── المزامنة ───────────────────────────────────────────────────

async function loadSyncStatus() {
    try {
        const res = await fetch('/api/sync/status');
        const data = await res.json();
        const el = document.getElementById('syncStatus');
        if (el && data.success) {
            el.textContent = `آخر مزامنة: ${data.last_sync || 'لم تتم بعد'}`;
        }
    } catch (e) { /* صامت */ }
}

async function syncNow() {
    showToast('🔄 جاري المزامنة مع GitHub...', 'info');
    try {
        const res = await fetch('/api/sync/github', { method: 'POST' });
        const data = await res.json();
        if (data.success) {
            showToast('✅ تمت المزامنة بنجاح', 'success');
            loadSyncStatus();
        } else {
            showToast('⚠️ ' + (data.message || 'فشلت المزامنة'), 'warning');
        }
    } catch (e) {
        showToast('❌ فشل الاتصال', 'error');
    }
}

// ─── المستخدمون المحظورون ───────────────────────────────────────

async function loadBlockedUsers() {
    try {
        const res = await fetch('/api/blocked/users');
        const data = await res.json();
        if (data.success) {
            renderBlockedUsers(data.users || []);
            const badge = document.getElementById('blockedCount');
            if (badge) badge.textContent = (data.users || []).length;
        }
    } catch (e) {
        console.error('❌ فشل تحميل المحظورين:', e);
    }
}

function renderBlockedUsers(users) {
    const container = document.getElementById('blockedUsersList');
    if (!container) return;
    if (!users || users.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-user-check" style="color:#555"></i>
                <span style="font-size:13px">لا يوجد مستخدمون محظورون</span>
            </div>`;
        return;
    }
    container.innerHTML = users.map(u => `
        <div class="blocked-user-item">
            <div class="avatar">${(u.name || u.username || 'U')[0].toUpperCase()}</div>
            <div class="user-info">
                <div class="name">${u.name || u.username || 'مستخدم'}</div>
                <div class="phone">${u.phone || u.user_id || ''}</div>
            </div>
            <button class="btn-unblock" onclick="unblockUser('${u.blocked_user_id || u.id}')">
                <i class="fas fa-user-check me-1"></i> إلغاء الحظر
            </button>
        </div>
    `).join('');
}

function showBlockModal() {
    const id = prompt('أدخل معرف المستخدم أو رقم الهاتف لحظره:');
    if (id && id.trim()) {
        blockUser(id.trim());
    }
}

async function blockUser(identifier) {
    try {
        // محاولة كعدد صحيح أولاً
        const userId = parseInt(identifier);
        const endpoint = isNaN(userId)
            ? `/api/blocked/users?phone=${encodeURIComponent(identifier)}`
            : `/api/users/${userId}/block`;
        const res = await fetch(endpoint, { method: 'POST' });
        const data = await res.json();
        if (data.success) {
            showToast('✅ تم حظر المستخدم', 'success');
            loadBlockedUsers();
        } else {
            showToast('❌ ' + (data.message || 'فشل الحظر'), 'error');
        }
    } catch (e) {
        showToast('❌ حدث خطأ', 'error');
    }
}

async function unblockUser(userId) {
    if (!confirm('هل أنت متأكد من إلغاء الحظر؟')) return;
    try {
        const res = await fetch(`/api/users/${userId}/block`, { method: 'DELETE' });
        const data = await res.json();
        if (data.success) {
            showToast('✅ تم إلغاء الحظر', 'success');
            loadBlockedUsers();
        } else {
            showToast('❌ ' + (data.message || 'فشل'), 'error');
        }
    } catch (e) {
        showToast('❌ حدث خطأ', 'error');
    }
}
