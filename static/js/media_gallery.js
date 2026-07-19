// ================================================================
//  media_gallery.js — مركز سرعة إنجاز
//  المرحلة 8: معرض الوسائط مع التمرير اللانهائي
// ================================================================

'use strict';

let _galleryType   = 'all';
let _galleryOffset = 0;
let _galleryLoading= false;
let _galleryHasMore= true;
let _galleryChatId = null;
let _allMedia      = [];       // جميع الوسائط المحملة للعارض

document.addEventListener('DOMContentLoaded', function () {
    _galleryChatId = _getChatIdFromURL();
    if (!_galleryChatId) {
        document.getElementById('mediaGrid').innerHTML =
            '<div style="grid-column:1/-1;text-align:center;color:#666;padding:40px;">⚠️ لم يتم تحديد المحادثة</div>';
        return;
    }
    _setupTabs();
    _setupInfiniteScroll();
    _loadMedia('all');
});

// ─── قراءة chat_id من URL ─────────────────────────────────────

function _getChatIdFromURL() {
    return new URLSearchParams(window.location.search).get('chat_id');
}

// ─── إعداد التبويبات ─────────────────────────────────────────────

function _setupTabs() {
    document.querySelectorAll('.gallery-tab').forEach(tab => {
        tab.addEventListener('click', function () {
            document.querySelectorAll('.gallery-tab').forEach(t => t.classList.remove('active'));
            this.classList.add('active');
            _galleryType   = this.dataset.type;
            _galleryOffset = 0;
            _galleryHasMore= true;
            _allMedia      = [];
            document.getElementById('mediaGrid').innerHTML = '';
            _loadMedia(_galleryType);
        });
    });
}

// ─── التمرير اللانهائي ──────────────────────────────────────────

function _setupInfiniteScroll() {
    const trigger = document.getElementById('scrollTrigger');
    if (!trigger) return;
    const obs = new IntersectionObserver(entries => {
        if (entries[0].isIntersecting && !_galleryLoading && _galleryHasMore) {
            _loadMedia(_galleryType);
        }
    }, { threshold: 0.1 });
    obs.observe(trigger);
}

// ─── تحميل الوسائط ──────────────────────────────────────────────

async function _loadMedia(type) {
    if (_galleryLoading) return;
    _galleryLoading = true;

    const trigger = document.getElementById('scrollTrigger');
    if (trigger) trigger.textContent = '⏳ جارٍ التحميل...';

    try {
        const url  = `/api/chats/${_galleryChatId}/media?type=${type}&offset=${_galleryOffset}&limit=30`;
        const res  = await fetch(url, { credentials: 'same-origin' });
        const data = await res.json();

        if (data.success) {
            _allMedia.push(...(data.media || []));
            _renderMedia(data.media || []);
            _galleryHasMore  = data.has_more || false;
            _galleryOffset  += (data.media || []).length;
        } else {
            _showEmpty(data.message || 'فشل التحميل');
        }
    } catch (e) {
        _showEmpty('حدث خطأ في الاتصال');
    }

    if (trigger)
        trigger.textContent = _galleryHasMore ? '⏬ تمرير للمزيد' : '✅ تم تحميل كل الوسائط';
    _galleryLoading = false;
}

// ─── عرض الوسائط في الشبكة ──────────────────────────────────────

function _renderMedia(items) {
    const grid = document.getElementById('mediaGrid');
    if (!items.length && _galleryOffset === 0) {
        _showEmpty('لا توجد وسائط من هذا النوع');
        return;
    }

    items.forEach((item, i) => {
        const div = document.createElement('div');
        div.className = 'media-grid-item';

        if (item.type === 'image') {
            const img = document.createElement('img');
            img.src   = item.url;
            img.alt   = item.filename || 'صورة';
            img.loading = 'lazy';
            img.onclick = () => _openItem(item);
            div.appendChild(img);

        } else if (item.type === 'video') {
            div.style.position = 'relative';
            const vid = document.createElement('video');
            vid.src   = item.url;
            vid.muted = true;
            vid.preload = 'metadata';
            vid.onclick = () => _openItem(item);
            div.appendChild(vid);
            const ply = document.createElement('div');
            ply.style.cssText = `
                position:absolute;inset:0;display:flex;align-items:center;
                justify-content:center;pointer-events:none;`;
            ply.innerHTML = '<i class="fas fa-play-circle" style="font-size:28px;color:rgba(255,255,255,.8);"></i>';
            div.appendChild(ply);

        } else {
            // صوت أو مستند
            const icon = item.type === 'audio' ? 'fa-music' : 'fa-file-alt';
            const clr  = item.type === 'audio' ? '#f9ca24' : '#3a7bd5';
            div.innerHTML = `
                <div class="file-icon">
                    <i class="fas ${icon}" style="color:${clr};"></i>
                    <span>${(item.filename || '').substring(0, 16)}</span>
                </div>`;
            div.onclick = () => _openItem(item);
        }

        grid.appendChild(div);
    });
}

// ─── فتح وسيط في العارض ─────────────────────────────────────────

function _openItem(item) {
    if (typeof openMediaViewer === 'function') {
        openMediaViewer(item.url, _allMedia.map(m => ({ url: m.url, type: m.type, caption: m.filename })));
    } else {
        window.open(item.url, '_blank');
    }
}

// ─── تحديث المعرض ────────────────────────────────────────────────

function refreshGallery() {
    _galleryOffset  = 0;
    _galleryHasMore = true;
    _allMedia       = [];
    document.getElementById('mediaGrid').innerHTML = '';
    _loadMedia(_galleryType);
}

// ─── رسالة فارغة ────────────────────────────────────────────────

function _showEmpty(msg) {
    const grid = document.getElementById('mediaGrid');
    if (!grid.children.length) {
        grid.innerHTML = `
            <div style="grid-column:1/-1;text-align:center;color:#666;padding:60px 20px;">
                <i class="fas fa-photo-video" style="font-size:48px;display:block;margin-bottom:16px;"></i>
                ${msg}
            </div>`;
    }
}
