// ================================================================
//  security_settings.js — مركز سرعة إنجاز
//  المرحلة 9: التحقق بخطوتين (2FA) + الجلسات النشطة
// ================================================================

'use strict';

let _2faEnabled = false;

// ═══════════════════════════════════════════════════════════════
//  التحقق بخطوتين (2FA)
// ═══════════════════════════════════════════════════════════════

async function toggleTwoFactor() {
    if (!_2faEnabled) {
        _showTwoFactorSetup();
    } else {
        const pwd = prompt('أدخل كلمة المرور الحالية لإلغاء التحقق بخطوتين:');
        if (pwd) await _disableTwoFactor(pwd);
    }
}

function _showTwoFactorSetup() {
    const pwd = prompt('أدخل كلمة مرور جديدة للتحقق بخطوتين (6 أحرف على الأقل):');
    if (!pwd || pwd.length < 6) {
        _toast('⚠️ كلمة المرور يجب أن تكون 6 أحرف على الأقل', 'warning');
        return;
    }
    const pwd2 = prompt('أعد إدخال كلمة المرور للتأكيد:');
    if (pwd !== pwd2) {
        _toast('❌ كلمات المرور غير متطابقة', 'error');
        return;
    }
    const hint = prompt('أدخل تلميحاً لكلمة المرور (اختياري):') || '';
    _enableTwoFactor(pwd, hint);
}

async function _enableTwoFactor(password, hint) {
    try {
        const res  = await fetch('/api/auth/2fa/enable', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ password, hint })
        });
        const data = await res.json();
        if (data.success) {
            _2faEnabled = true;
            _update2faUI();
            _toast('✅ تم تفعيل التحقق بخطوتين', 'success');
        } else {
            _toast('❌ ' + data.message, 'error');
        }
    } catch (_) {
        _toast('❌ حدث خطأ في الاتصال', 'error');
    }
}

async function _disableTwoFactor(password) {
    try {
        const res  = await fetch('/api/auth/2fa/disable', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ current_password: password })
        });
        const data = await res.json();
        if (data.success) {
            _2faEnabled = false;
            _update2faUI();
            _toast('✅ تم إلغاء التحقق بخطوتين', 'success');
        } else {
            _toast('❌ ' + data.message, 'error');
        }
    } catch (_) {
        _toast('❌ حدث خطأ في الاتصال', 'error');
    }
}

function _update2faUI() {
    const statusEl = document.getElementById('twoFactorStatus');
    const btnEl    = document.getElementById('twoFactorBtn');
    if (!statusEl || !btnEl) return;
    if (_2faEnabled) {
        statusEl.textContent = 'مفعّل ✅';
        statusEl.className   = 'badge bg-success ms-auto';
        btnEl.innerHTML      = '<i class="fas fa-unlock"></i> إلغاء التفعيل';
        btnEl.className      = 'btn btn-danger';
    } else {
        statusEl.textContent = 'غير مفعّل';
        statusEl.className   = 'badge bg-secondary ms-auto';
        btnEl.innerHTML      = '<i class="fas fa-lock"></i> تفعيل';
        btnEl.className      = 'btn btn-primary';
    }
}

// ═══════════════════════════════════════════════════════════════
//  الجلسات النشطة
// ═══════════════════════════════════════════════════════════════

async function loadSessions() {
    try {
        const res  = await fetch('/api/auth/sessions');
        const data = await res.json();
        if (data.success) {
            _renderSessions(data.sessions || []);
            const cnt = document.getElementById('sessionCount');
            if (cnt) cnt.textContent = data.sessions.length;
        } else {
            _toast('❌ ' + data.message, 'error');
        }
    } catch (_) {
        _toast('❌ فشل تحميل الجلسات', 'error');
    }
}

