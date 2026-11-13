/**
 * search_engine_chips.js
 * Engine/provider identity mapping, granular provider chips, exclusion pills, stream-bar collapse state, and engine matcher.
 */
window.SearchEngineChips = (function () {
  'use strict';
  const state = window.SearchState;

  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  // ── Known Providers Catalog & Extraction ─────────────────────────────────
  const KNOWN_PROVIDERS = [
    { id: 'google', name: 'Google', icon: 'fab fa-google', test: /(google|google_images|google_videos)/i },
    { id: 'bing', name: 'Bing', icon: 'fab fa-microsoft', test: /(bing|bing_images|bing_videos)/i },
    { id: 'yandex', name: 'Yandex', icon: 'fab fa-yandex', test: /(yandex|yandex_images)/i },
    { id: 'duckduckgo', name: 'DuckDuckGo', icon: 'fas fa-feather', test: /(duckduckgo|ddgs)/i },
    { id: 'yahoo', name: 'Yahoo', icon: 'fab fa-yahoo', test: /yahoo/i },
    { id: 'wikipedia', name: 'Wikipedia / Commons', icon: 'fab fa-wikipedia-w', test: /(wikipedia|wikicommons|commons)/i },
    { id: 'brave', name: 'Brave', icon: 'fas fa-shield', test: /brave/i },
    { id: 'startpage', name: 'Startpage', icon: 'fas fa-magnifying-glass', test: /startpage/i },
    { id: 'unsplash', name: 'Unsplash', icon: 'fas fa-camera', test: /unsplash/i },
    { id: 'openverse', name: 'Openverse', icon: 'fas fa-images', test: /openverse/i },
    { id: 'dailymotion', name: 'Dailymotion', icon: 'fas fa-play', test: /dailymotion/i },
    { id: 'peertube', name: 'PeerTube', icon: 'fas fa-circle-play', test: /peertube/i },
    { id: 'sepiasearch', name: 'SepiaSearch', icon: 'fas fa-film', test: /sepiasearch/i },
    { id: 'bitchute', name: 'BitChute', icon: 'fas fa-video', test: /bitchute/i },
    { id: 'odysee', name: 'Odysee', icon: 'fas fa-play-circle', test: /odysee/i },
    { id: 'piped', name: 'Piped', icon: 'fas fa-play', test: /piped/i },
    { id: 'invidious', name: 'Invidious', icon: 'fas fa-play', test: /invidious/i },
    { id: 'youtube', name: 'YouTube', icon: 'fab fa-youtube', test: /(youtube|yt-dlp)/i },
    { id: 'vimeo', name: 'Vimeo', icon: 'fab fa-vimeo-v', test: /vimeo/i },
    { id: 'rumble', name: 'Rumble', icon: 'fas fa-play-circle', test: /rumble/i },
    { id: 'eporner', name: 'Eporner', icon: 'fas fa-film', test: /eporner/i },
    { id: 'redtube', name: 'RedTube', icon: 'fas fa-video', test: /redtube/i },
    { id: 'archive_org', name: 'Archive.org', icon: 'fas fa-landmark', test: /archive_org/i },
    { id: 'soundcloud', name: 'SoundCloud', icon: 'fab fa-soundcloud', test: /soundcloud/i },
    { id: 'mixcloud', name: 'Mixcloud', icon: 'fab fa-mixcloud', test: /mixcloud/i },
    { id: 'itunes', name: 'Apple Podcasts', icon: 'fab fa-apple', test: /itunes/i },
    { id: 'artic', name: 'Artic Museum', icon: 'fas fa-palette', test: /artic/i },
    { id: 'genius', name: 'Genius', icon: 'fas fa-align-left', test: /genius/i },
    { id: 'file_dork', name: 'Dorks Hunter', icon: 'fas fa-file-shield', test: /(dork|file_dork)/i },
    { id: 'ahmia', name: 'Tor: Ahmia', icon: 'fas fa-user-secret', test: /ahmia/i },
    { id: 'torch', name: 'Tor: Torch', icon: 'fas fa-fire', test: /torch/i },
    { id: 'haystak', name: 'Tor: Haystak', icon: 'fas fa-wheat-awn', test: /haystak/i },
    { id: 'excavator', name: 'Tor: Excavator', icon: 'fas fa-compass', test: /excavator/i },
    { id: 'phobos', name: 'Tor: Phobos', icon: 'fas fa-moon', test: /phobos/i },
    { id: 'tor66', name: 'Tor: Tor66', icon: 'fas fa-route', test: /tor66/i },
    { id: 'danieltore', name: 'Tor: DanielTore', icon: 'fas fa-network-wired', test: /danieltore/i },
    // News & Media
    { id: 'reuters', name: 'Reuters', icon: 'fas fa-newspaper', test: /reuters/i },
    { id: 'wikinews', name: 'Wikinews', icon: 'fab fa-wikipedia-w', test: /wikinews/i },
    // Social & Discussions
    { id: 'reddit', name: 'Reddit', icon: 'fab fa-reddit', test: /reddit/i },
    { id: 'mastodon', name: 'Mastodon', icon: 'fab fa-mastodon', test: /mastodon/i },
    { id: 'lemmy', name: 'Lemmy', icon: 'fas fa-comments', test: /lemmy/i },
    // Science & Academic
    { id: 'arxiv', name: 'arXiv', icon: 'fas fa-graduation-cap', test: /arxiv/i },
    { id: 'scholar', name: 'Google Scholar', icon: 'fas fa-book', test: /scholar/i },
    { id: 'pubmed', name: 'PubMed', icon: 'fas fa-dna', test: /pubmed/i },
    { id: 'semantic_scholar', name: 'Semantic Scholar', icon: 'fas fa-brain', test: /semantic.*scholar/i },
    // IT & Development
    { id: 'github', name: 'GitHub', icon: 'fab fa-github', test: /github/i },
    { id: 'stackoverflow', name: 'Stack Overflow', icon: 'fab fa-stack-overflow', test: /(stackoverflow|askubuntu|superuser)/i },
    { id: 'pypi', name: 'PyPI', icon: 'fab fa-python', test: /pypi/i },
    { id: 'docker', name: 'Docker Hub', icon: 'fab fa-docker', test: /docker/i },
    { id: 'hackernews', name: 'Hacker News', icon: 'fab fa-y-combinator', test: /(hackernews|hn)/i },
    { id: 'mdn', name: 'MDN Web Docs', icon: 'fab fa-firefox-browser', test: /mdn/i },
    // Files & Torrents
    { id: 'kickass', name: 'Kickass', icon: 'fas fa-download', test: /kickass/i },
    { id: 'piratebay', name: 'The Pirate Bay', icon: 'fas fa-skull-crossbones', test: /piratebay/i },
    { id: 'solidtorrents', name: 'Solid Torrents', icon: 'fas fa-magnet', test: /solidtorrents/i },
    { id: 'bt4g', name: 'BT4G', icon: 'fas fa-magnet', test: /bt4g/i },
    { id: 'annas_archive', name: "Anna's Archive", icon: 'fas fa-book-open', test: /anna.*archive/i },
    { id: 'zlibrary', name: 'Z-Library', icon: 'fas fa-book-bookmark', test: /(zlibrary|z-library)/i },
    // Visual Media
    { id: 'flickr', name: 'Flickr', icon: 'fab fa-flickr', test: /flickr/i },
    { id: 'deviantart', name: 'DeviantArt', icon: 'fab fa-deviantart', test: /deviantart/i },
    { id: 'wallhaven', name: 'Wallhaven', icon: 'fas fa-image', test: /wallhaven/i },
    { id: 'pinterest', name: 'Pinterest', icon: 'fab fa-pinterest', test: /pinterest/i },
    // Music & Radio
    { id: 'bandcamp', name: 'Bandcamp', icon: 'fab fa-bandcamp', test: /bandcamp/i },
    { id: 'deezer', name: 'Deezer', icon: 'fas fa-music', test: /deezer/i },
    { id: 'radio_browser', name: 'Radio Browser', icon: 'fas fa-radio', test: /radio.*browser/i },
    // OSINT & Identity Providers
    { id: 'linkedin', name: 'LinkedIn', icon: 'fab fa-linkedin', test: /linkedin/i },
    { id: 'twitter', name: 'X / Twitter', icon: 'fab fa-x-twitter', test: /(twitter|x\.com)/i },
    { id: 'instagram', name: 'Instagram', icon: 'fab fa-instagram', test: /instagram/i },
    { id: 'facebook', name: 'Facebook', icon: 'fab fa-facebook', test: /facebook/i },
    { id: 'tiktok', name: 'TikTok', icon: 'fab fa-tiktok', test: /tiktok/i },
    { id: 'telegram', name: 'Telegram', icon: 'fab fa-telegram', test: /telegram/i },
    { id: 'gitlab', name: 'GitLab', icon: 'fab fa-gitlab', test: /gitlab/i },
    { id: 'keybase', name: 'Keybase', icon: 'fab fa-keybase', test: /keybase/i },
    { id: 'gravatar', name: 'Gravatar', icon: 'fas fa-user-check', test: /gravatar/i },
    { id: 'medium', name: 'Medium', icon: 'fab fa-medium', test: /medium/i },
    { id: 'crtsh', name: 'crt.sh', icon: 'fas fa-certificate', test: /crtsh/i },
    { id: 'osint_dork', name: 'OSINT Dorks', icon: 'fas fa-fingerprint', test: /(osint:dork|sherlock)/i },
    // References & Maps
    { id: 'imdb', name: 'IMDB', icon: 'fab fa-imdb', test: /imdb/i },
    { id: 'openstreetmap', name: 'OpenStreetMap', icon: 'fas fa-map-location-dot', test: /(openstreetmap|osm|photon)/i },
    { id: 'wikidata', name: 'Wikidata', icon: 'fas fa-barcode', test: /wikidata/i },
    { id: 'wttr', name: 'Weather', icon: 'fas fa-cloud-sun', test: /wttr/i }
  ];


  // ── Sub-Engine Display Labels & Icons ────────────────────────────────────
  // Maps raw r.engine strings (actual data sources) to display metadata.
  // Used by renderGranularProviderChips() for the bottom-row source panel.
  const ENGINE_LABELS = {
    // DuckDuckGo variants
    'ddgs': { name: 'DDG Web', icon: 'fas fa-feather' },
    'ddgs:images': { name: 'DDG Images', icon: 'fas fa-feather' },
    'ddgs:news': { name: 'DDG News', icon: 'fas fa-feather' },
    'ddgs:videos': { name: 'DDG Videos', icon: 'fas fa-feather' },
    'clear_ddgs': { name: 'DDG Web', icon: 'fas fa-feather' },
    // SearXNG aggregated
    'clear_searxng': { name: 'SearXNG Web', icon: 'fas fa-magnifying-glass' },
    'searxng': { name: 'SearXNG', icon: 'fas fa-magnifying-glass' },
    // SearXNG per-engine sub-sources
    'searxng:yahoo': { name: 'Yahoo (SXG)', icon: 'fab fa-yahoo' },
    'searxng:bing': { name: 'Bing (SXG)', icon: 'fab fa-microsoft' },
    'searxng:google': { name: 'Google (SXG)', icon: 'fab fa-google' },
    'searxng:duckduckgo': { name: 'DDG (SXG)', icon: 'fas fa-feather' },
    'searxng:yandex': { name: 'Yandex (SXG)', icon: 'fab fa-yandex' },
    'searxng:startpage': { name: 'Startpage (SXG)', icon: 'fas fa-magnifying-glass' },
    'searxng:brave': { name: 'Brave (SXG)', icon: 'fas fa-shield' },
    'searxng:wikipedia': { name: 'Wikipedia (SXG)', icon: 'fab fa-wikipedia-w' },
    'searxng:wikicommons': { name: 'Wiki Commons (SXG)', icon: 'fab fa-wikipedia-w' },
    'searxng:artic': { name: 'Artic Museum', icon: 'fas fa-palette' },
    'searxng:genius': { name: 'Genius', icon: 'fas fa-align-left' },
    'searxng:soundcloud': { name: 'SoundCloud', icon: 'fab fa-soundcloud' },
    'searxng:mixcloud': { name: 'Mixcloud', icon: 'fab fa-mixcloud' },
    'searxng:bandcamp': { name: 'Bandcamp', icon: 'fas fa-music' },
    'searxng:unsplash': { name: 'Unsplash', icon: 'fas fa-camera' },
    'searxng:openverse': { name: 'Openverse', icon: 'fas fa-images' },
    'searxng:peertube': { name: 'PeerTube (SXG)', icon: 'fas fa-circle-play' },
    'searxng:sepiasearch': { name: 'SepiaSearch (SXG)', icon: 'fas fa-film' },
    'searxng:bitchute': { name: 'BitChute (SXG)', icon: 'fas fa-video' },
    'searxng:odysee': { name: 'Odysee (SXG)', icon: 'fas fa-play-circle' },
    'searxng:piped': { name: 'Piped (SXG)', icon: 'fas fa-play' },
    'searxng:invidious': { name: 'Invidious (SXG)', icon: 'fas fa-play' },
    'searxng:redtube': { name: 'RedTube (SXG)', icon: 'fas fa-video' },
    'searxng:vimeo': { name: 'Vimeo (SXG)', icon: 'fab fa-vimeo-v' },
    'searxng:youtube': { name: 'YouTube (SXG)', icon: 'fab fa-youtube' },
    'searxng:dailymotion': { name: 'Dailymotion (SXG)', icon: 'fas fa-play' },
    'searxng:rumble': { name: 'Rumble (SXG)', icon: 'fas fa-play-circle' },
    'searxng:reddit': { name: 'Reddit (SXG)', icon: 'fab fa-reddit' },
    // RSS
    'rss:google_news': { name: 'Google News', icon: 'fab fa-google' },
    'rss:bing_news': { name: 'Bing News', icon: 'fab fa-microsoft' },
    'rss:yahoo_news': { name: 'Yahoo News', icon: 'fab fa-yahoo' },
    'rss': { name: 'RSS Feed', icon: 'fas fa-rss' },
    // Video platforms (direct)
    'youtube': { name: 'YouTube', icon: 'fab fa-youtube' },
    'yt-dlp': { name: 'YouTube (yt-dlp)', icon: 'fab fa-youtube' },
    'dailymotion': { name: 'Dailymotion', icon: 'fas fa-play' },
    'peertube': { name: 'PeerTube', icon: 'fas fa-circle-play' },
    'sepiasearch': { name: 'SepiaSearch', icon: 'fas fa-film' },
    'bitchute': { name: 'BitChute', icon: 'fas fa-video' },
    'odysee': { name: 'Odysee', icon: 'fas fa-play-circle' },
    'piped': { name: 'Piped', icon: 'fas fa-play' },
    'invidious': { name: 'Invidious', icon: 'fas fa-play' },
    'vimeo': { name: 'Vimeo', icon: 'fab fa-vimeo-v' },
    'rumble': { name: 'Rumble', icon: 'fas fa-play-circle' },
    'eporner': { name: 'Eporner', icon: 'fas fa-film' },
    'eporner:stream': { name: 'Eporner', icon: 'fas fa-film' },
    'redtube': { name: 'RedTube', icon: 'fas fa-video' },
    'redtube:stream': { name: 'RedTube', icon: 'fas fa-video' },
    // Archive
    'archive_org:video': { name: 'Archive.org Video', icon: 'fas fa-landmark' },
    'archive_org:audio': { name: 'Archive.org Audio', icon: 'fas fa-landmark' },
    'archive_org:texts': { name: 'Archive.org Texts', icon: 'fas fa-landmark' },
    'archive_org': { name: 'Archive.org', icon: 'fas fa-landmark' },
    // Audio platforms
    'soundcloud': { name: 'SoundCloud', icon: 'fab fa-soundcloud' },
    'mixcloud': { name: 'Mixcloud', icon: 'fab fa-mixcloud' },
    'bandcamp': { name: 'Bandcamp', icon: 'fas fa-music' },
    'audio_stream': { name: 'Audio Stream', icon: 'fas fa-music' },
    'itunes:music': { name: 'Apple Music', icon: 'fab fa-apple' },
    'itunes:podcast': { name: 'Apple Podcasts', icon: 'fab fa-apple' },
    'itunes': { name: 'Apple Podcasts', icon: 'fab fa-apple' },
    // Images
    'media_images': { name: 'Images (all)', icon: 'fas fa-image' },
    'media_videos': { name: 'Videos (all)', icon: 'fas fa-video' },
    'media_audio': { name: 'Audio (all)', icon: 'fas fa-music' },
    // Tor
    'ahmia': { name: 'Tor: Ahmia', icon: 'fas fa-user-secret' },
    'torch': { name: 'Tor: Torch', icon: 'fas fa-fire' },
    'haystak': { name: 'Tor: Haystak', icon: 'fas fa-wheat-awn' },
    'excavator': { name: 'Tor: Excavator', icon: 'fas fa-compass' },
    'phobos': { name: 'Tor: Phobos', icon: 'fas fa-moon' },
    'tor66': { name: 'Tor: Tor66', icon: 'fas fa-route' },
    'danieltore': { name: 'Tor: DanielTore', icon: 'fas fa-network-wired' },
    // Files / Dorks
    'file_dork': { name: 'Dorks Hunter', icon: 'fas fa-file-shield' },
    'files_dorks': { name: 'Dorks Hunter', icon: 'fas fa-file-shield' },
    // OSINT
    'osint:sherlock': { name: 'Sherlock', icon: 'fas fa-id-badge' },
    'osint:dork': { name: 'OSINT Dorks', icon: 'fas fa-fingerprint' },
    'osint:dork_html': { name: 'OSINT Dorks', icon: 'fas fa-fingerprint' },
    'osint:github': { name: 'GitHub OSINT', icon: 'fab fa-github' },
    'osint:gitlab': { name: 'GitLab OSINT', icon: 'fab fa-gitlab' },
    'osint:reddit': { name: 'Reddit OSINT', icon: 'fab fa-reddit' },
    'osint:hackernews': { name: 'HN OSINT', icon: 'fab fa-y-combinator' },
    'osint:wikipedia': { name: 'Wikipedia', icon: 'fab fa-wikipedia-w' },
    'osint:wikidata': { name: 'Wikidata', icon: 'fas fa-barcode' },
    'osint:gravatar': { name: 'Gravatar', icon: 'fas fa-user-check' },
    'osint:keybase': { name: 'Keybase', icon: 'fab fa-keybase' },
    'osint:archive_org': { name: 'Archive.org', icon: 'fas fa-landmark' },
    'osint:crtsh': { name: 'crt.sh', icon: 'fas fa-certificate' },
    // News
    'clear_news': { name: 'News Aggregator', icon: 'fas fa-newspaper' },
    'searxng:google news': { name: 'Google News (SXG)', icon: 'fab fa-google' },
    'searxng:bing news': { name: 'Bing News (SXG)', icon: 'fab fa-microsoft' },
    'searxng:yahoo news': { name: 'Yahoo News (SXG)', icon: 'fab fa-yahoo' },
    'searxng:brave news': { name: 'Brave News (SXG)', icon: 'fas fa-shield' },
    'searxng:duckduckgo news': { name: 'DDG News (SXG)', icon: 'fas fa-feather' },
    'searxng:reuters': { name: 'Reuters', icon: 'fas fa-newspaper' },
    'searxng:wikinews': { name: 'Wikinews', icon: 'fab fa-wikipedia-w' },
    // Social & Discussions
    'searxng:mastodon users': { name: 'Mastodon', icon: 'fab fa-mastodon' },
    'searxng:lemmy posts': { name: 'Lemmy', icon: 'fas fa-comments' },
    // Science & Academic
    'searxng:arxiv': { name: 'arXiv', icon: 'fas fa-graduation-cap' },
    'searxng:google scholar': { name: 'Google Scholar', icon: 'fas fa-book' },
    'searxng:pubmed': { name: 'PubMed', icon: 'fas fa-dna' },
    'searxng:semantic scholar': { name: 'Semantic Scholar', icon: 'fas fa-brain' },
    // IT & Development
    'searxng:github': { name: 'GitHub', icon: 'fab fa-github' },
    'searxng:stackoverflow': { name: 'Stack Overflow', icon: 'fab fa-stack-overflow' },
    'searxng:pypi': { name: 'PyPI', icon: 'fab fa-python' },
    'searxng:docker hub': { name: 'Docker Hub', icon: 'fab fa-docker' },
    'searxng:hackernews': { name: 'Hacker News', icon: 'fab fa-y-combinator' },
    'searxng:mdn': { name: 'MDN Web Docs', icon: 'fab fa-firefox-browser' },
    // Files & Torrents
    'searxng:kickass': { name: 'Kickass', icon: 'fas fa-download' },
    'searxng:piratebay': { name: 'The Pirate Bay', icon: 'fas fa-skull-crossbones' },
    'searxng:solidtorrents': { name: 'Solid Torrents', icon: 'fas fa-magnet' },
    'searxng:bt4g': { name: 'BT4G', icon: 'fas fa-magnet' },
    'searxng:annas archive': { name: "Anna's Archive", icon: 'fas fa-book-open' },
    'searxng:z-library': { name: 'Z-Library', icon: 'fas fa-book-bookmark' },
    // Visual Media
    'searxng:flickr': { name: 'Flickr', icon: 'fab fa-flickr' },
    'searxng:deviantart': { name: 'DeviantArt', icon: 'fab fa-deviantart' },
    'searxng:wallhaven': { name: 'Wallhaven', icon: 'fas fa-image' },
    'searxng:pinterest': { name: 'Pinterest', icon: 'fab fa-pinterest' },
    // Music & Audio
    'searxng:deezer': { name: 'Deezer', icon: 'fas fa-music' },
    'searxng:piped.music': { name: 'Piped Music', icon: 'fas fa-headphones' },
    'searxng:radio browser': { name: 'Radio Browser', icon: 'fas fa-radio' },
    // Other & Reference
    'searxng:imdb': { name: 'IMDB', icon: 'fab fa-imdb' },
    'searxng:openstreetmap': { name: 'OpenStreetMap', icon: 'fas fa-map-location-dot' },
    'searxng:wikidata': { name: 'Wikidata', icon: 'fas fa-barcode' },
    'searxng:wttr.in': { name: 'Weather', icon: 'fas fa-cloud-sun' },
    'searxng:currency': { name: 'Currency', icon: 'fas fa-coins' },
  };

  /**
   * getEngineDisplayInfo(engineStr)
   * Returns {name, icon} for a raw r.engine string.
   * Falls back to a prettified version of the engine string itself.
   */
  function getEngineDisplayInfo(engineStr) {
    if (!engineStr) return { name: 'Unknown', icon: 'fas fa-circle-nodes' };
    const lower = engineStr.toLowerCase();
    if (ENGINE_LABELS[lower]) return ENGINE_LABELS[lower];
    // Prettify unknown: "searxng:custom_name" -> "Custom Name (SXG)"
    if (lower.startsWith('searxng:')) {
      const sub = lower.slice(8).replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
      return { name: `${sub} (SXG)`, icon: 'fas fa-magnifying-glass' };
    }
    if (lower.startsWith('ddgs:')) {
      const sub = lower.slice(5).replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
      return { name: `DDG ${sub}`, icon: 'fas fa-feather' };
    }
    if (lower.startsWith('rss:')) {
      const sub = lower.slice(4).replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
      return { name: sub, icon: 'fas fa-rss' };
    }
    const cleanName = lower.replace(/_/g, ' ').replace(/:/g, ' · ').replace(/\b\w/g, c => c.toUpperCase());
    return { name: cleanName, icon: 'fas fa-circle-nodes' };
  }

  function extractProvider(r) {
    if (!r) return { id: 'unknown', name: 'Unknown', icon: 'fas fa-circle-nodes' };
    const sourceEng = (r.metadata?.source_engine || '').toLowerCase();
    const eng = (r.engine || '').toLowerCase();
    const engId = (r.engine_id || r.metadata?.engine_id || '').toLowerCase();
    const publisher = (r.metadata?.publisher || '').toLowerCase();
    const combined = `${sourceEng} ${eng} ${engId} ${publisher}`;

    for (const kp of KNOWN_PROVIDERS) {
      if (kp.test.test(combined)) {
        return kp;
      }
    }

    if (r.network === 'tor' || (r.url && r.url.includes('.onion'))) {
      try {
        const onionHost = r.url ? (new URL(r.url, 'http://onion.invalid')).hostname.replace('.onion', '') : 'onion';
        const label = onionHost.length > 12 ? onionHost.slice(0, 8) + '...' : onionHost;
        return { id: 'onion_' + label, name: `Tor: ${label}`, icon: 'fas fa-user-secret' };
      } catch (e) {
        return { id: 'onion_site', name: 'Tor .onion', icon: 'fas fa-user-secret' };
      }
    }

    const fallbackId = (sourceEng || eng.replace(/^(searxng:|ddgs:|rss:)/, '') || engId || 'other').trim().toLowerCase();
    const cleanName = fallbackId.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
    return { id: fallbackId, name: cleanName, icon: 'fas fa-circle-nodes' };
  }

  function providerMatches(r, targetProviderId) {
    if (!targetProviderId) return true;
    const target = targetProviderId.toLowerCase();
    // Match on raw r.engine — same key used by renderGranularProviderChips
    const rawEng = (r.engine || r.engine_id || '').trim().toLowerCase();
    return rawEng === target;
  }

  function filterByProvider(providerId) {
    if (state.activeProvider === providerId) {
      state.activeProvider = null; // Toggle off
    } else {
      state.activeProvider = providerId;
      state.activeEngine = null; // Prioritize granular provider
    }
    updateEngineChipsSelection();
    window.renderCurrentView?.();
  }

  function clearProviderFilter() {
    state.activeProvider = null;
    updateEngineChipsSelection();
    window.renderCurrentView?.();
  }

  // ── Provider Exclusion System ──────────────────────────────────────────
  function toggleExcludeProvider(providerId) {
    if (!state.excludedProviders) state.excludedProviders = [];
    const idx = state.excludedProviders.indexOf(providerId);
    if (idx >= 0) {
      // Already excluded — re-include
      state.excludedProviders.splice(idx, 1);
    } else {
      state.excludedProviders.push(providerId);
      // Cannot both include-filter and exclude same provider
      if (state.activeProvider === providerId) state.activeProvider = null;
    }
    renderGranularProviderChips();
    window.renderCurrentView?.();
    updateExclusionBar();
  }

  function clearAllExclusions() {
    state.excludedProviders = [];
    renderGranularProviderChips();
    window.renderCurrentView?.();
    updateExclusionBar();
  }

  function getProviderDisplayName(id) {
    if (!id) return '';
    const lower = String(id).toLowerCase();
    if (ENGINE_LABELS[lower]) return ENGINE_LABELS[lower].name;
    const kp = KNOWN_PROVIDERS.find(p => p.id === lower);
    if (kp) return kp.name;
    return getEngineDisplayInfo(id).name;
  }

  function updateExclusionBar() {
    // Show/hide excluded-providers pill in the stream header
    const bar = document.getElementById('exclusion-bar');
    if (!bar) return;
    const excluded = state.excludedProviders || [];
    if (excluded.length === 0) {
      bar.style.display = 'none';
      return;
    }
    bar.style.display = 'flex';
    const tagsHtml = excluded.map(id => {
      const safeId = escapeHtml(id);
      const safeName = escapeHtml(getProviderDisplayName(id));
      return `<span class="excl-tag">${safeName} <span class="excl-remove" data-provider-excl="${safeId}" onclick="window.toggleExcludeProvider(this.dataset.providerExcl)">✕</span></span>`;
    }).join(' ');
    bar.innerHTML = `<i class="fas fa-ban"></i> Excluded: ${tagsHtml}<button type="button" class="excl-clear-all" onclick="window.clearAllExclusions()">Clear all</button>`;
  }


  function filterByEngine(engineId) {
    if (state.activeEngine === engineId) {
      state.activeEngine = null; // Toggle off
    } else {
      state.activeEngine = engineId;
      state.activeProvider = null;
      setFilter('all', false, false);
    }
    updateEngineChipsSelection();
    window.renderCurrentView?.();
  }

  function clearEngineFilter() {
    state.activeEngine = null;
    state.activeProvider = null;
    updateEngineChipsSelection();
    window.renderCurrentView?.();
  }

  function updateEngineChipsSelection() {
    const btnClearEngine = document.getElementById('btn-clear-engine-filter');
    const clearLabel = document.getElementById('btn-clear-filter-label');
    const hasAnyFilter = Boolean(state.activeEngine || state.activeProvider);
    if (btnClearEngine) {
      btnClearEngine.style.display = hasAnyFilter ? 'inline-flex' : 'none';
      if (clearLabel) {
        if (state.activeProvider) {
          const name = getProviderDisplayName(state.activeProvider);
          clearLabel.innerText = `Active filter: ${name} (✖ Show all)`;
        } else if (state.activeEngine) {
          const engChip = document.getElementById(`chip-${state.activeEngine}`);
          const engName = engChip ? (engChip.querySelector('.chip-engine-name')?.innerText || state.activeEngine) : state.activeEngine;
          clearLabel.innerText = `Active filter: ${engName} (✖ Show all)`;
        } else {
          clearLabel.innerText = 'Show all sources';
        }
      }
    }
    document.querySelectorAll('.engine-chip').forEach(chip => {
      const eng = chip.dataset.engine || chip.id.replace('chip-', '');
      chip.classList.toggle('selected-engine', eng === state.activeEngine && !state.activeProvider);
    });
    document.querySelectorAll('.provider-chip').forEach(chip => {
      const prov = chip.dataset.provider;
      chip.classList.toggle('selected-provider', prov === state.activeProvider);
    });
    updateCollapsedPill();
  }

  function toggleStreamBarCollapse(event, explicitVal) {
    if (event) {
      const t = event.target;
      if (t && (t.closest('#btn-clear-engine-filter') || t.closest('.engine-chip') || t.closest('.provider-chip'))) {
        return;
      }
    }
    const bar = document.getElementById('stream-live-bar');
    const btn = document.getElementById('btn-toggle-stream-collapse');
    const icon = document.getElementById('icon-stream-collapse');
    const text = document.getElementById('text-stream-collapse');
    if (!bar) return;

    if (typeof explicitVal === 'boolean') {
      state.isStreamCollapsed = explicitVal;
    } else {
      state.isStreamCollapsed = !state.isStreamCollapsed;
    }

    try {
      if (typeof localStorage !== 'undefined') {
        localStorage.setItem('hecos_stream_collapsed', state.isStreamCollapsed ? 'true' : 'false');
      }
    } catch (e) { }

    bar.classList.toggle('is-collapsed', state.isStreamCollapsed);
    if (icon) {
      icon.className = state.isStreamCollapsed ? 'fas fa-chevron-down' : 'fas fa-chevron-up';
    }
    if (text) {
      text.innerText = state.isStreamCollapsed ? 'Expand' : 'Collapse';
    }
    if (btn) {
      btn.title = state.isStreamCollapsed ? 'Expand engines and providers panel' : 'Collapse engines and providers panel';
    }

    updateCollapsedPill();
  }

  function updateCollapsedPill() {
    const pill = document.getElementById('stream-collapsed-pill');
    if (!pill) return;
    if (state.isStreamCollapsed) {
      let label = '';
      if (state.activeProvider) {
        const name = escapeHtml(getProviderDisplayName(state.activeProvider));
        label = `<i class="fas fa-filter"></i> Filter: ${name}`;
      } else if (state.activeEngine) {
        const engChip = document.getElementById(`chip-${state.activeEngine}`);
        const engName = escapeHtml(engChip ? (engChip.querySelector('.chip-engine-name')?.innerText || state.activeEngine) : state.activeEngine);
        label = `<i class="fas fa-filter"></i> Filter: ${engName}`;
      } else {
        const allStats = state.engineStats || {};
        const total = Object.keys(allStats).length;
        const withRes = Object.values(allStats).filter(s => s.count > 0).length;
        if (total > 0) {
          label = `<i class="fas fa-layer-group"></i> ${withRes}/${total} sources (${state.results.length} res.)`;
        } else {
          label = `<i class="fas fa-layer-group"></i> Engines collapsed`;
        }
      }
      pill.innerHTML = label;
      pill.style.display = 'inline-flex';
    } else {
      pill.style.display = 'none';
    }
  }

  function renderGranularProviderChips() {
    const container = document.getElementById('stream-provider-badges');
    const section = document.getElementById('stream-providers-section');
    if (!container || !section) return;

    const results = state.results || [];
    if (results.length === 0) {
      section.style.display = 'none';
      return;
    }

    // Group by raw r.engine string — the actual data-source sub-engine identifier.
    // This preserves full granularity: ddgs:images, searxng:yahoo, rss:google_news, etc.
    const engineMap = {};
    results.forEach(r => {
      const rawEng = (r.engine || r.engine_id || 'unknown').trim().toLowerCase();
      if (!engineMap[rawEng]) {
        const display = getEngineDisplayInfo(rawEng);
        engineMap[rawEng] = {
          id: rawEng,
          name: display.name,
          icon: display.icon,
          count: 0,
          categories: {}
        };
      }
      engineMap[rawEng].count += 1;
      const cat = r.category || 'web';
      engineMap[rawEng].categories[cat] = (engineMap[rawEng].categories[cat] || 0) + 1;
    });

    const list = Object.values(engineMap).sort((a, b) => b.count - a.count);
    const excludedSet = new Set(state.excludedProviders || []);

    container.innerHTML = list.map(p => {
      const isSelected = state.activeProvider === p.id;
      const isExcluded = excludedSet.has(p.id);
      const catBreakdown = Object.entries(p.categories).map(([c, n]) => `${c}: ${n}`).join(', ');
      const title = isExcluded
        ? `${p.name} [${p.id}]: EXCLUDED\nShift+Click or Right-Click to re-include`
        : `${p.name}\nEngine: ${p.id}\n${p.count} results (${catBreakdown})\nClick: filter  •  Shift+Click / Right-Click: exclude`;
      const chipClass = `provider-chip has-results ${isSelected ? 'selected-provider' : ''} ${isExcluded ? 'excluded-provider' : ''}`;
      const badgeHtml = isExcluded
        ? '<span class="provider-chip-excl-badge"><i class="fas fa-ban"></i></span>'
        : `<span class="provider-chip-count">${p.count}</span>`;
      const safeId = escapeHtml(p.id);
      const safeName = escapeHtml(p.name);
      const safeIcon = escapeHtml(p.icon);
      const safeTitle = escapeHtml(title);
      return `
        <button type="button" class="${chipClass}"
                data-provider="${safeId}"
                onclick="if(event.shiftKey||event.ctrlKey){window.toggleExcludeProvider('${safeId}')}else{window.filterByProvider('${safeId}')}"
                oncontextmenu="event.preventDefault();window.toggleExcludeProvider('${safeId}')"
                title="${safeTitle}">
          <i class="${safeIcon}"></i>
          <span class="provider-chip-name">${safeName}</span>
          ${badgeHtml}
        </button>
      `;
    }).join('');

    section.style.display = 'flex';
    updateEngineChipsSelection();
  }


  function engineMatches(r, target) {
    if (!target) return true;
    target = target.toLowerCase();
    const engId = (r.engine_id || r.metadata?.engine_id || '').toLowerCase();
    const eng = (r.engine || '').toLowerCase();
    const cat = (r.category || '').toLowerCase();

    if (engId === target || eng === target) return true;
    if (r.metadata?.engine_ids && r.metadata.engine_ids.includes(target)) return true;

    const cleanTarget = target.replace(/^(clear_|media_|dark_|osint_)/, '');
    const cleanEng = eng.replace(/^(ddgs:|rss:|torch:|ahmia:|haystak:|osint:)/, '');

    if (cleanTarget === cleanEng) return true;
    if (eng.includes(cleanTarget) || cleanEng.includes(cleanTarget)) return true;
    if (engId && (engId.includes(cleanTarget) || cleanTarget.includes(engId))) return true;

    if (target === 'clear_news' && (cat === 'news' || eng.includes('news'))) return true;
    if (target === 'clear_ddgs' && (eng.includes('ddgs') || eng.includes('clearnet') || eng.includes('duckduckgo') || engId.includes('ddgs') || engId.includes('duckduckgo'))) return true;
    if (target === 'media_images' && (cat === 'images' || eng.includes('image') || eng.includes('commons'))) return true;
    if (target === 'media_videos' && (cat === 'videos' || eng.includes('video') || eng.includes('yt-dlp') || eng.includes('youtube') || eng.includes('archive_org:video'))) return true;
    if (target === 'media_audio' && (cat === 'audio' || eng.includes('audio') || eng.includes('podcast') || eng.includes('archive_org:audio'))) return true;
    if (target === 'files_dorks' && (cat === 'files' || eng.includes('dork') || eng.includes('file') || eng.includes('archive_org:texts'))) return true;
    if (target === 'clear_searxng' && (eng.includes('searx') || eng.includes('searxng') || engId.includes('searx') || engId.includes('searxng'))) return true;
    if (target === 'osint_sherlock' && (engId === 'osint_sherlock' || eng.includes('sherlock'))) return true;
    if (target === 'osint_sources' && (engId === 'osint_sources' || (eng.startsWith('osint:') && !eng.includes('sherlock')))) return true;
    if (target.startsWith('dark_')) {
      const darkName = target.replace(/^dark_/, '');
      if (engId === target || eng === darkName || eng.includes(darkName) || engId.includes(darkName)) return true;
      if (r.network === 'tor' || (r.url && r.url.includes('.onion'))) return true;
    }

    return false;
  }

  const api = {
    KNOWN_PROVIDERS,
    ENGINE_LABELS,
    getEngineDisplayInfo,
    extractProvider,
    providerMatches,
    filterByProvider,
    clearProviderFilter,
    toggleExcludeProvider,
    clearAllExclusions,
    getProviderDisplayName,
    updateExclusionBar,
    filterByEngine,
    clearEngineFilter,
    updateEngineChipsSelection,
    toggleStreamBarCollapse,
    updateCollapsedPill,
    renderGranularProviderChips,
    engineMatches
  };

  window.filterByEngine = filterByEngine;
  window.clearEngineFilter = clearEngineFilter;
  window.engineMatches = engineMatches;
  window.filterByProvider = filterByProvider;
  window.clearProviderFilter = clearProviderFilter;
  window.toggleExcludeProvider = toggleExcludeProvider;
  window.clearAllExclusions = clearAllExclusions;
  window.updateExclusionBar = updateExclusionBar;
  window.renderGranularProviderChips = renderGranularProviderChips;
  window.toggleStreamBarCollapse = toggleStreamBarCollapse;
  window.updateCollapsedPill = updateCollapsedPill;

  return api;
})();
