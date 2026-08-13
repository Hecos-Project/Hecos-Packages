import React from 'react';
import { Handle, Position } from '@xyflow/react';

export default function GroupNode({ data, selected }) {
  const isCollapsed = data.collapsed !== false;
  const childCount = Array.isArray(data.children) ? data.children.length : 0;
  const label = data.label || 'Group';
  const color = data.color || '#0ea5e9'; // Default cyan-ish

  return (
    <div className={`hc-group-node ${selected ? 'selected' : ''}`} style={{ '--group-color': color }}>
      <Handle type="target" position={Position.Left} className="hc-handle in" />
      
      <div className="hc-group-header">
        <div className="hc-group-icon" style={{ backgroundColor: color }}>
          <i className="fas fa-layer-group"></i>
        </div>
        <div className="hc-group-title">{label}</div>
        
        <button 
          className="hc-group-toggle" 
          onClick={(e) => {
            e.stopPropagation();
            if (window.toggleGroup) window.toggleGroup(data.id);
            else if (data.onToggle) data.onToggle(data.id);
          }}
          title={isCollapsed ? "Expand Group" : "Collapse Group"}
        >
          <i className={`fas fa-chevron-${isCollapsed ? 'down' : 'up'}`}></i>
        </button>
      </div>

      {isCollapsed && (
        <div className="hc-group-body">
          <div className="hc-group-count">
            <i className="fas fa-cubes"></i> {childCount} node{childCount !== 1 ? 's' : ''}
          </div>
        </div>
      )}
      
      <Handle type="source" position={Position.Right} className="hc-handle out" />
    </div>
  );
}
