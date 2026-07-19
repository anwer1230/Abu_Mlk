// static/js/sync.js — مركز سرعة إنجاز
// المرحلة 12: المزامنة الفورية بين الأجهزة

class SyncManager {
    constructor() {
        this.devices      = [];
        this.isSyncing    = false;
        this.lastSyncTime = null;
        this.syncInterval = 30000; // 30 ثانية
        this._intervalId  = null;
    }

    init() {
        this._loadDeviceId();
        this.loadDevices();
        this._intervalId = setInterval(() => this.sync(), this.syncInterval);
        this._bindSocketEvents();
        console.log('🔄 SyncManager: جاهز');
    }

    destroy() {
        if (this._intervalId) clearInterval(this._intervalId);
    }

    // ─── معرف الجهاز ─────────────────────────────────────────────
    _loadDeviceId() {
        let id = localStorage.getItem('device_id');
        if (!id) {
            id = 'dev_' + Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
            localStorage.setItem('device_id', id);
        }
        this.deviceId = id;
    }

    _deviceType() {
        return /Mobi|Android/i.test(navigator.userAgent) ? 'mobile' : 'desktop';
    }

    // ─── ربط Socket.IO ───────────────────────────────────────────
    _bindSocketEvents() {
        const s = window.socket || window.io?.();
        if (!s) return;

        s.on('sync_update', (data) => {
            this._applyChanges(data.changes);
            this._showToast('🔄 تمت مزامنة من جهاز آخر', 'info');
        });

        s.on('device_connected', (data) => {
            this._showToast(`📱 جهاز "${data.device_name}" متصل`, 'info');
            this.loadDevices();
        });

        s.on('device_disconnected', (data) => {
            this._showToast(`📴 جهاز "${data.device_name}" غير متصل`, 'warning');
            this.loadDevices();
        });
    }

    // ─── تحميل الأجهزة المتصلة ──────────────────────────────────
    async loadDevices() {
        try {
            const res  = await fetch('/api/sync/devices');
            const data = await res.json();
            if (data.success) {
                this.devices = data.devices || [];
                this._renderDevices();
            }
        } catch (e) {
            console.error('SyncManager: فشل تحميل الأجهزة:', e);
        }
    }

    // ─── مزامنة رئيسية ──────────────────────────────────────────
    async sync() {
        if (this.isSyncing) return;
        this.isSyncing = true;
        try {
            const res = await fetch('/api/sync/status');
            const data = await res.json();
            if (data.success) {
                this.lastSyncTime = data.last_sync;
                this._updateSyncUI(true);
            }
        } catch (e) {
            this._updateSyncUI(false);
        } finally {
            this.isSyncing = false;
        }
    }

    // ─── مزامنة يدوية مع GitHub ─────────────────────────────────
    async syncToGitHub() {
        try {
            this._updateSyncUI(null, 'جاري الرفع إلى GitHub...');
            const res  = await fetch('/api/sync/github', { method: 'POST' });
            const data = await res.json();
            if (data.success) {
                this._showToast('☁️ تمت المزامنة مع GitHub', 'success');
                this._updateSyncUI(true);
            } else {
                this._showToast('⚠️ فشلت المزامنة', 'warning');
                this._updateSyncUI(false);
            }
        } catch (e) {
            this._updateSyncUI(false);
        }
    }

    // ─── تصدير واستيراد البيانات ─────────────────────────────────
    async exportData() {
        try {
            const res  = await fetch('/api/sync/export');
            const data = await res.json();
            if (data.success) {
                const blob = new Blob([JSON.stringify(data.data, null, 2)], { type: 'application/json' });
                const url  = URL.createObjectURL(blob);
                const a    = document.createElement('a');
                a.href     = url;
                a.download = `speedengaz-backup-${Date.now()}.json`;
                a.click();
                URL.revokeObjectURL(url);
                this._showToast('✅ تم تصدير البيانات', 'success');
            }
        } catch (e) {
            this._showToast('❌ فشل التصدير', 'error');
        }
    }

    async importData(file) {
        try {
            const text = await file.text();
            const json = JSON.parse(text);
            const res  = await fetch('/api/sync/import', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ data: json })
            });
            const data = await res.json();
            if (data.success) {
                this._showToast(`✅ تم استيراد ${data.imported} عنصر`, 'success');
            }
        } catch (e) {
            this._showToast('❌ فشل الاستيراد', 'error');
        }
    }

    // ─── تطبيق التغييرات الواردة ─────────────────────────────────
    _applyChanges(changes) {
        if (!changes) return;
        // تحديث إعدادات السمة
        if (changes.settings?.theme && window.setTheme) {
            window.setTheme(changes.settings.theme);
        }
        // إعادة رسم قائمة المحادثات إذا تغيّرت
        if (changes.chats && window.renderChatList) {
            window.renderChatList(changes.chats);
        }
    }

    // ─── واجهة الأجهزة ───────────────────────────────────────────
    _renderDevices() {
        const el = document.getElementById('devicesList');
        if (!el) return;
        if (!this.devices.length) {
            el.innerHTML = '<p style="color:#555; font-size:13px; text-align:center;">لا توجد أجهزة أخرى متصلة</p>';
            return;
        }
        el.innerHTML = this.devices.map(d => `
            <div style="display:flex; align-items:center; gap:12px; padding:10px 0; border-bottom:1px solid rgba(255,255,255,0.04)">
                <i class="fas fa-${d.type === 'mobile' ? 'mobile-alt' : 'laptop'} fa-lg" style="color:${d.is_online ? '#2ecc71' : '#555'}; width:24px; text-align:center;"></i>
                <div style="flex:1">
                    <div style="font-size:14px; font-weight:500">
                        ${d.name || 'جهاز'} ${d.id === this.deviceId ? '<span style="color:#00d2ff; font-size:11px">(هذا الجهاز)</span>' : ''}
                    </div>
                    <div style="font-size:12px; color:#777">${d.last_active || ''}</div>
                </div>
                <span style="font-size:12px; padding:3px 10px; border-radius:12px; background:${d.is_online ? 'rgba(46,204,113,0.1)' : 'rgba(255,255,255,0.05)'}; color:${d.is_online ? '#2ecc71' : '#666'}">
                    ${d.is_online ? '● متصل' : '○ غير متصل'}
                </span>
            </div>
        `).join('');
    }

    // ─── تحديث مؤشر المزامنة ─────────────────────────────────────
    _updateSyncUI(success, msg = null) {
        const el = document.getElementById('syncIndicator');
        if (!el) return;
        if (success === null) {
            el.textContent = msg || '🔄 جاري المزامنة...';
            el.style.color = '#f9ca24';
        } else if (success) {
            const t = this.lastSyncTime || new Date().toLocaleTimeString('ar');
            el.innerHTML = `<i class="fas fa-check-circle" style="color:#2ecc71"></i> متزامن — ${t}`;
            el.style.color = '#2ecc71';
        } else {
            el.innerHTML = `<i class="fas fa-exclamation-circle" style="color:#f9ca24"></i> فشل — جاري المحاولة`;
            el.style.color = '#f9ca24';
        }
    }

    // ─── إشعار بسيط ──────────────────────────────────────────────
    _showToast(msg, type = 'info') {
        if (window.showToast) { window.showToast(msg, type); return; }
        console.log(`[SyncManager] ${msg}`);
    }
}

// ─── تصدير عام ──────────────────────────────────────────────────
window.syncManager = new SyncManager();
document.addEventListener('DOMContentLoaded', () => {
    // تأخير قصير للسماح للـ Socket.IO بالاتصال أولاً
    setTimeout(() => window.syncManager.init(), 1500);
});
