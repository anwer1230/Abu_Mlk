// static/js/voice_call.js — مركز سرعة إنجاز
// المرحلة 14: المكالمات الصوتية المشفرة (WebRTC + Socket.IO)

class VoiceCallManager {
    constructor() {
        this.pc           = null;   // RTCPeerConnection
        this.localStream  = null;
        this.remoteStream = null;
        this.isMuted      = false;
        this.isSpeaker    = false;
        this.isConnected  = false;
        this.callDuration = 0;
        this._timer       = null;
        this._remoteAudio = null;

        this.iceServers = {
            iceServers: [
                { urls: 'stun:stun.l.google.com:19302' },
                { urls: 'stun:stun1.l.google.com:19302' },
                { urls: 'stun:stun2.l.google.com:19302' },
            ]
        };

        this._socket = null;
        this._initSocket();
    }

    // ─── تهيئة Socket.IO ─────────────────────────────────────────
    _initSocket() {
        try {
            this._socket = io();
            this._socket.on('incoming_call',  d => this._onIncoming(d));
            this._socket.on('call_answered',  d => this._onAnswered(d));
            this._socket.on('call_offer',     d => this._onOffer(d));
            this._socket.on('call_answer',    d => this._onAnswer(d));
            this._socket.on('call_ice',       d => this._onIce(d));
            this._socket.on('call_ended',     ()=> this._onEnded());
            this._socket.on('call_rejected',  ()=> this._onRejected());
            this._socket.on('call_busy',      ()=> this._onBusy());
        } catch (e) {
            console.warn('VoiceCall: Socket.IO غير متاح:', e.message);
        }
    }

