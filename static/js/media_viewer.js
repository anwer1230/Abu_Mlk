// ================================================================
//  media_viewer.js — مركز سرعة إنجاز
//  المرحلة 7: معرض الوسائط + Lightbox + مشاركة + تحميل
// ================================================================

'use strict';

let _gallery      = [];   // [{url, type, caption}]
let _galleryIndex = 0;

// ─── فتح عارض الوسائط ──────────────────────────────────────────

function openMediaViewer(url, allMedia) {
    if (!url) return;

    _gallery = Array.isArray(allMedia) && allMedia.length
        ? allMedia
        : [{ url, type: _guessType(url) }];

    _galleryIndex = _gallery.findIndex(m => m.url === url);
    if (_galleryIndex < 0) _galleryIndex = 0;

    _renderViewer();

    const el = document.getElementById('mediaViewerModal');
    if (!el) return;

    // Bootstrap modal
    if (typeof bootstrap !== 'undefined' && bootstrap.Modal) {
        const modal = bootstrap.Modal.getOrCreateInstance(el);
        modal.show();
    } else {
        el.style.display = 'flex';
    }

    document.addEventListener('keydown', _viewerKey);
}

// ─── غلق العارض ─────────────────────────────────────────────────

function closeMediaViewer() {
    const el = document.getElementById('mediaViewerModal');
    if (!el) return;
    if (typeof bootstrap !== 'undefined' && bootstrap.Modal) {
        const m = bootstrap.Modal.getInstance(el);
        if (m) m.hide();
    } else {
        el.style.display = 'none';
    }
    // وقف الفيديو إن وجد
    const vid = el.querySelector('video');
    if (vid) { vid.pause(); vid.src = ''; }
    document.removeEventListener('keydown', _viewerKey);
}

function _viewerKey(e) {
    if (e.key === 'Escape')       closeMediaViewer();
    if (e.key === 'ArrowLeft')    nextMedia();
    if (e.key === 'ArrowRight')   prevMedia();
}

// ─── عرض الوسيط الحالي ──────────────────────────────────────────

function _renderViewer() {
    const container = document.getElementById('mediaViewerContent');
    const counter   = document.getElementById('mediaCounter');
    if (!container) return;

    const media = _gallery[_galleryIndex] || {};
    const url   = media.url || '';
    const type  = media.type || _guessType(url);

    // وقف أي فيديو سابق
    const oldVid = container.querySelector('video');
    if (oldVid) { oldVid.pause(); oldVid.src = ''; }

    if (type === 'image') {
        container.innerHTML = `
            <img src="${url}"
                 alt="${media.caption || 'وسائط'}"
                 style="max-width:90vw;max-height:85vh;object-fit:contain;border-radius:8px;display:block;margin:auto;">
        `;
    } else if (type === 'video') {
        container.innerHTML = `
            <video src="${url}" controls autoplay
                   style="max-width:90vw;max-height:85vh;border-radius:8px;display:block;margin:auto;"></video>
        `;
    } else if (type === 'audio') {
        container.innerHTML = `
            <div style="text-align:center;padding:40px 20px;">
                <i class="fas fa-music" style="font-size:64px;color:#f9ca24;display:block;margin-bottom:20px;"></i>
                <audio src="${url}" controls style="width:320px;max-width:90vw;"></audio>
                <div style="color:#888;margin-top:12px;font-size:13px;">${media.caption || url.split('/').pop()}</div>
            </div>
        `;
    } else {
        container.innerHTML = `
            <div style="text-align:center;padding:60px 20px;">
                <i class="fas fa-file-alt" style="font-size:64px;color:#3a7bd5;display:block;margin-bottom:20px;"></i>
                <div style="color:#e0e0e0;font-size:16px;margin-bottom:16px;">${media.caption || url.split('/').pop()}</div>
                <a href="${url}" download
                   style="background:linear-gradient(135deg,#00d2ff,#3a7bd5);color:#fff;
                          padding:10px 24px;border-radius:10px;text-decoration:none;font-size:14px;">
                    <i class="fas fa-download"></i> تحميل الملف
                </a>
            </div>
        `;
    }

    if (counter)
        counter.textContent = `${_galleryIndex + 1} / ${_gallery.length}`;

    // إظهار / إخفاء أزرار التنقل
    const btnPrev = document.getElementById('viewerPrevBtn');
    const btnNext = document.getElementById('viewerNextBtn');
    if (btnPrev) btnPrev.style.opacity = _galleryIndex > 0 ? '1' : '0.3';
    if (btnNext) btnNext.style.opacity = _galleryIndex < _gallery.length - 1 ? '1' : '0.3';
}

// ─── التنقل بين الوسائط ─────────────────────────────────────────

function nextMedia() {
    if (_galleryIndex < _gallery.length - 1) {
        _galleryIndex++;
        _renderViewer();
    }
}

function prevMedia() {
    if (_galleryIndex > 0) {
        _galleryIndex--;
        _renderViewer();
    }
}

// ─── تحميل الوسيط الحالي ────────────────────────────────────────

function downloadCurrentMedia() {
    const media = _gallery[_galleryIndex];
    if (!media) return;
    const a = document.createElement('a');
    a.href     = media.url;
    a.download = media.url.split('/').pop() || 'media';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
}

// ─── مشاركة الوسيط الحالي ────────────────────────────────────────

function shareCurrentMedia() {
    const media = _gallery[_galleryIndex];
    if (!media) return;
    if (navigator.share) {
        navigator.share({ title: 'مشاركة وسائط', url: media.url }).catch(() => {});
    } else {
        navigator.clipboard.writeText(media.url).then(() => {
            if (typeof showToast === 'function')
                showToast('✅ تم نسخ رابط الوسيط', 'success');
        });
    }
}

// ─── مساعد: تخمين نوع الوسيط من الرابط ──────────────────────────

function _guessType(url) {
    if (!url) return 'file';
    const ext = (url.split('?')[0].split('.').pop() || '').toLowerCase();
    if (['jpg','jpeg','png','gif','webp','bmp','svg'].includes(ext)) return 'image';
    if (['mp4','webm','ogg','mov','avi'].includes(ext))               return 'video';
    if (['mp3','wav','ogg','aac','m4a'].includes(ext))                return 'audio';
    return 'file';
}

// ─── تحميل الوسيط من API ثم فتح العارض ────────────────────────
// (يستبدل loadAndShowMedia إن كان مُعرَّفاً مسبقاً)

window.loadAndShowMedia = async function(chatId, msgId, isVideo) {
    if (typeof showToast === 'function')
        showToast('⏳ جارٍ تحميل الوسيط...', 'info');
    try {
        const res  = await fetch(`/api/media/${chatId}/${msgId}`);
        const data = await res.json();
        if (data.success) {
            const src  = `data:${data.mime};base64,${data.data}`;
            const type = isVideo ? 'video' : (data.mime.startsWith('audio') ? 'audio' : 'image');
            openMediaViewer(src, [{ url: src, type }]);
        } else {
            if (typeof showToast === 'function')
                showToast('❌ ' + data.message, 'error');
        }
    } catch (e) {
        if (typeof showToast === 'function')
            showToast('❌ فشل تحميل الوسيط', 'error');
    }
};
