/**
 * Hecos Playbooks - Module Initializer
 * Bootstraps the Playbooks panel upon fragment insertion and tab activation.
 */
window.HecosPlaybooks = window.HecosPlaybooks || {};

(function(HP) {
  HP.init = function() {
    // Initial fetch of playbooks list and settings
    if (typeof window.pbReloadList === 'function') {
      window.pbReloadList();
    }
  };

  // Run automatically shortly after scripts are loaded
  setTimeout(HP.init, 100);
})(window.HecosPlaybooks);
