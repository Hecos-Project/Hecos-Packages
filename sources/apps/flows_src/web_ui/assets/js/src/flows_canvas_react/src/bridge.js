/**
 * HecosFlowsBridge
 * ================
 * Global bridge object that exposes the same API surface as the old LiteGraph
 * wrappers so that flows_api.js, flows_editor.js and flows_logs.js keep working
 * with zero changes.
 *
 * Populated by FlowsApp once React is mounted.
 */

const bridge = {
  // Will be set by FlowsApp once mounted
  _api: null,

  renderCanvasFromFlow(flowObj) {
    if (this._api) this._api.renderCanvasFromFlow(flowObj);
    else console.warn('[Bridge] renderCanvasFromFlow called before React mount');
  },

  exportFlowFromCanvas() {
    if (this._api) return this._api.exportFlowFromCanvas();
    return null;
  },

  setNodeState(stepId, state) {
    if (this._api) this._api.setNodeState(stepId, state);
  },

  setNodeAudioState(stepId, isPlaying) {
    if (this._api) this._api.setNodeAudioState(stepId, isPlaying);
  },

  resetNodeStates() {
    if (this._api) this._api.resetNodeStates();
  },

  deleteSelectedNodes() {
    if (this._api) this._api.deleteSelectedNodes();
  },

  setInteractionMode(mode) {
    if (this._api) this._api.setInteractionMode(mode);
  },

  /** Called by flows_editor.js to be notified when canvas graph changes */
  onGraphChange: null,

  /** Internal: called by React when nodes/edges change */
  _notifyGraphChange(flowObj) {
    if (typeof this.onGraphChange === 'function') {
      this.onGraphChange(flowObj);
    }
  },
};

window.HecosFlowsBridge = bridge;
export default bridge;