function _renderSessions(sessions) {
    const container = document.getElementById('sessionsList');
    if (!container) return;
    container.innerHTML = '';

    if (!sessions.length) {
        container.innerHTML = '<div style="color:#666;font-size:13px;padding:12px 0;">لا توجد جلسات نشطة</div>';
        return;
    }

    sessions.forEach(s => {
        const isMobile = (s.platform || '').toLowerCase().includes('android') ||
                         (s.platform || '').toLowerCase().includes('ios');
        const div = document.createElement('div');
        div.className = 'session-item';
        const lastActive = s.date_active
            ? new Date(s.date_active * 1000).toLocaleString('ar')
            : 'غير معروف';
        div.innerHTML = `
            <div class="session-icon">
                <i class="fas fa-${isMobile ? 'mobile-alt' : 'laptop'}"></i>
            </div>
            <div class="session-info">
                <div class="device">${s.device || s.app || 'جهاز غير معروف'}</div>
                <div class="details">${s.country || ''} ${s.ip ? '• ' + s.ip : ''}</div>
                <div class="details">آخر نشاط: ${lastActive}</div>
            </div>
            <span class="session-status ${s.current ? 'active' : 'other'}">
                ${s.current ? '🟢 الجلسة الحالية' : ''}
            </span>
            ${!s.current ? `<button class="btn btn-sm btn-outline-danger ms-2"
                onclick="terminateSession(${s.hash})">
                <i class="fas fa-times"></i></button>` : ''}
        `;
        container.appendChild(div);
    });
}

async function terminateSession(hash) {
    if (!confirm('هل أنت متأكد من إنهاء هذه الجلسة؟')) return;
    try {
        const res  = await fetch('/api/auth/sessions/revoke', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ hash })
        });
        const data = await res.json();
        if (data.success) {
            _toast('✅ تم إنهاء الجلسة', 'success');
            loadSessions();
        } else {
            _toast('❌ ' + data.message, 'error');
        }
    } catch (_) {
        _toast('❌ حدث خطأ', 'error');
    }
}

async function terminateAllSessions() {
    if (!confirm('⚠️ سيتم إنهاء جميع الجلسات الأخرى. هل أنت متأكد؟')) return;
    try {
        const res  = await fetch('/api/auth/sessions/revoke-all', { method: 'POST' });
        const data = await res.json();
        if (data.success) {
            _toast('✅ تم إنهاء جميع الجلسات', 'success');
            loadSessions();
        } else {
            _toast('❌ ' + data.message, 'error');
        }
    } catch (_) {
        _toast('❌ حدث خطأ', 'error');
    }
}

// ═══════════════════════════════════════════════════════════════
//  تهيئة الصفحة
// ═══════════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', async function () {
    // تحميل الجلسات
    loadSessions();

    // تحميل حالة 2FA
    try {
        const res  = await fetch('/api/auth/2fa/status');
        const data = await res.json();
        if (data.success) {
            _2faEnabled = data.has_2fa || false;
            _update2faUI();
        }
    } catch (_) {}
});

// ═══════════════════════════════════════════════════════════════
//  Toast مدمج للصفحة المستقلة
// ═══════════════════════════════════════════════════════════════

function _toast(msg, type = 'info') {
    if (typeof showToast === 'function') { showToast(msg, type); return; }
    const colors = { success:'#2ecc71', error:'#ff4757', warning:'#f9ca24', info:'#00d2ff' };
    const t = document.createElement('div');
    t.style.cssText = `
        position:fixed;bottom:24px;left:50%;transform:translateX(-50%);
        background:#1a1a2e;color:#fff;border-left:4px solid ${colors[type]||'#888'};
        padding:12px 20px;border-radius:10px;z-index:9999;
        font-family:Tajawal,sans-serif;font-size:14px;
        box-shadow:0 8px 24px rgba(0,0,0,.4);
    `;
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(() => { t.style.opacity='0'; t.style.transition='opacity .3s'; setTimeout(()=>t.remove(),350); }, 3000);
}
