import React, { useRef, useLayoutEffect, useState } from 'react';
import { Handle, Position } from '@xyflow/react';
import { CATEGORY_COLORS, getCategoryFromAction } from './nodeTypeMap.js';

/**
 * BaseNode — shared rendering logic for all Hecos Flow nodes.
 * Accepts:
 *   data.stepId, data.action, data.params, data.outputAs,
 *   data.execState ('running'|'done'|'error'|null)
 *   data.muted (bool)       — audio muted for this node
 *   data.audioPlaying (bool) — audio currently playing on this node
 *   customHandles           — array of { id, label, color } for multi-output nodes (e.g. if_else)
 */
export function BaseNode({
  data,
  selected,
  headerColor = '#0c4a6e',
  showInputHandle = true,
  showOutputHandle = true,
  showTrueOutput = false,
  showFalseOutput = false,
  customHandles = null,
  children,
}) {
  const cat = getCategoryFromAction(data.action);
  const catColor = CATEGORY_COLORS[cat] || { bg: '#1a1a1a', text: '#aaa' };
  const actionMethod = data.action?.split('__')[1] || data.action || '';

  // Params preview (first 2 entries)
  const paramEntries = Object.entries(data.params || {}).slice(0, 2);
  const paramPreview = paramEntries.map(([k, v]) => {
    const val = typeof v === 'object' ? JSON.stringify(v) : String(v);
    return `${k}: ${val.length > 20 ? val.slice(0, 20) + '…' : val}`;
  }).join('  ·  ');

  const stateClass = data.execState ? `state-${data.execState}` : '';
  const disableClass = data.disabled ? 'disabled' : '';

  // Audio controls — only shown on AUDIO__ and TTS__ nodes
  const actionUpper = (data.action || '').toUpperCase();
  const isAudioNode = actionUpper.startsWith('AUDIO__') ||
                      actionUpper.startsWith('TTS__') ||
                      actionUpper.startsWith('ALARM__');
  const isMuted = data.muted === true;
  const isAudioPlaying = data.audioPlaying === true;

  const handleToggleMute = (e) => {
    e.stopPropagation();
    e.preventDefault();
    window.dispatchEvent(new CustomEvent('hecos-node-toggle-mute', { detail: { id: data.stepId } }));
  };

  // For customHandles: measure pill row positions so handles align with pills
  const pillRefs = useRef([]);
  const nodeRef = useRef(null);
  const [handleTops, setHandleTops] = useState([]);

  useLayoutEffect(() => {
    if (!customHandles || !nodeRef.current) return;
    const nodeRect = nodeRef.current.getBoundingClientRect();
    if (nodeRect.height === 0) return;
    const tops = pillRefs.current.map(el => {
      if (!el) return 50;
      const rect = el.getBoundingClientRect();
      const relTop = rect.top - nodeRect.top + rect.height / 2;
      return Math.round((relTop / nodeRect.height) * 100);
    });
    // Only update if actually changed (avoid infinite loop)
    const hasChanged = tops.some((t, i) => t !== handleTops[i]);
    if (hasChanged) setHandleTops(tops);
  });

  return (
    <div
      ref={nodeRef}
      className={`hc-node ${stateClass} ${disableClass} ${selected ? 'selected' : ''}`}
      style={{ '--hc-header-color': headerColor }}
    >

      {data.disabled && (
        <div className="hc-node-bypass-overlay" title="Node Disabled / Bypassed">
          <i className="fas fa-times" />
        </div>
      )}

      {showInputHandle && (
        <Handle type="target" position={Position.Left} id="in"
          style={{ top: '50%' }} />
      )}

      {/* ── Header ── */}
      <div className="hc-node-header" style={{ background: headerColor }}>
        <span className="icon">{data.icon || '⚡'}</span>
        <span className="title" title={data.action}>{actionMethod}</span>
        <span className="badge" style={{ background: catColor.bg, color: catColor.text }}>
          {cat}
        </span>
      </div>

      {/* ── Body ── */}
      <div className="hc-node-body">
        <div className="step-id" title={data.stepId}>{data.stepId}</div>
        {paramPreview && <div className="param-preview">{paramPreview}</div>}
        {data.outputAs && (
          <div className="param-preview" style={{ color: 'rgba(0,212,255,0.5)', marginTop: 2 }}>
            → {data.outputAs}
          </div>
        )}
        {/* If customHandles are passed, render branch pills injecting refs for handle alignment */}
        {customHandles ? (
          <div style={{ marginTop: 6, display: 'flex', flexDirection: 'column', gap: 6 }}>
            {customHandles.map((h, i) => (
              <div
                key={h.id}
                ref={el => { pillRefs.current[i] = el; }}
                style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'flex-end',
                  paddingRight: 14, fontSize: '0.62rem',
                }}
              >
                <span style={{
                  color: h.color,
                  background: `${h.color}22`,
                  border: `1px solid ${h.color}55`,
                  borderRadius: 4,
                  padding: '2px 8px',
                  fontWeight: 700,
                  letterSpacing: '0.03em',
                  whiteSpace: 'nowrap',
                }}>{h.label}</span>
              </div>
            ))}
          </div>
        ) : (
          children
        )}
      </div>

      {/* ── Audio footer — only on AUDIO__ nodes ── */}
      {isAudioNode && (
        <div className="hc-node-audio-footer">
          <button
            className={`hc-node-mute-btn ${isMuted ? 'muted' : ''}`}
            onClick={handleToggleMute}
            title={isMuted ? 'Unmute audio for this node' : 'Mute audio for this node'}
          >
            <i className={`fas ${isMuted ? 'fa-volume-mute' : 'fa-volume-up'}`}></i>
            <span>{isMuted ? 'Muted' : 'Audio On'}</span>
          </button>

          {isAudioPlaying && (
            <div className="hc-audio-bars" title="Playing audio…">
              <div className="hc-audio-bar"></div>
              <div className="hc-audio-bar"></div>
              <div className="hc-audio-bar"></div>
              <div className="hc-audio-bar"></div>
            </div>
          )}
        </div>
      )}

      {/* ── Single output handle ── */}
      {showOutputHandle && !showTrueOutput && (
        <Handle type="source" position={Position.Right} id="out"
          style={{ top: '50%' }} />
      )}

      {/* ── Dual outputs for switch / and_gate / or_gate ── */}
      {showTrueOutput && (
        <Handle type="source" position={Position.Right} id="true"
          style={{ top: '33%', background: '#22c55e' }}
          title="True / Success" />
      )}
      {showFalseOutput && (
        <Handle type="source" position={Position.Right} id="false"
          style={{ top: '67%', background: '#ef4444' }}
          title="False / Fail" />
      )}

      {/* ── Custom multi-handles (if_else with N branches) ── */}
      {customHandles && customHandles.map((h, i) => (
        <Handle
          key={h.id}
          type="source"
          position={Position.Right}
          id={h.id}
          style={{
            top: handleTops[i] !== undefined && handleTops[i] > 0
              ? `${handleTops[i]}%`
              : `${(i + 1) * 100 / (customHandles.length + 1)}%`,
            background: h.color || '#fff',
            width: 10,
            height: 10,
          }}
          title={h.label}
        />
      ))}
    </div>
  );
}
