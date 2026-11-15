/**
 * stream_player_dock.js
 * Floating dockable In-Page Live Stream Player for Hecos NetSearch Stream Hunter.
 * Supports HLS (.m3u8 via hls.js + anti-CORS proxy fallback), Icecast/Radio (<audio>),
 * MJPEG Webcams (<img> stream), and 1-click handoff to VLC Desktop.
 */
(function () {
  let hlsInstance = null;
  let currentStream = null;
  let hlsScriptPromise = null;
  let desiredVolume = 85;
  let desiredMuted = false;

  function _getActiveMediaEl() {
    const stage = document.getElementById('sh-dock-stage');
    return stage ? stage.querySelector('video, audio') : null;
  }

  function _applyAudioSettingsToMedia(media) {
    if (!media) return;
    try {
      media.volume = Math.max(0, Math.min(1, desiredVolume / 100));
      media.muted = Boolean(desiredMuted);
    } catch (_e) {}
  }

  function pauseToggle() {
    const media = _getActiveMediaEl();
    if (!media) return false;
    if (media.paused) {
      media.play().catch(() => {});
      return false; // not paused anymore
    }
    media.pause();
    return true;
  }

  function setVolume(vol) {
    const clamped = Math.max(0, Math.min(100, parseInt(vol, 10) || 0));
    desiredVolume = clamped;
    if (clamped > 0) desiredMuted = false;
    const media = _getActiveMediaEl();
    _applyAudioSettingsToMedia(media);
    return { volume: desiredVolume, muted: desiredMuted };
  }

  function toggleMute(explicitMuted) {
    desiredMuted = (typeof explicitMuted === 'boolean') ? explicitMuted : !desiredMuted;
    const media = _getActiveMediaEl();
    _applyAudioSettingsToMedia(media);
    return desiredMuted;
  }

  function getPlaybackState() {
    const media = _getActiveMediaEl();
    return {
      isPlaying: Boolean(currentStream),
      currentStream,
      paused: media ? Boolean(media.paused) : false,
      volume: desiredVolume,
      muted: desiredMuted,
    };
  }

  function ensureHlsJs() {
    if (window.Hls) return Promise.resolve(window.Hls);
    if (hlsScriptPromise) return hlsScriptPromise;
    hlsScriptPromise = new Promise((resolve) => {
      const s = document.createElement('script');
      s.src = 'https://cdn.jsdelivr.net/npm/hls.js@1.5.15/dist/hls.min.js';
      s.async = true;
      s.onload = () => resolve(window.Hls || null);
      s.onerror = () => resolve(null);
      document.head.appendChild(s);
    });
    return hlsScriptPromise;
  }

  function ensureDockDom() {
    let dock = document.getElementById('sh-player-dock');
    if (dock) return dock;

    dock = document.createElement('div');
    dock.id = 'sh-player-dock';
    dock.className = 'sh-player-dock';
    dock.innerHTML = `
      <div class="sh-player-header">
        <span class="sh-pill sh-pill-live" id="sh-dock-proto-pill">LIVE</span>
        <div class="sh-player-title" id="sh-dock-title">Stream Player</div>
        <div class="sh-player-controls-top">
          <button type="button" class="sh-btn" id="sh-dock-min-btn" title="Minimize / Expand Player" style="padding:3px 7px;">
            <i class="fas fa-window-minimize"></i>
          </button>
          <button type="button" class="sh-btn" id="sh-dock-close-btn" title="Stop & Close Player" style="padding:3px 7px;">
            <i class="fas fa-times"></i>
          </button>
        </div>
      </div>
      <div class="sh-player-stage" id="sh-dock-stage"></div>
      <div class="sh-player-footer">
        <div style="display:flex; align-items:center; gap:6px;">
          <button type="button" class="sh-btn is-vlc" id="sh-dock-vlc-btn" title="Open this stream in VLC Desktop">
            <i class="fas fa-play-circle"></i> Open in VLC
          </button>
          <button type="button" class="sh-btn" id="sh-dock-proxy-btn" title="Reload stream through Hecos Anti-CORS Proxy">
            <i class="fas fa-shield-halved"></i> Proxy Mode
          </button>
        </div>
        <button type="button" class="sh-btn" id="sh-dock-copy-btn" title="Copy direct stream URL">
          <i class="fas fa-copy"></i> Copy URL
        </button>
      </div>
    `;
    document.body.appendChild(dock);

    document.getElementById('sh-dock-min-btn').addEventListener('click', () => {
      dock.classList.toggle('is-minimized');
    });
    document.getElementById('sh-dock-close-btn').addEventListener('click', () => {
      stopAndClose();
    });
    document.getElementById('sh-dock-vlc-btn').addEventListener('click', (ev) => {
      if (currentStream && window.StreamHunterUI) {
        window.StreamHunterUI.openInVlc(currentStream.stream_url, currentStream.title, ev.currentTarget);
      }
    });
    document.getElementById('sh-dock-proxy-btn').addEventListener('click', () => {
      if (currentStream) {
        playStream(currentStream, true);
      }
    });
    document.getElementById('sh-dock-copy-btn').addEventListener('click', () => {
      if (currentStream && currentStream.stream_url) {
        navigator.clipboard.writeText(currentStream.stream_url).catch(() => {});
      }
    });

    return dock;
  }

  function cleanupMedia() {
    if (hlsInstance) {
      try { hlsInstance.destroy(); } catch (_e) {}
      hlsInstance = null;
    }
    const stage = document.getElementById('sh-dock-stage');
    if (stage) {
      const mediaEls = stage.querySelectorAll('video, audio');
      mediaEls.forEach(el => {
        try {
          el.pause();
          el.removeAttribute('src');
          el.load();
        } catch (_e) {}
      });
      stage.innerHTML = '';
    }
  }

  function stopAndClose() {
    cleanupMedia();
    currentStream = null;
    const dock = document.getElementById('sh-player-dock');
    if (dock) {
      dock.classList.remove('is-open', 'is-minimized');
    }
    document.querySelectorAll('.sh-card.is-playing').forEach(el => el.classList.remove('is-playing'));
  }

  async function playStream(streamObj, forceProxy = false) {
    if (!streamObj || !streamObj.stream_url) return;
    currentStream = streamObj;

    const dock = ensureDockDom();
    dock.classList.add('is-open');
    dock.classList.remove('is-minimized');

    cleanupMedia();

    const titleEl = document.getElementById('sh-dock-title');
    const protoEl = document.getElementById('sh-dock-proto-pill');
    const stage = document.getElementById('sh-dock-stage');

    const proto = (streamObj.protocol || 'HLS').toUpperCase();
    const cat = (streamObj.category || 'tv').toLowerCase();
    const rawUrl = streamObj.stream_url;
    const proxiedUrl = `/api/hsearch/streams/proxy?url=${encodeURIComponent(rawUrl)}`;
    const targetUrl = forceProxy ? proxiedUrl : rawUrl;

    if (titleEl) titleEl.textContent = streamObj.title || rawUrl;
    if (protoEl) protoEl.textContent = forceProxy ? `${proto} • PROXY` : proto;

    // Highlight active card
    document.querySelectorAll('.sh-card').forEach(c => {
      c.classList.toggle('is-playing', c.dataset.streamUrl === rawUrl);
    });

    // RTSP / RTMP / MMS -> Direct VLC handoff notice
    if (proto === 'RTSP' || proto === 'RTMP' || proto === 'MMS' || rawUrl.startsWith('rtsp://')) {
      stage.className = 'sh-player-stage is-audio-only';
      stage.innerHTML = `
        <div style="text-align:center; color:#cbd5e1; font-size:12px; padding:10px;">
          <div style="margin-bottom:8px; color:#fdba74; font-weight:700;">
            <i class="fas fa-satellite-dish"></i> Native ${proto} Stream Detected
          </div>
          <div style="color:#94a3b8; margin-bottom:10px;">
            Browsers do not decode raw ${proto} sockets directly. Launching in VLC Desktop is recommended.
          </div>
          <button type="button" class="sh-btn is-vlc" id="sh-dock-rtsp-vlc-btn">
            <i class="fas fa-external-link-alt"></i> Launch Now in VLC Desktop
          </button>
        </div>
      `;
      const rtspBtn = document.getElementById('sh-dock-rtsp-vlc-btn');
      if (rtspBtn) {
        rtspBtn.addEventListener('click', () => {
          if (window.StreamHunterUI) {
            window.StreamHunterUI.openInVlc(rawUrl, streamObj.title || '', rtspBtn);
          }
        });
      }
      return;
    }

    // MJPEG Camera stream
    if (proto === 'MJPEG' || rawUrl.toLowerCase().includes('mjpg')) {
      stage.className = 'sh-player-stage';
      const img = document.createElement('img');
      img.className = 'sh-mjpeg-view';
      img.src = proxiedUrl;
      img.alt = streamObj.title || 'MJPEG Live Cam';
      stage.appendChild(img);
      return;
    }

    // Radio / Icecast / Audio stream (unless it is an .m3u8 stream)
    const isHls = proto === 'HLS' || rawUrl.toLowerCase().includes('.m3u8');
    if ((cat === 'radio' || proto === 'ICECAST' || proto === 'PLS') && !isHls) {
      stage.className = 'sh-player-stage is-audio-only';
      stage.innerHTML = `
        <div style="display:flex; align-items:center; gap:10px; width:100%; color:#e2e8f0; font-size:12px;">
          <i class="fas fa-broadcast-tower fa-spin" style="color:#22d3ee; font-size:18px;"></i>
          <div style="flex:1; min-width:0;">
            <div style="font-weight:700; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${streamObj.title || 'Live Radio'}</div>
            <div style="font-size:11px; color:#94a3b8;">${streamObj.country || 'INT'} • ${streamObj.codec || 'MP3'} ${streamObj.bitrate ? streamObj.bitrate + ' kbps' : ''}</div>
          </div>
        </div>
      `;
      const audio = document.createElement('audio');
      audio.controls = true;
      audio.autoplay = true;
      _applyAudioSettingsToMedia(audio);
      audio.src = targetUrl;
      audio.onerror = () => {
        console.warn('[StreamPlayerDock] Direct audio playback error, forceProxy=' + forceProxy, rawUrl);
        if (!forceProxy) {
          playStream(streamObj, true);
        }
      };
      stage.appendChild(audio);
      return;
    }

    // Video / HLS (.m3u8) stream
    stage.className = 'sh-player-stage';
    const video = document.createElement('video');
    video.controls = true;
    video.autoplay = true;
    video.playsInline = true;
    _applyAudioSettingsToMedia(video);
    stage.appendChild(video);

    if (isHls) {
      const HlsLib = await ensureHlsJs();
      if (HlsLib && HlsLib.isSupported()) {
        hlsInstance = new HlsLib({
          enableWorker: true,
          lowLatencyMode: true,
        });
        hlsInstance.loadSource(targetUrl);
        hlsInstance.attachMedia(video);
        hlsInstance.on(HlsLib.Events.MANIFEST_PARSED, () => {
          console.info('[StreamPlayerDock] HLS manifest parsed:', streamObj.title || rawUrl, 'proxy=' + forceProxy);
          video.play().catch((err) => console.debug('[StreamPlayerDock] HLS autoplay blocked/deferred:', err && err.message));
        });
        hlsInstance.on(HlsLib.Events.ERROR, (_ev, data) => {
          if (data && data.fatal) {
            console.warn('[StreamPlayerDock] Fatal HLS error:', data.type, data.details, 'forceProxy=' + forceProxy, rawUrl);
            if (!forceProxy) {
              // Automatically retry through anti-CORS proxy on network/CORS error
              playStream(streamObj, true);
            }
          }
        });
        return;
      }
    }

    // Native HLS (Safari) or direct MP4/WebM stream
    video.src = targetUrl;
    video.onerror = () => {
      console.warn('[StreamPlayerDock] Direct video playback error, forceProxy=' + forceProxy, rawUrl);
      if (!forceProxy) {
        playStream(streamObj, true);
      }
    };
    video.play().catch(() => {});
  }

  window.StreamPlayerDock = {
    playStream,
    stopAndClose,
    pauseToggle,
    setVolume,
    getVolume: () => desiredVolume,
    toggleMute,
    getPlaybackState,
  };
})();