    // ─── بدء مكالمة صادرة ────────────────────────────────────────
    async startCall(targetUserId, targetName) {
        try {
            this.localStream = await navigator.mediaDevices.getUserMedia({
                audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true }
            });
            this._createPC(targetUserId);
            this.localStream.getTracks().forEach(t => this.pc.addTrack(t, this.localStream));

            const offer = await this.pc.createOffer();
            await this.pc.setLocalDescription(offer);

            this._socket?.emit('call_offer', {
                to_user_id:  targetUserId,
                from_user_id: this._myId(),
                from_name:   this._myName(),
                offer
            });

            this._showStatus('📞 جاري الاتصال...');
            this._startTimer();
        } catch (e) {
            console.error('VoiceCall: فشل بدء المكالمة:', e);
            this._showStatus('❌ تعذّر الوصول للميكروفون');
        }
    }

    // ─── الرد على مكالمة واردة ───────────────────────────────────
    async answerCall(callerId) {
        try {
            this.localStream = await navigator.mediaDevices.getUserMedia({
                audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true }
            });
            this._createPC(callerId);
            this.localStream.getTracks().forEach(t => this.pc.addTrack(t, this.localStream));
            this._socket?.emit('call_answer', { to_user_id: callerId });
        } catch (e) {
            console.error('VoiceCall: فشل الرد:', e);
        }
    }

    // ─── إنشاء PeerConnection ────────────────────────────────────
    _createPC(remoteUserId) {
        this.pc = new RTCPeerConnection(this.iceServers);

        this.pc.ontrack = (e) => {
            this.remoteStream = e.streams[0];
            this._playRemote();
        };

        this.pc.onicecandidate = (e) => {
            if (e.candidate) {
                this._socket?.emit('call_ice', {
                    to_user_id: remoteUserId,
                    candidate:  e.candidate
                });
            }
        };

        this.pc.onconnectionstatechange = () => {
            const s = this.pc?.connectionState;
            if (s === 'connected')    { this.isConnected = true;  this._showStatus('✅ متصل — مشفّر'); }
            if (s === 'disconnected') this._showStatus('⚠️ انقطع الاتصال...');
            if (s === 'failed')       this._showStatus('❌ فشل الاتصال');
        };
    }

    // ─── معالجات الإشارات ────────────────────────────────────────
    _onIncoming(data) {
        if (confirm(`📞 مكالمة واردة من ${data.from_name || 'مستخدم'}\nالرد؟`)) {
            this.answerCall(data.from_user_id);
        } else {
            this._socket?.emit('call_reject', { to_user_id: data.from_user_id });
        }
    }

    _onAnswered(data) {
        this._showStatus('📲 تم الرد — جاري الاتصال...');
    }

    async _onOffer(data) {
        if (!this.pc) return;
        await this.pc.setRemoteDescription(new RTCSessionDescription(data.offer));
        const answer = await this.pc.createAnswer();
        await this.pc.setLocalDescription(answer);
        this._socket?.emit('call_answer', { to_user_id: data.from_user_id, answer });
        this._startTimer();
    }

    async _onAnswer(data) {
        if (!this.pc || !data.answer) return;
        await this.pc.setRemoteDescription(new RTCSessionDescription(data.answer));
    }

    async _onIce(data) {
        if (!this.pc || !data.candidate) return;
        try { await this.pc.addIceCandidate(new RTCIceCandidate(data.candidate)); } catch (_) {}
    }

    _onEnded()   { this._showStatus('📵 انتهت المكالمة'); setTimeout(() => this.hangup(), 1500); }
    _onRejected(){ this._showStatus('❌ تم رفض المكالمة'); setTimeout(() => history.back(), 2000); }
    _onBusy()    { this._showStatus('📵 المستخدم مشغول'); setTimeout(() => history.back(), 2000); }

    // ─── تشغيل الصوت البعيد ──────────────────────────────────────
    _playRemote() {
        if (this._remoteAudio) this._remoteAudio.remove();
        this._remoteAudio = document.createElement('audio');
        this._remoteAudio.srcObject = this.remoteStream;
        this._remoteAudio.autoplay  = true;
        this._remoteAudio.style.display = 'none';
        document.body.appendChild(this._remoteAudio);
    }

    // ─── كتم / مكبر ──────────────────────────────────────────────
    toggleMute() {
        this.isMuted = !this.isMuted;
        this.localStream?.getAudioTracks().forEach(t => t.enabled = !this.isMuted);
        const btn = document.getElementById('muteBtn');
        if (btn) {
            btn.classList.toggle('active', this.isMuted);
            btn.innerHTML = this.isMuted
                ? '<i class="fas fa-microphone-slash"></i>'
                : '<i class="fas fa-microphone"></i>';
        }
    }

    toggleSpeaker() {
        this.isSpeaker = !this.isSpeaker;
        const btn = document.getElementById('speakerBtn');
        if (btn) btn.classList.toggle('active', this.isSpeaker);
    }

    // ─── إنهاء المكالمة ──────────────────────────────────────────
    hangup() {
        this._socket?.emit('call_end', { to_user_id: window.TARGET_USER_ID });
        this._cleanup();
        history.back();
    }

    _cleanup() {
        if (this._timer) clearInterval(this._timer);
        this.pc?.close();
        this.pc = null;
        this.localStream?.getTracks().forEach(t => t.stop());
        this.localStream = null;
        this.remoteStream?.getTracks().forEach(t => t.stop());
        this.remoteStream = null;
        this._remoteAudio?.remove();
        this.isConnected  = false;
        this.callDuration = 0;
    }

    // ─── مؤقت ───────────────────────────────────────────────────
    _startTimer() {
        this.callDuration = 0;
        this._timer = setInterval(() => {
            this.callDuration++;
            const m = String(Math.floor(this.callDuration / 60)).padStart(2, '0');
            const s = String(this.callDuration % 60).padStart(2, '0');
            const el = document.getElementById('callTimer');
            if (el) el.textContent = `${m}:${s}`;
        }, 1000);
    }

    // ─── عرض حالة ────────────────────────────────────────────────
    _showStatus(msg) {
        const el = document.getElementById('callStatus');
        if (el) el.textContent = msg;
    }

    _myId()   { return window._userId   || localStorage.getItem('user_id')   || ''; }
    _myName() { return window._userName || localStorage.getItem('user_name') || 'مستخدم'; }
}

// ─── تهيئة عالمي ─────────────────────────────────────────────────
const callManager = new VoiceCallManager();

// دوال HTML
function endCall()       { callManager.hangup(); }
function toggleMute()    { callManager.toggleMute(); }
function toggleSpeaker() { callManager.toggleSpeaker(); }

// بدء مكالمة تلقائياً عند تحميل الصفحة إذا كان هناك مستهدف
document.addEventListener('DOMContentLoaded', () => {
    if (typeof TARGET_USER_ID !== 'undefined' && TARGET_USER_ID) {
        callManager.startCall(TARGET_USER_ID, typeof TARGET_NAME !== 'undefined' ? TARGET_NAME : 'مستخدم');
    }
});
