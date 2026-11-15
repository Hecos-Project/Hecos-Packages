/**
 * copilot_markdown.js
 * Thinking-block parser, safe link sanitizer, markdown renderer, and assistant bubble updater for Net Search Copilot.
 */
window.SearchCopilotMarkdown = (function () {
  'use strict';

  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  /**
   * Separate model reasoning (<think>...</think>, bare </think>, or unclosed
   * streaming <think>...) from the visible assistant reply.
   */
  function splitThinkingContent(rawText) {
    if (!rawText) return { thinking: '', body: '', isThinkingStreaming: false };
    let working = String(rawText);
    const thoughts = [];
    let isThinkingStreaming = false;

    // 1. Extract complete <think>...</think> blocks
    working = working.replace(/<think>([\s\S]*?)<\/think>/gi, (_m, inner) => {
      const cleaned = (inner || '').trim();
      if (cleaned) thoughts.push(cleaned);
      return '';
    });

    // 2. Handle bare closing </think> (some streaming adapters omit opening tag)
    const bareCloseIdx = working.search(/<\/think>/i);
    if (bareCloseIdx !== -1 && !/<think>/i.test(working.slice(0, bareCloseIdx))) {
      const preThought = working.slice(0, bareCloseIdx).replace(/^\s*<\/?think>/i, '').trim();
      if (preThought) thoughts.push(preThought);
      working = working.slice(bareCloseIdx).replace(/^<\/think>\s*/i, '');
    }

    // 3. Handle unclosed <think>... while actively streaming
    const openIdx = working.search(/<think>/i);
    if (openIdx !== -1) {
      const activeThought = working.slice(openIdx).replace(/^<think>/i, '').trim();
      if (activeThought) thoughts.push(activeThought);
      working = working.slice(0, openIdx);
      isThinkingStreaming = true;
    }

    return {
      thinking: thoughts.join('\n\n').trim(),
      body: working.trim(),
      isThinkingStreaming
    };
  }

  function unescapeBasicEntities(str) {
    if (!str) return '';
    return String(str)
      .replace(/&amp;/g, '&')
      .replace(/&#039;/g, "'")
      .replace(/&#39;/g, "'")
      .replace(/&quot;/g, '"')
      .replace(/&lt;/g, '<')
      .replace(/&gt;/g, '>');
  }

  function resolveSafeHref(rawUrl) {
    const clean = unescapeBasicEntities(rawUrl).trim();
    if (!/^https?:\/\/\S+$/i.test(clean)) return null;
    try {
      const parsed = new URL(clean);
      if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') return null;
      const isOnion = parsed.hostname.toLowerCase().endsWith('.onion');
      const finalHref = isOnion ? `/search/viewer?url=${encodeURIComponent(clean)}` : clean;
      return {
        href: escapeHtml(finalHref),
        raw: clean,
        isOnion
      };
    } catch (_e) {
      return null;
    }
  }

  function buildCopilotLinkHtml(labelHtml, rawUrl, extraClass, titleText) {
    const resolved = resolveSafeHref(rawUrl);
    if (!resolved) return null;
    const cls = extraClass ? `copilot-link ${extraClass}` : 'copilot-link';
    const tip = titleText || (resolved.isOnion ? `Open .onion in Tor Live Viewer: ${resolved.raw}` : resolved.raw);
    return `<a href="${resolved.href}" class="${cls}" target="_blank" rel="noopener noreferrer" title="${escapeHtml(tip)}">${labelHtml}</a>`;
  }

  function trimTrailingUrlPunct(urlStr) {
    let url = urlStr;
    let suffix = '';
    while (url.length > 0) {
      const last = url.slice(-1);
      if (last === ')') {
        const openCount = (url.match(/\(/g) || []).length;
        const closeCount = (url.match(/\)/g) || []).length;
        if (closeCount > openCount) {
          url = url.slice(0, -1);
          suffix = ')' + suffix;
          continue;
        }
        break;
      }
      if ('.,;:!?]*\'"'.includes(last)) {
        url = url.slice(0, -1);
        suffix = last + suffix;
        continue;
      }
      break;
    }
    return { url, suffix };
  }

  function formatInlineStyles(str) {
    return str
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.*?)\*/g, '<em>$1</em>');
  }

  function formatMarkdown(text, citeResults) {
    if (!text) return '';
    const tokens = [];
    const stash = (htmlStr) => {
      const idx = tokens.push(htmlStr) - 1;
      return `\uE000CPTOK${idx}\uE001`;
    };

    const resolvedResults = Array.isArray(citeResults)
      ? citeResults
      : (window.SearchState && Array.isArray(window.SearchState.results) ? window.SearchState.results : []);

    let html = escapeHtml(text);

    // 1. Protect inline code `code` before any link or style parsing
    html = html.replace(/`([^`]+)`/g, (_m, code) => stash(`<code>${code}</code>`));

    // 2. Markdown links [label](https://...)
    const mdLinkRe = /\[([^\]]+)\]\((?:&lt;)?(https?:\/\/(?:(?!&(?:lt|gt|quot|#0?39);)[^\s()<>]|(?:\((?:(?!&(?:lt|gt|quot|#0?39);)[^\s()<>])*\)))+)(?:&gt;)?\)/gi;
    html = html.replace(mdLinkRe, (fullMatch, label, rawUrl) => {
      const styledLabel = formatInlineStyles(label);
      const linkHtml = buildCopilotLinkHtml(styledLabel, rawUrl, '', '');
      return linkHtml ? stash(linkHtml) : fullMatch;
    });

    // 3. Bare URLs https://... or http://...
    const bareUrlRe = /https?:\/\/(?:(?!&(?:lt|gt|quot|#0?39);)[^\s<>\uE000\uE001])+/gi;
    html = html.replace(bareUrlRe, (rawMatch) => {
      const { url, suffix } = trimTrailingUrlPunct(rawMatch);
      const cleanRaw = unescapeBasicEntities(url);
      const linkHtml = buildCopilotLinkHtml(escapeHtml(cleanRaw), url, 'copilot-link-url', '');
      return linkHtml ? `${stash(linkHtml)}${suffix}` : rawMatch;
    });

    // 4. Bare schemeless .onion domains (e.g. abcdef1234567890.onion/path)
    const bareOnionRe = /(^|[\s(>])([a-z2-7]{16,56}\.onion(?:\/(?:(?!&(?:lt|gt|quot|#0?39);)[^\s<>\uE000\uE001])*)?)/gi;
    html = html.replace(bareOnionRe, (fullMatch, prefix, onionPath) => {
      const { url, suffix } = trimTrailingUrlPunct(onionPath);
      const linkHtml = buildCopilotLinkHtml(escapeHtml(url), `http://${url}`, 'copilot-link-url', '');
      return linkHtml ? `${prefix}${stash(linkHtml)}${suffix}` : fullMatch;
    });

    // 5. Reference numbers [1], [2] -> clickable source links when matching session results exist
    html = html.replace(/\[(\d+)\]/g, (_m, numStr) => {
      const num = parseInt(numStr, 10);
      const item = (num >= 1 && num <= resolvedResults.length) ? resolvedResults[num - 1] : null;
      if (item && item.url) {
        const titleHint = item.title ? `[${num}] ${item.title} — ${item.url}` : item.url;
        const citeLink = buildCopilotLinkHtml(`[${numStr}]`, item.url, 'copilot-cite copilot-cite-link', titleHint);
        if (citeLink) return stash(citeLink);
      }
      return stash(`<span class="copilot-cite">[${numStr}]</span>`);
    });

    // 6. Bullet points (handle `* ` bullets before italic conversion)
    html = html.replace(/^• (.*?)$/gm, '<li>$1</li>');
    html = html.replace(/^- (.*?)$/gm, '<li>$1</li>');
    html = html.replace(/^\* (.*?)$/gm, '<li>$1</li>');

    // 7. Bold **text** and Italic *text*
    html = formatInlineStyles(html);

    // 8. Line breaks
    html = html.replace(/\n\n/g, '<br><br>').replace(/\n/g, '<br>');

    // 9. Restore protected code & link tokens
    html = html.replace(/\uE000CPTOK(\d+)\uE001/g, (_m, idx) => tokens[Number(idx)] || '');
    return html;
  }

  function applyThinkState(msgEl, wrapEl, isStreaming, isThinkingStreaming) {
    if (!msgEl || !wrapEl) return;
    const expanded = Boolean(msgEl._thinkExpanded);
    const toggleBtn = wrapEl.querySelector('.copilot-think-toggle');
    const labelEl = wrapEl.querySelector('.copilot-think-label');
    const panelEl = wrapEl.querySelector('.copilot-think-panel');

    wrapEl.classList.toggle('is-open', expanded);
    wrapEl.classList.toggle('is-streaming', Boolean(isStreaming && isThinkingStreaming));

    if (toggleBtn) {
      toggleBtn.setAttribute('aria-expanded', expanded ? 'true' : 'false');
    }
    if (labelEl) {
      if (expanded) {
        labelEl.textContent = 'Hide Thinking';
      } else if (isStreaming && isThinkingStreaming) {
        labelEl.textContent = 'Thinking...';
      } else {
        labelEl.textContent = 'Show Thinking';
      }
    }
    if (panelEl) {
      panelEl.style.display = expanded ? 'block' : 'none';
    }
  }

  function renderAssistantBubble(msgEl, rawText, isStreaming) {
    if (!msgEl) return;
    const bubbleEl = msgEl.querySelector('.copilot-msg-bubble');
    const textEl = msgEl.querySelector('.copilot-msg-text');
    if (!bubbleEl || !textEl) return;

    const { thinking, body, isThinkingStreaming } = splitThinkingContent(rawText);
    msgEl._lastThinkingStreaming = isThinkingStreaming;

    let wrapEl = bubbleEl.querySelector('.copilot-think-wrap');
    if (thinking) {
      if (!wrapEl) {
        wrapEl = document.createElement('div');
        wrapEl.className = 'copilot-think-wrap';
        wrapEl.innerHTML = `
          <button type="button" class="copilot-think-toggle" aria-expanded="false" title="Toggle AI reasoning">
            <i class="fas fa-lightbulb copilot-think-bulb" aria-hidden="true"></i>
            <span class="copilot-think-label">Show Thinking</span>
            <i class="fas fa-chevron-down copilot-think-chevron" aria-hidden="true"></i>
          </button>
          <div class="copilot-think-panel"></div>
        `;
        const toggleBtn = wrapEl.querySelector('.copilot-think-toggle');
        if (toggleBtn) {
          toggleBtn.addEventListener('click', () => {
            msgEl._thinkExpanded = !msgEl._thinkExpanded;
            applyThinkState(msgEl, wrapEl, false, msgEl._lastThinkingStreaming);
          });
        }
        bubbleEl.insertBefore(wrapEl, textEl);
      }
      const panelEl = wrapEl.querySelector('.copilot-think-panel');
      if (panelEl) {
        panelEl.textContent = thinking;
        if (msgEl._thinkExpanded && isStreaming) {
          panelEl.scrollTop = panelEl.scrollHeight;
        }
      }
      applyThinkState(msgEl, wrapEl, isStreaming, isThinkingStreaming);
    } else if (wrapEl) {
      wrapEl.remove();
    }

    if (body) {
      textEl.innerHTML = formatMarkdown(body, msgEl._citeResults);
    } else if (thinking && isStreaming) {
      textEl.innerHTML = '<span class="copilot-typing-dots"><span>.</span><span>.</span><span>.</span></span>';
    } else if (thinking && !isStreaming) {
      textEl.innerHTML = '<span class="copilot-think-empty-note"><i class="fas fa-lightbulb" aria-hidden="true"></i> Reasoning available above (click Show Thinking to inspect).</span>';
    } else {
      textEl.innerHTML = '';
    }

    if (!isStreaming && body) {
      if (window.SearchCopilotVoice && typeof window.SearchCopilotVoice.attachListenAction === 'function') {
        window.SearchCopilotVoice.attachListenAction(msgEl, body);
      }
    }
  }

  return {
    escapeHtml,
    splitThinkingContent,
    unescapeBasicEntities,
    resolveSafeHref,
    buildCopilotLinkHtml,
    trimTrailingUrlPunct,
    formatInlineStyles,
    formatMarkdown,
    applyThinkState,
    renderAssistantBubble
  };
})();
