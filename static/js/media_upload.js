// ================================================================
//  media_upload.js — مركز سرعة إنجاز
//  المرحلة 7: رفع الوسائط المتقدم (صور، فيديو، ملفات، صوت)
// ================================================================

'use strict';

let _mediaFiles  = [];       // [{file, type}]
let _mediaUploading = false;

// ─── إظهار / إخفاء لوحة الرفع ───────────────────────────────────

function toggleMediaUpload() {
    const panel = document.getElementById('mediaUploadPanel');
    if (!panel) return;
    const visible = panel.style.display !== 'none';
    panel.style.display = visible ? 'none' : 'block';
    if (!visible) {
        // إغلاق أي لوحة وسائط قديمة
        if (typeof hideMediaPicker === 'function') hideMediaPicker();
    }
}

function closeMediaUpload() {
    const panel = document.getElementById('mediaUploadPanel');
    if (panel) panel.style.display = 'none';
    clearMediaPreview();
}

// ─── معالجة الملفات المختارة ─────────────────────────────────────

function handleMediaFiles(input, type) {
    const files = Array.from(input.files || []);
    files.forEach(file => _mediaFiles.push({ file, type }));
    renderMediaPreviews();
    input.value = '';
}

function removeMediaFile(index) {
    _mediaFiles.splice(index, 1);
    renderMediaPreviews();
}

function clearMediaPreview() {
    _mediaFiles = [];
    const c = document.getElementById('mediaPreviewContainer');
    if (c) c.innerHTML = '';
}

// ─── عرض المعاينة ───────────────────────────────────────────────

function renderMediaPreviews() {
    const container = document.getElementById('mediaPreviewContainer');
    if (!container) return;
    container.innerHTML = '';

    _mediaFiles.forEach((item, index) => {
        const wrap = document.createElement('div');
        wrap.className = 'media-preview-item';
        wrap.style.cssText = `
            display:inline-block; position:relative; margin:4px;
            width:90px; height:90px; border-radius:10px; overflow:hidden;
            background:rgba(255,255,255,0.04);
            border:1px solid rgba(255,255,255,0.08);
            vertical-align:top;
        `;

        // زر الحذف
        const rm = document.createElement('button');
        rm.style.cssText = `
            position:absolute; top:3px; right:3px; z-index:5;
            background:rgba(220,53,69,.85); border:none; color:#fff;
            border-radius:50%; width:20px; height:20px; cursor:pointer;
            display:flex; align-items:center; justify-content:center;
            font-size:10px; padding:0;
        `;
        rm.innerHTML = '✕';
        rm.onclick = () => removeMediaFile(index);

        if (item.type === 'image') {
            const img = document.createElement('img');
            img.src = URL.createObjectURL(item.file);
            img.style.cssText = 'width:100%;height:100%;object-fit:cover;';
            wrap.appendChild(img);
        } else if (item.type === 'video') {
            const vid = document.createElement('video');
            vid.src = URL.createObjectURL(item.file);
            vid.muted = true;
            vid.style.cssText = 'width:100%;height:100%;object-fit:cover;';
            vid.onmouseenter = () => vid.play().catch(() => {});
            vid.onmouseleave = () => vid.pause();
            const ply = document.createElement('div');
            ply.style.cssText = `
                position:absolute;inset:0;display:flex;align-items:center;
                justify-content:center;pointer-events:none;
            `;
            ply.innerHTML = '<i class="fas fa-play-circle" style="font-size:28px;color:rgba(255,255,255,.7);"></i>';
            wrap.appendChild(vid);
            wrap.appendChild(ply);
        } else {
            const icons = { audio: 'fa-music', document: 'fa-file-alt' };
            const icon  = icons[item.type] || 'fa-file';
            const clr   = item.type === 'audio' ? '#f9ca24' : '#3a7bd5';
            const ico   = document.createElement('div');
            ico.style.cssText = `
                display:flex;flex-direction:column;align-items:center;
                justify-content:center;height:100%;color:${clr};padding:4px;
            `;
            ico.innerHTML = `
                <i class="fas ${icon}" style="font-size:24px;"></i>
                <span style="font-size:9px;margin-top:4px;max-width:78px;overflow:hidden;
                             text-overflow:ellipsis;white-space:nowrap;color:#aaa;">
                    ${item.file.name}
                </span>`;
            wrap.appendChild(ico);
        }

        wrap.appendChild(rm);
        container.appendChild(wrap);
    });

    if (_mediaFiles.length > 0) {
        const sendBtn = document.createElement('button');
        sendBtn.style.cssText = `
            display:block; margin:8px 4px 2px;
            background:linear-gradient(135deg,#00d2ff,#3a7bd5);
            border:none; color:#fff; border-radius:10px;
            padding:8px 18px; cursor:pointer;
            font-family:Tajawal,sans-serif; font-size:13px;
            transition:opacity .2s;
        `;
        sendBtn.innerHTML = `<i class="fas fa-paper-plane"></i> إرسال ${_mediaFiles.length} ملف`;
        sendBtn.onclick = sendMediaFiles;
        container.appendChild(sendBtn);
    }
}

// ─── إرسال الوسائط ──────────────────────────────────────────────

async function sendMediaFiles() {
    const chatId = (typeof AppState !== 'undefined' ? AppState.currentChatId : null)
                   || window._currentChatId;
    if (!chatId) {
        if (typeof showToast === 'function') showToast('⚠️ اختر محادثة أولاً', 'warning');
        return;
    }
    if (_mediaFiles.length === 0) return;
    if (_mediaUploading) return;

    _mediaUploading = true;
    if (typeof showToast === 'function')
        showToast(`⏳ جارٍ إرسال ${_mediaFiles.length} ملف...`, 'info');

    const form = new FormData();
    form.append('chat_id', chatId);
    _mediaFiles.forEach(item => form.append('files', item.file));

    try {
        const res  = await fetch('/api/messages/send-media', { method: 'POST', body: form });
        const data = await res.json();
        if (data.success) {
            if (typeof showToast === 'function')
                showToast(`✅ تم إرسال ${data.message_ids?.length || _mediaFiles.length} ملف`, 'success');
            clearMediaPreview();
            closeMediaUpload();
            // تحديث الرسائل بعد ثانية
            setTimeout(() => {
                if (typeof loadMessages === 'function' && chatId) loadMessages(chatId);
            }, 1200);
        } else {
            if (typeof showToast === 'function') showToast('❌ ' + data.message, 'error');
        }
    } catch (err) {
        if (typeof showToast === 'function') showToast('❌ فشل الإرسال: ' + err.message, 'error');
    }
    _mediaUploading = false;
}
