// ════════════════════════════════════════════════════════════════
//  سرعة انجاز — Service Worker v9
//  يتعامل مع: كاش الملفات، Web Push، الإشعارات على الهاتف
// ════════════════════════════════════════════════════════════════
const CACHE_NAME = 'speed-center-v9';
const CACHE_URLS = ['/', '/static/js/app.js', '/static/icons/app-logo.png'];

self.addEventListener('install', e => {
    e.waitUntil(
        caches.open(CACHE_NAME).then(c => c.addAll(CACHE_URLS)).catch(() => {})
    );
    self.skipWaiting();
});

self.addEventListener('activate', e => {
    e.waitUntil(
        caches.keys().then(keys =>
            Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
        ).then(() => self.clients.claim())
    );
});

self.addEventListener('fetch', e => {
    if (e.request.method !== 'GET') return;
    e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
});

// ── استقبال Web Push ──────────────────────────────────────────
self.addEventListener('push', function(event) {
    // قيم افتراضية
    var title = '🔔 تنبيه من سرعة انجاز';
    var body  = 'لديك تنبيه جديد';
    var tag   = 'general-' + Date.now();
    var icon  = '/static/icons/app-logo.png';
    var badge = '/static/icons/app-logo.png';
    var msgData = {};

    try {
        if (event.data) {
            var raw = event.data.json();
            if (raw.title) title = raw.title;
            if (raw.body)  body  = raw.body;
            if (raw.icon)  icon  = raw.icon;
            if (raw.badge) badge = raw.badge;
            msgData = raw.data || {};

            // تخصيص حسب النوع
            if (raw.type === 'schedule_expired') {
                tag = 'schedule_expired';
            } else if (raw.type === 'broadcast') {
                tag = 'broadcast_' + (raw.id || Date.now());
            } else if (raw.tag) {
                tag = raw.tag;
            }
        }
    } catch(e) {}

    // خيارات الإشعار — بسيطة ومتوافقة مع أندرويد وiOS
    var options = {
        body:    body,
        icon:    icon,
        badge:   badge,
        tag:     tag,
        renotify: true,
        requireInteraction: false,   // false أفضل على الهاتف (لا تبقى مفتوحة بقوة)
        silent:  false,
        vibrate: [300, 100, 300],
        dir:     'rtl',
        lang:    'ar',
        data:    Object.assign({ url: '/' }, msgData)
    };

    event.waitUntil(
        self.registration.showNotification(title, options)
            .then(function() {
                // أرسل رسالة للتبويبات المفتوحة لتشغيل الصوت / TTS
                return clients.matchAll({ type: 'window', includeUncontrolled: true });
            })
            .then(function(openClients) {
                openClients.forEach(function(client) {
                    client.postMessage({
                        type:      'SW_NOTIF',
                        notifType: msgData.type || tag,
                        title:     title,
                        body:      body,
                        tag:       tag
                    });
                });
            })
            .catch(function(err) {
                // fallback: في حال فشل الإشعار، حاول بدون خيارات متقدمة
                return self.registration.showNotification(title, { body: body, icon: icon });
            })
    );
});

// ── نقر على الإشعار ──────────────────────────────────────────
self.addEventListener('notificationclick', function(event) {
    event.notification.close();

    var targetUrl = '/';
    try {
        if (event.notification.data && event.notification.data.url) {
            targetUrl = event.notification.data.url;
        }
    } catch(e) {}

    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true })
            .then(function(clientList) {
                // ركّز على تبويبة موجودة
                for (var i = 0; i < clientList.length; i++) {
                    var c = clientList[i];
                    if ('focus' in c) return c.focus();
                }
                // أو افتح تبويبة جديدة
                if (clients.openWindow) return clients.openWindow(targetUrl);
            })
    );
});

// ── رسائل من الصفحة للـ SW ───────────────────────────────────
self.addEventListener('message', function(event) {
    if (event.data && event.data.type === 'SKIP_WAITING') {
        self.skipWaiting();
    }
});
