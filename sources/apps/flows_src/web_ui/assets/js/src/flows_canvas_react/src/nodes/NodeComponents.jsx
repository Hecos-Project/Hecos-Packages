import React from 'react';
import { BaseNode } from './BaseNode.jsx';

export function ActionNode({ data, selected }) {
  return (
    <BaseNode
      data={data}
      selected={selected}
      headerColor="#0c4a6e"
      showInputHandle={true}
      showOutputHandle={true}
    />
  );
}

export function TriggerNode({ data, selected }) {
  return (
    <BaseNode
      data={data}
      selected={selected}
      headerColor="#3b0764"
      showInputHandle={false}
      showOutputHandle={true}
    />
  );
}

export function LogicNode({ data, selected }) {
  const method = data.action?.split('__')[1] || '';
  
  if (method === 'if_else') {
    const branches = Array.isArray(data.params?.branches) ? data.params.branches : [];
    let customHandles = [];
    if (branches.length > 0) {
      customHandles = branches.map((_, i) => ({
        id: `branch_${i}`,
        label: i === 0 ? 'If' : `Elif ${i}`,
        color: '#22c55e'
      }));
      customHandles.push({ id: 'false', label: 'Else', color: '#ef4444' });
    } else {
      // Legacy: old schema with condition string
      customHandles = [
        { id: 'true', label: 'True', color: '#22c55e' },
        { id: 'false', label: 'False', color: '#ef4444' }
      ];
    }

    return (
      <BaseNode
        data={data}
        selected={selected}
        headerColor="#78350f"
        showInputHandle={true}
        showOutputHandle={false}
        customHandles={customHandles}
      />
    );
  }

  const hasBranches = ['switch', 'and_gate', 'or_gate'].includes(method);
  return (
    <BaseNode
      data={data}
      selected={selected}
      headerColor="#78350f"
      showInputHandle={true}
      showOutputHandle={!hasBranches}
      showTrueOutput={hasBranches}
      showFalseOutput={hasBranches}
    />
  );
}

export function AINode({ data, selected }) {
  const promptPreview = data.params?.prompt
    ? String(data.params.prompt).slice(0, 40) + (data.params.prompt.length > 40 ? '…' : '')
    : null;
  return (
    <BaseNode
      data={{ ...data, icon: '🧠' }}
      selected={selected}
      headerColor="#581c87"
      showInputHandle={true}
      showOutputHandle={true}
    >
      {promptPreview && (
        <div style={{
          marginTop: 4,
          padding: '4px 6px',
          background: 'rgba(192,38,211,0.1)',
          borderRadius: 4,
          fontSize: '0.62rem',
          color: 'rgba(232,121,249,0.8)',
          fontStyle: 'italic',
        }}>
          "{promptPreview}"
        </div>
      )}
    </BaseNode>
  );
}

export function HttpNode({ data, selected }) {
  const method = data.params?.method || 'GET';
  const url = data.params?.url ? String(data.params.url).slice(0, 30) : '';
  return (
    <BaseNode
      data={{ ...data, icon: '🌐' }}
      selected={selected}
      headerColor="#134e4a"
      showInputHandle={true}
      showOutputHandle={true}
    >
      {(method || url) && (
        <div style={{
          marginTop: 4,
          display: 'flex',
          gap: 6,
          alignItems: 'center',
          fontSize: '0.62rem',
        }}>
          <span style={{
            background: '#0e7490', color: '#fff',
            borderRadius: 3, padding: '1px 5px', fontWeight: 700, fontSize: '0.58rem',
          }}>{method}</span>
          <span style={{ color: 'rgba(20,184,166,0.7)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {url}
          </span>
        </div>
      )}
    </BaseNode>
  );
}

export function DelayNode({ data, selected }) {
  const secs = data.params?.seconds ?? '';
  return (
    <BaseNode
      data={{ ...data, icon: '⏱️' }}
      selected={selected}
      headerColor="#1e1b4b"
      showInputHandle={true}
      showOutputHandle={true}
    >
      {secs !== '' && (
        <div style={{ marginTop: 4, color: 'rgba(129,140,248,0.8)', fontSize: '0.68rem', fontWeight: 600 }}>
          {secs}s
        </div>
      )}
    </BaseNode>
  );
}

export function VarNode({ data, selected }) {
  return (
    <BaseNode
      data={{ ...data, icon: '📌' }}
      selected={selected}
      headerColor="#14532d"
      showInputHandle={true}
      showOutputHandle={true}
    />
  );
}
