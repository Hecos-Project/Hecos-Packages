/**
 * search_copilot.js
 * AI Copilot intelligence & auto-synthesis side-panel.
 */
window.SearchCopilot = (function() {

  function updateOverview(results, query, mode) {
    const summaryCard = document.getElementById('copilot-summary-content');
    if (!summaryCard) return;

    if (!results || results.length === 0) {
      summaryCard.innerHTML = '<span style="color:var(--text-dim); font-size:12px;">Waiting for search results to generate intelligence summary...</span>';
      return;
    }

    const total = results.length;
    const onionCount = results.filter(r => r.network === 'tor' || r.url.includes('.onion')).length;
    const clearCount = total - onionCount;
    const engines = [...new Set(results.map(r => r.engine))].join(', ');

    summaryCard.innerHTML = `
      <div style="font-weight:600; margin-bottom:6px; color:var(--text-main);">
        Analysis for "${query}"
      </div>
      <div style="display:flex; flex-direction:column; gap:4px; font-size:12px; color:var(--text-muted);">
        <div>• <strong>${total}</strong> sources indexed successfully</div>
        <div>• Distribution: <strong>${clearCount}</strong> Clearnet, <strong>${onionCount}</strong> Tor (.onion)</div>
        <div>• Active engines: <span style="font-family:var(--font-mono); color:var(--accent-cyan);">${engines}</span></div>
      </div>
    `;
  }

  function generateReport(results, query) {
    if (!results || results.length === 0) {
      alert('No results available to export.');
      return;
    }

    let md = `# Deep Search Investigation Report: ${query}\n`;
    md += `*Date: ${new Date().toLocaleString()}*  \n`;
    md += `*Total sources found: ${results.length}*\n\n---\n\n`;

    results.forEach((r, idx) => {
      const net = r.network === 'tor' ? '[TOR/ONION]' : '[CLEARWEB]';
      md += `### ${idx + 1}. ${net} ${r.title}\n`;
      md += `- **URL**: ${r.url}\n`;
      md += `- **Engine**: ${r.engine}\n`;
      if (r.snippet) {
        md += `- **Snippet**: ${r.snippet}\n`;
      }
      md += `\n`;
    });

    // Create and trigger download
    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `hecos_search_${query.replace(/\W+/g, '_')}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return {
    update(results, query, mode) {
      updateOverview(results, query, mode);
    },
    exportReport() {
      generateReport(window.SearchState.results, window.SearchState.currentQuery);
    }
  };
})();
