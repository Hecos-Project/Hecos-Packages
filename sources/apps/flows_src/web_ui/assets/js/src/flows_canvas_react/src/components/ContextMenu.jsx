import React, { useEffect, useRef } from 'react';

export default function ContextMenu({ menu, onClose, onAction }) {
  const ref = useRef(null);

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (ref.current && !ref.current.contains(e.target)) {
        onClose();
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [onClose]);

  if (!menu) return null;

  return (
    <div
      ref={ref}
      style={{
        position: 'absolute',
        top: menu.top,
        left: menu.left,
        zIndex: 1000,
        backgroundColor: 'rgba(8,15,28,0.98)',
        border: '1px solid rgba(0,212,255,0.18)',
        borderRadius: '8px',
        boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
        backdropFilter: 'blur(12px)',
        minWidth: '150px',
        padding: '5px 0',
        fontFamily: 'Inter, sans-serif'
      }}
      // Stop context menu propagation on the menu itself
      onContextMenu={(e) => { e.preventDefault(); e.stopPropagation(); }}
    >
      {menu.type === 'node' && menu.node?.type !== 'groupNode' && (
        <React.Fragment>
          <div className="hc-cm-item" onClick={() => onAction('EDIT', menu.node)}>
            <i className="fas fa-edit" style={{ width: '20px', color: '#00d4ff' }} /> Edit Node
          </div>
          <div className="hc-cm-item" onClick={() => onAction('TOGGLE_DISABLE', menu.node)}>
            {menu.node?.data?.disabled ? (
              <><i className="fas fa-play" style={{ width: '20px', color: '#22c55e' }} /> Enable Node</>
            ) : (
              <><i className="fas fa-ban" style={{ width: '20px', color: '#ef4444' }} /> Disable Node</>
            )}
          </div>
          <div className="hc-cm-item" onClick={() => onAction('DUPLICATE', menu.node)}>
            <i className="fas fa-copy" style={{ width: '20px', color: '#b45309' }} /> Duplicate
          </div>
          {(menu.selectedCount >= 2) && (
            <>
              <div className="hc-separator" style={{ height: '1px', background: 'rgba(255,255,255,0.1)', margin: '4px 0' }} />
              <div className="hc-cm-item" onClick={() => onAction('GROUP_SELECTED')}>
                <i className="fas fa-object-group" style={{ width: '20px', color: '#0ea5e9' }} /> Group Selected ({menu.selectedCount})
              </div>
            </>
          )}
          <div className="hc-separator" style={{ height: '1px', background: 'rgba(255,255,255,0.1)', margin: '4px 0' }} />
          <div className="hc-cm-item" onClick={() => onAction('DELETE', menu.node)}>
            <i className="fas fa-trash" style={{ width: '20px', color: '#ef4444' }} /> Delete
          </div>
        </React.Fragment>
      )}

      {menu.type === 'node' && menu.node?.type === 'groupNode' && (
        <React.Fragment>
          <div className="hc-cm-item" onClick={() => onAction('TOGGLE_GROUP', menu.node)}>
            {menu.node?.data?.collapsed === false ? (
               <><i className="fas fa-compress-arrows-alt" style={{ width: '20px', color: '#0ea5e9' }} /> Collapse Group</>
            ) : (
               <><i className="fas fa-expand-arrows-alt" style={{ width: '20px', color: '#0ea5e9' }} /> Expand Group</>
            )}
          </div>
          <div className="hc-cm-item" onClick={() => onAction('UNGROUP', menu.node)}>
            <i className="fas fa-object-ungroup" style={{ width: '20px', color: '#f59e0b' }} /> Ungroup
          </div>
          <div className="hc-separator" style={{ height: '1px', background: 'rgba(255,255,255,0.1)', margin: '4px 0' }} />
          <div className="hc-cm-item" onClick={() => onAction('DELETE', menu.node)}>
            <i className="fas fa-trash" style={{ width: '20px', color: '#ef4444' }} /> Delete Group
          </div>
        </React.Fragment>
      )}

      {menu.type === 'pane' && (
        <React.Fragment>
          <div className="hc-cm-item" onClick={() => onAction('SHOW_PALETTE')}>
            <i className="fas fa-toolbox" style={{ width: '20px', color: '#00d4ff' }} /> Show Palette
          </div>
          <div className="hc-cm-item" onClick={() => onAction('NEW_NODE', menu)}>
            <i className="fas fa-plus-circle" style={{ width: '20px', color: '#22c55e' }} /> Quick Add
          </div>
          <div className="hc-separator" style={{ height: '1px', background: 'rgba(255,255,255,0.1)', margin: '4px 0' }} />
          <div className="hc-cm-item" onClick={() => onAction('ADD_AREA', menu)}>
            <i className="fas fa-layer-group" style={{ width: '20px', color: '#c026d3' }} /> Add Area
          </div>
          {(menu.selectedCount >= 2) && (
            <div className="hc-cm-item" onClick={() => onAction('GROUP_SELECTED')}>
              <i className="fas fa-object-group" style={{ width: '20px', color: '#0ea5e9' }} /> Group Selected ({menu.selectedCount})
            </div>
          )}
          <div className="hc-separator" style={{ height: '1px', background: 'rgba(255,255,255,0.1)', margin: '4px 0' }} />
          <div className="hc-cm-item" onClick={() => onAction('REARRANGE_NODES')}>
            <i className="fas fa-th" style={{ width: '20px', color: '#f59e0b' }} /> Rearrange Nodes
          </div>
        </React.Fragment>
      )}

      {menu.type === 'edge' && (
        <React.Fragment>
          <div className="hc-cm-item" onClick={() => onAction('DELETE_EDGE', menu.edge)}>
            <i className="fas fa-unlink" style={{ width: '20px', color: '#ef4444' }} /> Delete Connection
          </div>
        </React.Fragment>
      )}
    </div>
  );
}
