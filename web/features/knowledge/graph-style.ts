import type cytoscape from 'cytoscape';

export const GRAPH_STYLE: cytoscape.StylesheetStyle[] = [
  {
    selector: 'node',
    style: {
      label: 'data(label)',
      'font-size': 12,
      'text-valign': 'center',
      'text-halign': 'center',
      'text-wrap': 'wrap',
      'text-max-width': '120px',
      padding: '10px',
      shape: 'round-rectangle',
      'border-width': 1.5,
    },
  },
  {
    selector: 'node[type="chapter"]',
    style: {
      'background-color': '#12263a',
      color: '#f8fafc',
      'border-color': '#12263a',
      width: 'label',
      height: 'label',
    },
  },
  {
    selector: 'node[type="concept"]',
    style: {
      'background-color': '#fff7ed',
      color: '#7c2d12',
      'border-color': '#c2410c',
      width: 'label',
      height: 'label',
    },
  },
  {
    selector: 'node.selected',
    style: { 'border-width': 3, 'border-color': '#0f766e', 'background-color': '#ecfdf5' },
  },
  {
    selector: 'edge[kind="contains"]',
    style: {
      'line-style': 'solid',
      'line-color': '#94a3b8',
      'curve-style': 'bezier',
      width: 1.2,
      'target-arrow-shape': 'triangle',
      'target-arrow-color': '#94a3b8',
    },
  },
  {
    selector: 'edge[kind="precedes"]',
    style: {
      'line-color': '#1d4ed8',
      width: 2,
      'curve-style': 'bezier',
      'target-arrow-shape': 'triangle',
      'target-arrow-color': '#1d4ed8',
      label: 'data(label)',
      'font-size': 10,
      color: '#1d4ed8',
      'text-background-color': '#ffffff',
      'text-background-opacity': 0.9,
      'text-background-padding': '2px',
    },
  },
  {
    selector: 'edge[kind="contrasts"]',
    style: {
      'line-color': '#b45309',
      'line-style': 'dotted',
      width: 2,
      'curve-style': 'bezier',
      'target-arrow-shape': 'none',
      label: 'data(label)',
      'font-size': 10,
      color: '#b45309',
      'text-background-color': '#ffffff',
      'text-background-opacity': 0.9,
      'text-background-padding': '2px',
    },
  },
  {
    selector: 'edge[origin="suggested"]',
    style: { 'line-style': 'dashed' },
  },
];
