/**
 * search_state.js
 * Central state store for Deep Search UI.
 */
window.SearchState = {
  currentQuery: '',
  currentMode: 'clear',
  activeSessionId: null,
  activeSession: null,
  results: [],
  runningEngines: new Set(),
  activeEventSource: null,
  torOnline: false,
  torIp: '',
  torPort: null,
  safeSearch: false,
  darkBypass: true,
  searchLimit: 50,
  activeFilter: 'all', // all, images, videos, audio, files, dark, osint
  activeEngine: null,
  engineStats: {},
  viewMode: (function() {
    try {
      return (typeof localStorage !== 'undefined' && localStorage.getItem('hecos_search_view_mode')) || 'scroll';
    } catch (e) {
      return 'scroll';
    }
  })(), // 'scroll' | 'paging'
  currentPage: 1,
  pageSize: 25,
  scrollRenderCount: 40,

  resetResults() {
    this.results = [];
    this.runningEngines.clear();
    this.engineStats = {};
    this.activeEngine = null;
    this.currentPage = 1;
    this.scrollRenderCount = 40;
    if (this.activeEventSource) {
      this.activeEventSource.close();
      this.activeEventSource = null;
    }
  },

  addResults(newItems, engineId = null) {
    const seen = new Set(this.results.map(r => r.url));
    for (const item of newItems) {
      if (engineId && !item.engine_id) {
        item.engine_id = engineId;
      }
      if (!seen.has(item.url)) {
        this.results.push(item);
        seen.add(item.url);
      }
    }
  }
};
