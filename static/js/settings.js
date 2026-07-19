// ================================================================
//  settings.js — مركز سرعة إنجاز
//  المرحلة 10: إعدادات التطبيق (سمات، لغة، إشعارات، تخزين)
// ================================================================

'use strict';

// ═══════════════════════════════════════════════════════════════
//  المظهر (السمة)
// ═══════════════════════════════════════════════════════════════

function setTheme(theme) {
    document.querySelectorAll('.theme-btn').forEach(btn =>
        btn.classList.toggle('active', btn.dataset.theme === theme)
    );

    let applied = theme;
    if (theme === 'auto') {
        applied = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }
    document.documentElement.setAttribute('data-theme', applied);
    document.body.setAttribute('data-theme', applied);
    localStorage.setItem('theme', theme);

    // إرسال التفضيل إلى الخادم
    fetch('/api/settings/theme', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ theme })
    }).catch(() => {});

    _toast(`🎨 تم تطبيق السمة ${theme === 'dark' ? 'الليلية' : theme === 'light' ? 'النهارية' : 'التلقائية'}`, 'success');
}

// ═══════════════════════════════════════════════════════════════
//  الإشعارات
// ═══════════════════════════════════════════════════════════════

function toggleNotifications(enabled) {
    localStorage.setItem('notifications', enabled);
    if (enabled && 'Notification' in window && Notification.permission === 'default') {
        Notification.requestPermission();
    }
    _toast(enabled ? '🔔 تم تفعيل الإشعارات' : '🔕 تم إيقاف الإشعارات', 'info');
}

function toggleSound(enabled) {
    localStorage.setItem('sound', enabled);
    window.notificationSoundEnabled = enabled;
    _toast(enabled ? '🔊 تم تفعيل الصوت' : '🔇 تم إيقاف الصوت', 'info');
}

function toggleVibration(enabled) {
    localStorage.setItem('vibration', enabled);
    if (enabled && navigator.vibrate) navigator.vibrate(200);
    _toast(enabled ? '📳 تم تفعيل الاهتزاز' : '📴 تم إيقاف الاهتزاز', 'info');
}

// ═══════════════════════════════════════════════════════════════
//  التخزين
// ═══════════════════════════════════════════════════════════════

async function loadStorageInfo() {
    try {
        const res  = await fetch('/api/settings/storage');
        const data = await res.json();
        if (data.success) {
            const usedEl = document.getElementById('storageUsed');
            const barEl  = document.getElementById('storageProgress');
            const pct    = Math.min(100, Math.round((data.used / Math.max(data.total, 1)) * 100));
            if (usedEl) usedEl.textContent = `${data.used} MB / ${data.total} MB`;
            if (barEl)  barEl.style.width  = pct + '%';
        }
    } catch (_) {}
}

async function clearCache() {
    if (!confirm('⚠️ هل أنت متأكد من تنظيف الذاكرة المؤقتة؟')) return;
    try {
        const res  = await fetch('/api/settings/clear-cache', { method: 'POST' });
        const data = await res.json();
        if (data.success) {
            _toast('✅ تم تنظيف الذاكرة المؤقتة (' + (data.freed_mb || 0) + ' MB محرر)', 'success');
            loadStorageInfo();
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

document.addEventListener('DOMContentLoaded', function () {
    // تطبيق السمة المحفوظة
    const savedTheme = localStorage.getItem('theme') || 'dark';
    setTheme(savedTheme);

    // مزامنة التبديلات مع localStorage
    const swNotif  = document.querySelector('[onchange*="toggleNotifications"]');
    const swSound  = document.querySelector('[onchange*="toggleSound"]');
    const swVibr   = document.querySelector('[onchange*="toggleVibration"]');

    if (swNotif)  swNotif.checked  = localStorage.getItem('notifications')  !== 'false';
    if (swSound)  swSound.checked  = localStorage.getItem('sound')          !== 'false';
    if (swVibr)   swVibr.checked   = localStorage.getItem('vibration')      !== 'false';

    // تحميل معلومات التخزين
    loadStorageInfo();

    // ضبط اختيار الخصوصية المحفوظ
    const privacySelects = document.querySelectorAll('.privacy-select');
    privacySelects.forEach(sel => {
        const key = sel.dataset.key;
        if (key && localStorage.getItem('priv_' + key)) {
            sel.value = localStorage.getItem('priv_' + key);
        }
        sel.onchange = () => {
            if (key) localStorage.setItem('priv_' + key, sel.value);
            fetch('/api/settings', {
                method:  'POST',
                headers: { 'Content-Type': 'application/json' },
                body:    JSON.stringify({ [key]: sel.value })
            }).catch(() => {});
        };
    });
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
        transition:opacity .3s;
    `;
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(() => { t.style.opacity = '0'; setTimeout(() => t.remove(), 350); }, 3000);
}
