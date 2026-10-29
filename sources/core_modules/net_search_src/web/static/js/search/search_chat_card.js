/**
 * search_chat_card.js
 * Injected into Hecos Chat UI to transform [[HSEARCH:<id>]] tokens
 * into beautiful, interactive, collapsible Deep Search cards.
 */
(function() {
  const HSEARCH_REGEX = /\[\[HSEARCH:([a-zA-Z0-9_-]+)\]\]/g;

  function renderSearchCard(sessionId) {
    const cardId = `hsearch-card-${sessionId}`;
    return `
      <div class="hsearch-chat-card" id="${cardId}" data-session-id="${sessionId}">
        <div class="hsearch-card-header">
          <div class="hsearch-card-title">
            <span class="hsearch-icon"><i class="fas fa-satellite-dish"></i></span>
            <span>Hecos Net Search</span>
            <span class="hsearch-badge-live" id="${cardId}-badge">Loading...</span>
          </div>
          <div class="hsearch-card-actions">
            <button class="hsearch-btn-toggle" onclick="window.toggleHSearchCard('${sessionId}')" title="Toggle sources">
              <i class="fas fa-chevron-down" id="${cardId}-icon"></i>
            </button>
            <a href="/search?session=${sessionId}" target="_blank" class="hsearch-btn-open" title="Open in Net Search">
              <i class="fas fa-external-link-alt"></i> Open
            </a>
          </div>
        </div>
        <div class="hsearch-card-content" id="${cardId}-content" style="display:none;">
          <div class="hsearch-loading"><i class="fas fa-spinner fa-spin"></i> Loading search details...</div>
        </div>
      </div>
    `;
  }

  window.toggleHSearchCard = async function(sessionId) {
    const content = document.getElementById(`hsearch-card-${sessionId}-content`);
    const icon = document.getElementById(`hsearch-card-${sessionId}-icon`);
    if (!content) return;

    if (content.style.display === 'none') {
      content.style.display = 'block';
      if (icon) icon.className = 'fas fa-chevron-up';

      // Load session details from API if not yet loaded
      if (content.querySelector('.hsearch-loading')) {
        try {
          const res = await fetch(`/api/hsearch/sessions/${sessionId}`);
          const data = await res.json();
          if (data.ok && data.session) {
            const s = data.session;
            const badge = document.getElementById(`hsearch-card-${sessionId}-badge`);
            if (badge) badge.innerText = `${s.total_results} sources (${s.duration_ms}ms)`;

            if (s.results && s.results.length > 0) {
              content.innerHTML = s.results.map((r, i) => `
                <div class="hsearch-item-row">
                  <span class="hsearch-num">[${i + 1}]</span>
                  <div class="hsearch-item-text">
                    <a href="${r.url}" target="_blank" class="hsearch-link">${escapeHtml(r.title)}</a>
                    <div class="hsearch-sub">
                      <span class="hsearch-eng">${escapeHtml(r.engine)}</span>
                      <span class="hsearch-net">${r.network === 'tor' ? '🧅 Tor' : '🌐 Clear'}</span>
                      <span class="hsearch-url">${escapeHtml(r.url)}</span>
                    </div>
                  </div>
                </div>
              `).join('');
            } else {
              content.innerHTML = '<div style="padding:10px; font-size:12px; color:#888;">No links saved for this session.</div>';
            }
          }
        } catch (e) {
          content.innerHTML = `<div style="padding:10px; font-size:12px; color:#f87171;">Loading error: ${e.message}</div>`;
        }
      }
    } else {
      content.style.display = 'none';
      if (icon) icon.className = 'fas fa-chevron-down';
    }
  };

  function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  // Scan chat messages and inject widgets
  function processChatMessages() {
    const bubbles = document.querySelectorAll('.message-content, .msg-text, .bubble-content');
    bubbles.forEach(bubble => {
      if (bubble.innerHTML.includes('[[HSEARCH:')) {
        bubble.innerHTML = bubble.innerHTML.replace(HSEARCH_REGEX, (match, sessionId) => {
          return renderSearchCard(sessionId);
        });
      }
    });
  }

  // Inject styles for the chat card
  const style = document.createElement('style');
  style.textContent = `
    .hsearch-chat-card {
      margin: 12px 0;
      background: rgba(15, 23, 42, 0.7);
      border: 1px solid rgba(6, 182, 212, 0.3);
      border-radius: 12px;
      overflow: hidden;
      font-family: inherit;
      box-shadow: 0 4px 16px rgba(0,0,0,0.3);
    }
    .hsearch-card-header {
      padding: 10px 14px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      background: rgba(6, 182, 212, 0.08);
      border-bottom: 1px solid rgba(255, 255, 255, 0.05);
    }
    .hsearch-card-title {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 13px;
      font-weight: 600;
      color: #38bdf8;
    }
    .hsearch-icon {
      color: #06b6d4;
    }
    .hsearch-badge-live {
      font-size: 10px;
      padding: 2px 6px;
      border-radius: 10px;
      background: rgba(6, 182, 212, 0.2);
      color: #67e8f9;
      font-weight: normal;
    }
    .hsearch-card-actions {
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .hsearch-btn-toggle, .hsearch-btn-open {
      padding: 4px 8px;
      border-radius: 6px;
      background: rgba(255, 255, 255, 0.06);
      border: 1px solid rgba(255, 255, 255, 0.1);
      color: #cbd5e1;
      font-size: 11px;
      cursor: pointer;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }
    .hsearch-btn-toggle:hover, .hsearch-btn-open:hover {
      background: rgba(255, 255, 255, 0.12);
      color: #fff;
    }
    .hsearch-card-content {
      padding: 12px 14px;
      max-height: 240px;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 8px;
      background: rgba(10, 14, 24, 0.5);
    }
    .hsearch-item-row {
      display: flex;
      align-items: flex-start;
      gap: 8px;
      font-size: 12px;
    }
    .hsearch-num {
      color: #06b6d4;
      font-weight: bold;
    }
    .hsearch-link {
      color: #7dd3fc;
      text-decoration: none;
      font-weight: 500;
    }
    .hsearch-link:hover {
      text-decoration: underline;
    }
    .hsearch-sub {
      display: flex;
      gap: 8px;
      font-size: 10px;
      color: #94a3b8;
      margin-top: 2px;
    }
    .hsearch-net {
      color: #c084fc;
    }
  `;
  document.head.appendChild(style);

  // Run on load and observe DOM for new incoming chat messages
  document.addEventListener('DOMContentLoaded', processChatMessages);
  const observer = new MutationObserver(processChatMessages);
  observer.observe(document.body, { childList: true, subtree: true });
})();
