import { useEffect, useMemo, useRef, useState } from 'react';
import cytoscape, { type Core, type ElementDefinition, type Position } from 'cytoscape';
import { type KnowledgeConcept, type KnowledgeSnapshot } from '../../api';
import { GRAPH_STYLE } from './graph-style';

const KIND_LABEL = { contains: '包含', precedes: '前置', contrasts: '对比' } as const;
const MODES = { chapters: '章节概览', cross: '跨章节关联', full: '全图' } as const;
type Mode = keyof typeof MODES;
type Viewport = { zoom: number; pan: Position; positions: Map<string, Position> };

function conceptLabel(concept: KnowledgeConcept) {
  return concept.name + (concept.status === 'needs_review' ? ' · 待核对' : '')
    + (concept.conflicts?.length ? ' · 有冲突' : '');
}

/** Own graph views and their viewport state without changing knowledge identities. */
export function GraphExplorer({ snapshot, selectedId, onSelectConcept }: {
  snapshot: KnowledgeSnapshot;
  selectedId: string | null;
  onSelectConcept: (id: string) => void;
}) {
  const [mode, setMode] = useState<Mode>('chapters');
  const [expanded, setExpanded] = useState<string[]>([]);
  const [zoom, setZoom] = useState(100);
  const container = useRef<HTMLDivElement>(null);
  const instance = useRef<Core | null>(null);
  const viewports = useRef(new Map<string, Viewport>());
  const select = useRef(onSelectConcept);
  select.current = onSelectConcept;

  const chapterConcepts = useMemo(() => new Map(snapshot.chapters.map(chapter => {
    const descendants = new Set(snapshot.chapters.filter(item => item.material_id === chapter.material_id
      && chapter.start_line <= item.start_line && item.end_line <= chapter.end_line).map(item => item.id));
    return [chapter.id, snapshot.concepts.filter(concept => concept.chapter_ids.some(id => descendants.has(id)))];
  })), [snapshot]);

  const crossRelations = useMemo(() => {
    const concepts = new Map(snapshot.concepts.map(concept => [concept.id, concept]));
    return snapshot.relations.filter(relation => {
      if (relation.kind === 'contains') return false;
      const from = concepts.get(relation.from_id);
      const to = concepts.get(relation.to_id);
      return from?.chapter_ids.some(a => to?.chapter_ids.some(b => a !== b));
    });
  }, [snapshot]);

  const visible = useMemo(() => {
    if (mode === 'full') return snapshot.concepts;
    const ids = mode === 'cross'
      ? new Set([...snapshot.concepts.filter(concept => concept.chapter_ids.length > 1).map(concept => concept.id),
        ...crossRelations.flatMap(relation => [relation.from_id, relation.to_id])])
      : new Set(expanded.flatMap(chapterId => (chapterConcepts.get(chapterId) ?? []).map(concept => concept.id)));
    return snapshot.concepts.filter(concept => ids.has(concept.id));
  }, [snapshot, mode, expanded, chapterConcepts, crossRelations]);

  const relations = useMemo(() => {
    const ids = new Set(visible.map(concept => concept.id));
    return snapshot.relations.filter(relation => relation.kind === 'contains'
      ? ids.has(relation.to_id)
      : ids.has(relation.from_id) && ids.has(relation.to_id)
        && (mode !== 'cross' || crossRelations.includes(relation)));
  }, [snapshot, visible, mode, crossRelations]);

  const allElements = useMemo<ElementDefinition[]>(() => [
    ...snapshot.chapters.map(chapter => ({ data: {
      id: `chapter:${chapter.id}`, label: chapter.title, type: 'chapter',
    } })),
    ...snapshot.concepts.map(concept => ({ data: {
      id: `concept:${concept.id}`, label: conceptLabel(concept), type: 'concept',
    } })),
    ...snapshot.relations.map(relation => ({ data: {
      id: `relation:${relation.id}`, source: `${relation.from_type}:${relation.from_id}`,
      target: `${relation.to_type}:${relation.to_id}`, kind: relation.kind, origin: relation.origin,
      label: relation.kind === 'contains' ? '' : KIND_LABEL[relation.kind],
    } })),
  ], [snapshot]);
  const visibleIds = useMemo(() => new Set([
    ...snapshot.chapters.map(chapter => `chapter:${chapter.id}`),
    ...visible.map(concept => `concept:${concept.id}`),
    ...relations.map(relation => `relation:${relation.id}`),
  ]), [snapshot, visible, relations]);
  const viewKey = mode + (mode === 'chapters' ? ':' + [...expanded].sort().join(',') : '');

  function toggleChapter(id: string) {
    setMode('chapters');
    setExpanded(current => current.includes(id)
      ? mode === 'chapters' ? current.filter(item => item !== id) : current
      : [...current, id]);
  }
  const toggle = useRef(toggleChapter);
  toggle.current = toggleChapter;

  useEffect(() => {
    if (!container.current) return;
    const cy = cytoscape({
      container: container.current, style: GRAPH_STYLE, elements: allElements,
      layout: { name: 'preset', fit: false },
      minZoom: 0.1, maxZoom: 2.5, wheelSensitivity: 0.2, autounselectify: true,
    });
    cy.on('zoom', () => setZoom(Math.round(cy.zoom() * 100)));
    cy.on('tap', 'node[type="concept"]', event => select.current(event.target.id().slice('concept:'.length)));
    cy.on('tap', 'node[type="chapter"]', event => toggle.current(event.target.id().slice('chapter:'.length)));
    const observer = new ResizeObserver(() => { if (!cy.destroyed()) cy.resize(); });
    observer.observe(container.current);
    instance.current = cy;
    return () => {
      observer.disconnect();
      cy.destroy();
      instance.current = null;
    };
  }, [allElements]);

  useEffect(() => {
    const cy = instance.current;
    if (!cy) return;
    const saved = viewports.current.get(viewKey);
    // Keep the elements alive: restoring newly inserted nodes with label-sized
    // geometry can leave stale drawing bounds in the renderer.
    const shown = cy.elements().filter(element => visibleIds.has(element.id()));
    cy.batch(() => {
      cy.elements().difference(shown).style('display', 'none');
      shown.style('display', 'element');
    });
    shown.layout(saved ? {
      name: 'preset', fit: false,
      positions: Object.fromEntries(saved.positions),
    } : {
      name: 'cose', animate: false, randomize: false, numIter: 1500, padding: 40,
      nodeDimensionsIncludeLabels: true, nodeOverlap: 16, componentSpacing: 50,
      nodeRepulsion: () => 11000, idealEdgeLength: () => 130, gravity: 0.4,
    }).run();
    if (saved) cy.viewport({ zoom: saved.zoom, pan: saved.pan });
    setZoom(Math.round(cy.zoom() * 100));
    return () => {
      if (cy.destroyed()) return;
      viewports.current.set(viewKey, {
        zoom: cy.zoom(), pan: { ...cy.pan() },
        positions: new Map(cy.nodes().map(node => [node.id(), { ...node.position() }])),
      });
    };
  }, [allElements, visibleIds, viewKey]);

  useEffect(() => {
    const cy = instance.current;
    if (!cy) return;
    cy.nodes().removeClass('selected');
    if (selectedId) cy.getElementById(`concept:${selectedId}`).addClass('selected');
  }, [selectedId, allElements, visibleIds]);

  function changeZoom(factor: number) {
    const cy = instance.current;
    if (cy) cy.zoom({ level: cy.zoom() * factor, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } });
  }
  const names = new Map([...snapshot.chapters, ...snapshot.concepts].map(item => [item.id, 'name' in item ? item.name : item.title]));

  return <>
    <nav className="graph-views" aria-label="图谱视图">
      {(Object.keys(MODES) as Mode[]).map(value => <button key={value} aria-pressed={mode === value}
        className={mode === value ? 'active' : ''} onClick={() => setMode(value)}>{MODES[value]}</button>)}
      <div className="graph-zoom">
        <button aria-label="缩小图谱" onClick={() => changeZoom(1 / 1.2)}>−</button>
        <output aria-label="图谱缩放">{zoom}%</output>
        <button aria-label="放大图谱" onClick={() => changeZoom(1.2)}>＋</button>
        <button onClick={() => instance.current?.fit(undefined, 40)}>适应画布</button>
      </div>
    </nav>
    <div className="chapter-overview" aria-label="章节概览列表">
      {snapshot.chapters.map(chapter => <button key={chapter.id} aria-expanded={mode === 'chapters' && expanded.includes(chapter.id)}
        aria-label={`${expanded.includes(chapter.id) && mode === 'chapters' ? '收起' : '展开'} ${chapter.title}`}
        onClick={() => toggleChapter(chapter.id)}>
        <span>{chapter.title}</span><small>{chapterConcepts.get(chapter.id)?.length ?? 0} 个知识点 · 含下级章节</small>
      </button>)}
    </div>
    <p className="graph-view-help">{mode === 'chapters' ? '点击章节展开或收起知识点；同一知识点跨章节共用一个节点。'
      : mode === 'cross' ? '展示多章节共有知识点，以及连接不同章节知识点的前置和对比关系。'
        : '展示当前已发布范围的全部章节、知识点与关系。'}</p>
    <div className="graph-canvas" ref={container} role="img" aria-label="章节与知识点关系图" />
    <div className="concept-list" aria-label="知识点列表">
      <span className="pane-label">知识点</span><div className="concept-chips">
        {visible.length === 0 && <span className="muted">{mode === 'chapters' ? '展开章节后显示知识点' : '当前版本没有可显示的跨章节知识'}</span>}
        {visible.map(concept => <button key={concept.id} className={`chip-toggle ${selectedId === concept.id ? 'on' : ''}`}
          title={concept.chapter_ids.length > 1 ? '此知识点关联多个章节' : undefined}
          onClick={() => onSelectConcept(concept.id)}>{conceptLabel(concept)}</button>)}
      </div>
    </div>
    <div className="graph-legend">
      <span><i className="dot chapter" />章节</span><span><i className="dot concept" />知识点</span>
      <span><i className="line contains" />包含（章节 → 知识点）</span>
      <span><i className="line precedes" />前置（有方向）</span>
      <span><i className="line contrasts" />对比（无先后）</span>
      <span><i className="line suggested" />虚线 = 系统推断</span>
    </div>
    <details className="visible-relations">
      <summary>当前视图的关系 · {relations.length} 条</summary>
      {relations.map(relation => <div className="relation-row" key={relation.id}>
        <span className={`relation-kind ${relation.kind}`}>{KIND_LABEL[relation.kind]}</span>
        <span>{names.get(relation.from_id)} {relation.kind === 'contrasts' ? '↔' : '→'} {names.get(relation.to_id)}</span>
        <span className={`origin ${relation.origin}`}>{relation.origin === 'source' ? '资料依据' : '系统推断'}</span>
        <p>{relation.reason}</p>
      </div>)}
    </details>
  </>;
}
