/**
 * copilot_mic.js
 * Dual PTT / tap-toggle microphone capture, Ctrl+Shift global hold shortcut, and /api/speech/transcribe upload.
 */
window.SearchCopilotMic = (function () {
  'use strict';

  // ── 1b. Microphone Dictation (Dual PTT / Tap-Toggle + Ctrl+Shift) ────────
  let micStream = null;
  let micRecorder = null;
  let micChunks = [];
  let micAudioCtx = null;
  let isMicRecording = false;
  let isMicAcquiring = false;
  let isMicTouchHold = false;
  let isMicLockedMode = false;
  let activeSessionLocked = false;
  let micPressStartTime = 0;
  let isMicPttKeyDown = false;
  let pttAbortThirdKey = false;
  let remoteBackendPttActive = false;
  let lastRemoteBackendPttStart = 0;
  let lastRemoteBackendPttEnd = 0;
  let lastVoiceText = '';
  let lastVoiceTime = 0;
  let micKeyboardBound = false;

  const IDLE_MIC_HINT = 'MIC: Hold or Ctrl+Shift to talk · Tap to lock';

  function shouldCopilotMicAutoSend(lockedMode) {
    try {
      if (lockedMode) {
        return localStorage.getItem('webptt_toggle_preview') !== 'true';
      }
      return localStorage.getItem('webptt_ptt_preview') !== 'true';
    } catch (_e) {
      return true;
    }
  }

  function playMicBeep(freq, duration) {
    try {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (!AudioCtx) return;
      if (!micAudioCtx) micAudioCtx = new AudioCtx();
      if (micAudioCtx.state === 'suspended') micAudioCtx.resume();
      const osc = micAudioCtx.createOscillator();
      const gain = micAudioCtx.createGain();
      osc.connect(gain);
      gain.connect(micAudioCtx.destination);
      osc.type = 'sine';
      osc.frequency.setValueAtTime(freq, micAudioCtx.currentTime);
      gain.gain.setValueAtTime(0, micAudioCtx.currentTime);
      gain.gain.linearRampToValueAtTime(0.08, micAudioCtx.currentTime + 0.01);
      gain.gain.linearRampToValueAtTime(0, micAudioCtx.currentTime + duration);
      osc.start();
      osc.stop(micAudioCtx.currentTime + duration);
    } catch (_e) { /* Ignore AudioContext blocks in headless/muted sessions */ }
  }

  function setCopilotMicStatus(text, toneClass) {
    const statusEl = document.getElementById('copilot-mic-status');
    if (!statusEl) return;
    statusEl.classList.remove('is-listening', 'is-transcribing', 'is-error');
    if (toneClass) statusEl.classList.add(toneClass);
    statusEl.textContent = text;
  }

  function setCopilotMicState(state) {
    const btn = document.getElementById('copilot-chat-mic');
    if (!btn) return;
    btn.classList.remove('preparing', 'listening', 'transcribing');
    switch (state) {
      case 'preparing':
        btn.classList.add('preparing');
        btn.innerHTML = '<i class="fas fa-spinner fa-spin" aria-hidden="true"></i>';
        btn.setAttribute('aria-label', 'Preparing microphone...');
        setCopilotMicStatus('Requesting microphone...', '');
        break;
      case 'listening':
        btn.classList.add('listening');
        btn.innerHTML = '<i class="fas fa-microphone-lines" aria-hidden="true"></i>';
        btn.setAttribute('aria-label', isMicLockedMode ? 'Recording (Locked) — tap to stop' : 'Recording in progress — release to send');
        setCopilotMicStatus(isMicLockedMode ? 'Listening (Locked) — tap mic to stop' : 'Listening... release to transcribe', 'is-listening');
        break;
      case 'transcribing':
        btn.classList.add('transcribing');
        btn.innerHTML = '<i class="fas fa-spinner fa-spin" aria-hidden="true"></i>';
        btn.setAttribute('aria-label', 'Transcribing voice...');
        setCopilotMicStatus('Transcribing voice...', 'is-transcribing');
        break;
      case 'idle':
      default:
        btn.innerHTML = '<i class="fas fa-microphone" aria-hidden="true"></i>';
        btn.setAttribute('aria-label', 'Microphone — hold for PTT, tap to toggle lock');
        setCopilotMicStatus(IDLE_MIC_HINT, '');
        break;
    }
  }

  function releaseCopilotMicStream() {
    if (micStream) {
      try {
        micStream.getTracks().forEach((t) => t.stop());
      } catch (_e) {}
      micStream = null;
    }
  }

  async function initCopilotMicStream() {
    if (micStream && micStream.active) return true;
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      console.error('[CopilotMic] Browser MediaDevices API unavailable.');
      return false;
    }
    try {
      micStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
      return true;
    } catch (err) {
      console.error('[CopilotMic] Failed to acquire microphone:', err);
      return false;
    }
  }

  async function startCopilotMic() {
    if (isMicRecording || isMicAcquiring) return;
    isMicAcquiring = true;

    // Preempt any TTS playback (local + Main Chat) and claim mic ownership across tabs
    window.SearchCopilotVoice?.stopLocalSearchAudio?.();
    if (window.HecosAudioBus) {
      window.HecosAudioBus.stopAll('net_search_mic');
      window.HecosAudioBus.claimMic('net_search_mic');
    }
    try { fetch('/api/audio/stop', { method: 'POST' }).catch(() => {}); } catch (_e) {}
    try { fetch('/api/audio/speaking/stop', { method: 'POST' }).catch(() => {}); } catch (_e) {}

    setCopilotMicState('preparing');
    const ready = await initCopilotMicStream();
    isMicAcquiring = false;

    if (!ready) {
      isMicTouchHold = false;
      isMicLockedMode = false;
      setCopilotMicState('idle');
      setCopilotMicStatus('Microphone permission denied or unavailable', 'is-error');
      setTimeout(() => {
        if (!isMicRecording) setCopilotMicState('idle');
      }, 3000);
      return;
    }

    // Abort if user released a long-hold press while waiting for permission
    if (!isMicTouchHold && !isMicLockedMode) {
      setCopilotMicState('idle');
      return;
    }

    micChunks = [];
    const mimeType = (typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported('audio/webm'))
      ? 'audio/webm'
      : '';
    const options = mimeType ? { mimeType } : {};

    try {
      micRecorder = new MediaRecorder(micStream, options);
    } catch (_e) {
      micRecorder = new MediaRecorder(micStream);
    }

    micRecorder.ondataavailable = (ev) => {
      if (ev.data && ev.data.size > 0) micChunks.push(ev.data);
    };

    activeSessionLocked = Boolean(isMicLockedMode);
    micRecorder.onstop = () => {
      const capturedChunks = micChunks.slice();
      const recMime = (micRecorder && micRecorder.mimeType) || 'audio/webm';
      const sessionWasLocked = activeSessionLocked;
      activeSessionLocked = false;
      micChunks = [];
      uploadCopilotAudio(capturedChunks, recMime, sessionWasLocked);
    };

    micRecorder.start();
    isMicRecording = true;

    playMicBeep(880, 0.1);
    setCopilotMicState('listening');
    console.log('[CopilotMic] Recording started... lockedMode=', activeSessionLocked);
  }

  function stopCopilotMic() {
    if (!isMicRecording || !micRecorder) {
      if (!isMicAcquiring) setCopilotMicState('idle');
      return;
    }
    playMicBeep(440, 0.15);
    setCopilotMicState('transcribing');
    isMicRecording = false;
    try {
      micRecorder.stop();
    } catch (e) {
      console.warn('[CopilotMic] Error stopping recorder:', e);
      setCopilotMicState('idle');
    }
  }

  function cancelCopilotMic(releaseStreamTracks = false) {
    isMicTouchHold = false;
    isMicLockedMode = false;
    if (isMicRecording && micRecorder) {
      micChunks = [];
      try {
        micRecorder.onstop = null;
        micRecorder.stop();
      } catch (_e) {}
    }
    isMicRecording = false;
    if (releaseStreamTracks) {
      releaseCopilotMicStream();
    }
    setCopilotMicState('idle');
    console.log('[CopilotMic] Recording cancelled.');
  }

  async function uploadCopilotAudio(chunks, mimeType, wasLockedMode) {
    if (!chunks || chunks.length === 0) {
      setCopilotMicState('idle');
      return;
    }

    const audioBlob = new Blob(chunks, { type: mimeType || 'audio/webm' });
    const inputEl = document.getElementById('copilot-chat-input');
    const origPlaceholder = inputEl ? inputEl.placeholder : '';

    if (inputEl) {
      inputEl.placeholder = 'Transcribing voice...';
      inputEl.disabled = true;
    }

    try {
      let uploadBlob = audioBlob;
      let uploadName = 'speech.webm';

      if (typeof window._audioBufferToWav === 'function') {
        const arrayBuffer = await audioBlob.arrayBuffer();
        if (!micAudioCtx) {
          const AudioCtx = window.AudioContext || window.webkitAudioContext;
          micAudioCtx = new AudioCtx();
        }
        const audioBuffer = await micAudioCtx.decodeAudioData(arrayBuffer);
        uploadBlob = await window._audioBufferToWav(audioBuffer);
        uploadName = 'speech.wav';
      }

      const formData = new FormData();
      formData.append('audio_file', uploadBlob, uploadName);

      const res = await fetch('/api/audio/transcribe', {
        method: 'POST',
        credentials: 'same-origin',
        body: formData
      });
      const data = await res.json();

      if (data.ok && data.text) {
        const transcribed = data.text.trim();
        if (!transcribed) return;

        const now = Date.now();
        const elapsed = now - lastVoiceTime;
        const isGenActive = Boolean(window.SearchCopilot?.isGeneratingRequest?.());
        const similarFn = window.areVoicePhrasesSimilar;
        const isDuplicate = (
          (elapsed < 8000 && similarFn && similarFn(lastVoiceText, transcribed)) ||
          (isGenActive && elapsed < 15000 && similarFn && similarFn(lastVoiceText, transcribed)) ||
          (isGenActive && elapsed < 4000)
        );
        if (isDuplicate) {
          console.warn('[CopilotMic] Duplicate dictation ignored:', transcribed);
          return;
        }
        lastVoiceText = transcribed;
        lastVoiceTime = now;

        const autoSend = shouldCopilotMicAutoSend(wasLockedMode);
        if (autoSend) {
          if (inputEl) {
            inputEl.value = transcribed;
            inputEl.disabled = false;
          }
          window.SearchCopilot?.sendMessage?.(transcribed);
        } else if (inputEl) {
          inputEl.value = (inputEl.value + ' ' + transcribed).trim();
          inputEl.disabled = false;
          inputEl.focus();
        }
      } else if (!data.ok) {
        console.error('[CopilotMic] Transcription error:', data.error);
        setCopilotMicStatus('Transcription error: ' + (data.error || 'unknown'), 'is-error');
        setTimeout(() => setCopilotMicState('idle'), 3000);
        return;
      }
    } catch (err) {
      console.error('[CopilotMic] Network/decode error:', err);
      setCopilotMicStatus('Transcription failed', 'is-error');
      setTimeout(() => setCopilotMicState('idle'), 3000);
      return;
    } finally {
      if (inputEl) {
        inputEl.placeholder = origPlaceholder;
        inputEl.disabled = false;
      }
      setCopilotMicState('idle');
    }
  }

  function bindCopilotMicButton() {
    const btn = document.getElementById('copilot-chat-mic');
    if (!btn) return;

    const startFn = (e) => {
      e.preventDefault();
      if (micAudioCtx && micAudioCtx.state === 'suspended') {
        micAudioCtx.resume().catch(() => {});
      }

      if (isMicRecording) {
        if (isMicLockedMode) {
          isMicLockedMode = false;
          stopCopilotMic();
        }
        return;
      }
      micPressStartTime = Date.now();
      isMicTouchHold = true;
      isMicLockedMode = false;
      startCopilotMic();
    };

    const stopFn = (e) => {
      e.preventDefault();
      if (!isMicTouchHold) return;
      isMicTouchHold = false;

      const elapsed = Date.now() - micPressStartTime;
      const isTapRelease = (e.type === 'mouseup' || e.type === 'touchend');

      if (isTapRelease && elapsed < 400 && !isMicLockedMode) {
        isMicLockedMode = true;
        activeSessionLocked = true;
        if (isMicRecording) {
          setCopilotMicState('listening');
        }
        return;
      }

      if (!isMicRecording) return;

      isMicLockedMode = false;
      stopCopilotMic();
    };

    btn.addEventListener('mousedown', startFn);
    window.addEventListener('mouseup', stopFn);
    btn.addEventListener('touchstart', startFn, { passive: false });
    btn.addEventListener('touchend', stopFn, { passive: false });
    btn.addEventListener('touchcancel', stopFn, { passive: false });
  }

  function bindCopilotMicKeyboard() {
    if (micKeyboardBound) return;
    micKeyboardBound = true;

    const isCtrlOrShift = (e) => (
      e.key === 'Control' || e.key === 'Shift' ||
      e.code === 'ControlLeft' || e.code === 'ControlRight' ||
      e.code === 'ShiftLeft' || e.code === 'ShiftRight'
    );

    const canCaptureKeyboardPtt = () => {
      if (document.hidden) return false;
      if (document.querySelector('.search-modal-backdrop.open')) return false;
      const sidebar = document.getElementById('search-copilot');
      if (sidebar && sidebar.offsetParent === null) return false;
      return true;
    };

    document.addEventListener('keydown', (e) => {
      if (isMicPttKeyDown && !isCtrlOrShift(e)) {
        pttAbortThirdKey = true;
        if (isMicRecording) {
          cancelCopilotMic(false);
        }
        return;
      }

      const isCtrlShift = (e.ctrlKey || e.metaKey) && e.shiftKey;
      if (isCtrlShift && isCtrlOrShift(e)) {
        if (isMicPttKeyDown) return;
        if (!canCaptureKeyboardPtt()) return;

        // Avoid conflicting with host desktop hardware PTT if active in Main Chat
        if (
          window.isBackendPTTActive ||
          remoteBackendPttActive ||
          (Date.now() - lastRemoteBackendPttStart) < 1500
        ) {
          isMicPttKeyDown = true;
          console.log('[CopilotMic] Backend hardware PTT active; skipping browser capture.');
          return;
        }

        isMicPttKeyDown = true;
        pttAbortThirdKey = false;
        isMicTouchHold = true;
        isMicLockedMode = false;
        micPressStartTime = Date.now();
        startCopilotMic();
      }
    });

    document.addEventListener('keyup', (e) => {
      if (isMicPttKeyDown && isCtrlOrShift(e)) {
        isMicPttKeyDown = false;
        isMicTouchHold = false;

        if (pttAbortThirdKey) {
          pttAbortThirdKey = false;
          return;
        }

        if (
          window.isBackendPTTActive ||
          remoteBackendPttActive ||
          (Date.now() - lastRemoteBackendPttEnd) < 2000
        ) {
          if (isMicRecording) cancelCopilotMic(false);
          return;
        }

        if (isMicRecording) {
          isMicLockedMode = false;
          stopCopilotMic();
        }
      }
    });

    window.addEventListener('blur', () => {
      if (isMicPttKeyDown) {
        isMicPttKeyDown = false;
        isMicTouchHold = false;
        if (isMicRecording) {
          isMicLockedMode = false;
          stopCopilotMic();
        }
      }
    });

    document.addEventListener('visibilitychange', () => {
      if (document.hidden && isMicPttKeyDown) {
        isMicPttKeyDown = false;
        isMicTouchHold = false;
        if (isMicRecording) {
          isMicLockedMode = false;
          stopCopilotMic();
        }
      }
    });
  }

  if (window.HecosAudioBus) {
    if (typeof window.HecosAudioBus.onMicClaim === 'function') {
      window.HecosAudioBus.onMicClaim((msg) => {
        if (msg && msg.owner !== 'net_search_mic') {
          console.log(`[CopilotMic] Remote tab (${msg.owner}) claimed mic — cancelling local capture.`);
          cancelCopilotMic(true);
        }
      });
    }
    if (typeof window.HecosAudioBus.onBackendPtt === 'function') {
      window.HecosAudioBus.onBackendPtt((msg) => {
        if (!msg) return;
        remoteBackendPttActive = Boolean(msg.active);
        if (msg.active) {
          lastRemoteBackendPttStart = Date.now();
          if (isMicRecording) cancelCopilotMic(true);
        } else {
          lastRemoteBackendPttEnd = Date.now();
        }
      });
    }
  }

  return {
    bindCopilotMicButton,
    bindCopilotMicKeyboard,
    setCopilotMicState,
    cancelCopilotMic,
    releaseCopilotMicStream
  };
})();
