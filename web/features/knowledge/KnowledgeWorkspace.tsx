import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import cytoscape, { Core, ElementDefinition } from 'cytoscape';
import katex from 'katex';
import {
  ConceptDetail,
  KnowledgeSnapshot,
  MaterialDetail,
  ModelStatus,
  SourceDetail,
  Task,
  conceptUrl,
  knowledgeUrl,
  materialUrl,
  request,
  sourceUrl,
  tasksUrl,
} from '../../api';
import './knowledge.css';

const KIND_LABEL = { contains: '包含', precedes: '前置', contrasts: '对比' } as const;
const STATUS_LABEL: Record<Task['status'], string> = {
  queued: '等待执行',
  running: '整理中',
  completed: '已完成',
  failed: '失败',
};
const STEP_MARK: Record<Task['steps'][number]['status'], string> = {
  pending: '待处理',
  running: '进行中',
  completed: '完成',
  failed: '失败',
};

const GRAPH_STYLE: cytoscape.StylesheetStyle[] = [
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
      'target-arrow-shape': 'none',
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

function useRenderedMath(ref: React.RefObject<HTMLElement | null>, html: string | undefined) {
  useEffect(() => {
    ref.current?.querySelectorAll<HTMLElement>('[data-math]').forEach(element => {
      katex.render(element.dataset.math ?? '', element, {
        displayMode: element.dataset.display === 'true',
        throwOnError: false,
        trust: false,
        strict: 'ignore',
      });
    });
  }, [ref, html]);
}

function KnowledgeGraph({
  snapshot,
  selectedId,
  onSelectConcept,
}: {
  snapshot: KnowledgeSnapshot;
  selectedId: string | null;
  onSelectConcept: (id: string) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const instance = useRef<Core | null>(null);
  const select = useRef(onSelectConcept);
  select.current = onSelectConcept;

  useEffect(() => {
    if (!container.current) return;
    const elements: ElementDefinition[] = [
      ...snapshot.chapters.map(chapter => ({
        data: { id: `chapter:${chapter.id}`, label: chapter.title, type: 'chapter' },
      })),
      ...snapshot.concepts.map(concept => ({
        data: { id: `concept:${concept.id}`, label: concept.name, type: 'concept' },
      })),
      ...snapshot.relations.map(relation => ({
        data: {
          id: `relation:${relation.id}`,
          source: `${relation.from_type}:${relation.from_id}`,
          target: `${relation.to_type}:${relation.to_id}`,
          kind: relation.kind,
          origin: relation.origin,
          label: relation.kind === 'contains' ? '' : KIND_LABEL[relation.kind],
        },
      })),
    ];
    const cy = cytoscape({
      container: container.current,
      elements,
      style: GRAPH_STYLE,
      layout: {
        name: 'cose',
        animate: false,
        randomize: false,
        numIter: 1500,
        padding: 40,
        nodeDimensionsIncludeLabels: true,
        nodeOverlap: 16,
        componentSpacing: 50,
        nodeRepulsion: () => 11000,
        idealEdgeLength: () => 130,
        gravity: 0.4,
      },
      minZoom: 0.2,
      maxZoom: 2.5,
      wheelSensitivity: 0.2,
    });
    cy.on('tap', 'node[type="concept"]', event => {
      select.current(event.target.id().slice('concept:'.length));
    });
    instance.current = cy;
    return () => {
      cy.destroy();
      instance.current = null;
    };
  }, [snapshot]);

  useEffect(() => {
    const cy = instance.current;
    const element = container.current;
    if (!cy || !element || typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(() => {
      if (cy.destroyed()) return;
      cy.resize();
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [snapshot]);

  useEffect(() => {
    const cy = instance.current;
    if (!cy) return;
    cy.nodes().removeClass('selected');
    if (!selectedId) return;
    const node = cy.getElementById(`concept:${selectedId}`);
    if (node.nonempty()) node.addClass('selected');
  }, [selectedId, snapshot]);

  return <div className="graph-canvas" ref={container} role="img" aria-label="章节与知识点关系图" />;
}

function SourceDialog({ source, onClose }: { source: SourceDetail; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const content = useRef<HTMLDivElement>(null);
  useRenderedMath(content, source.html);
  useEffect(() => {
    dialog.current?.showModal();
  }, []);
  return (
    <dialog
      ref={dialog}
      className="source-dialog"
      onCancel={event => {
        event.preventDefault();
        onClose();
      }}
      onClick={event => {
        if (event.target === dialog.current) onClose();
      }}
    >
      <div className="modal-head">
        <div>
          <h2>原文依据</h2>
          <p className="source-meta">
            {source.filename}
            {source.chapter_title ? ` · ${source.chapter_title}` : ''} · 第 {source.start_line}—
            {source.end_line} 行
          </p>
        </div>
        <button className="icon-button" onClick={onClose} aria-label="关闭">
          ×
        </button>
      </div>
      <div ref={content} className="reading-content compact" dangerouslySetInnerHTML={{ __html: source.html }} />
      <details>
        <summary>查看原始 Markdown</summary>
        <pre className="source-original">{source.markdown}</pre>
      </details>
      <p className="form-help">内容直接来自已导入资料，未经模型改写。</p>
    </dialog>
  );
}

function ConceptPanel({
  concept,
  snapshot,
  onClose,
  onOpenSource,
  onSelectConcept,
}: {
  concept: ConceptDetail;
  snapshot: KnowledgeSnapshot;
  onClose: () => void;
  onOpenSource: (snippetId: string) => void;
  onSelectConcept: (id: string) => void;
}) {
  const page = useRef<HTMLDivElement>(null);
  useRenderedMath(page, concept.html);
  const names = useMemo(
    () => new Map(snapshot.concepts.map(item => [item.id, item.name])),
    [snapshot.concepts],
  );
  const chapters = snapshot.chapters.filter(chapter => concept.chapter_ids.includes(chapter.id));
  const relations = snapshot.relations.filter(
    relation => relation.kind !== 'contains' && (relation.from_id === concept.id || relation.to_id === concept.id),
  );

  function openInlineSource(event: React.MouseEvent<HTMLDivElement>) {
    const anchor = (event.target as HTMLElement).closest('a');
    const href = anchor?.getAttribute('href') ?? '';
    if (!href.startsWith('snippet:')) return;
    event.preventDefault();
    onOpenSource(href.slice('snippet:'.length));
  }

  return (
    <aside className="concept-panel" aria-label={`知识点：${concept.name}`}>
      <div className="concept-panel-head">
        <div>
          <div className="eyebrow">KNOWLEDGE POINT</div>
          <h2>{concept.name}</h2>
          {concept.aliases.length > 0 && <p className="aliases">别名：{concept.aliases.join('、')}</p>}
        </div>
        <button className="icon-button" onClick={onClose} aria-label="关闭知识点页面">
          ×
        </button>
      </div>
      <div className="concept-chapters">
        {chapters.map(chapter => (
          <span className="chip" key={chapter.id}>
            {chapter.title}
          </span>
        ))}
      </div>
      <p className="concept-definition">{concept.definition}</p>
      <div
        ref={page}
        className="concept-page"
        onClick={openInlineSource}
        dangerouslySetInnerHTML={{ __html: concept.html }}
      />
      <section className="concept-citations">
        <h3>资料依据</h3>
        {concept.citations.map(citation => (
          <button
            className="citation"
            key={`${citation.snippet_id}-${citation.start_line}`}
            onClick={() => onOpenSource(citation.snippet_id)}
          >
            <span className="citation-lines">
              {citation.chapter_title ?? citation.filename} · L{citation.start_line}–{citation.end_line}
            </span>
            <span className="citation-quote">{citation.quote}</span>
          </button>
        ))}
      </section>
      <section className="concept-relations">
        <h3>关系</h3>
        {relations.length === 0 && <p className="muted">当前版本没有与其他知识点的前置或对比关系。</p>}
        {relations.map(relation => {
          const outgoing = relation.from_id === concept.id;
          const other = outgoing ? relation.to_id : relation.from_id;
          return (
            <div className="relation-row" key={relation.id}>
              <span className={`relation-kind ${relation.kind}`}>{KIND_LABEL[relation.kind]}</span>
              <button className="link-button" onClick={() => onSelectConcept(other)}>
                {relation.kind === 'contrasts' ? '↔' : outgoing ? '→' : '←'} {names.get(other) ?? '未知知识点'}
              </button>
              <span className={`origin ${relation.origin}`}>
                {relation.origin === 'source' ? '资料依据' : '系统推断'}
              </span>
              <p>{relation.reason}</p>
            </div>
          );
        })}
      </section>
    </aside>
  );
}

function TaskPanel({ task, onRetry }: { task: Task; onRetry: () => void }) {
  return (
    <section className={`task-panel ${task.status}`} aria-live="polite">
      <div className="task-head">
        <div>
          <span className={`badge ${task.status}`}>{STATUS_LABEL[task.status]}</span>
          <strong>整理任务</strong>
          <span className="muted">
            {task.scope.chapters} 个章节 · {task.scope.fragments} 个片段 · {task.scope.characters.toLocaleString()} 字符
          </span>
        </div>
        {task.status === 'failed' && (
          <button className="secondary" onClick={onRetry}>
            重试
          </button>
        )}
      </div>
      <ol className="task-steps">
        {task.steps.map(step => (
          <li key={step.name} className={step.status}>
            <span className="step-dot" />
            <span>{step.label}</span>
            <small>
              {STEP_MARK[step.status]}
              {step.attempts > 1 ? ` · 第 ${step.attempts} 次` : ''}
            </small>
          </li>
        ))}
      </ol>
      {task.error_message && (
        <p className="task-error" role="alert">
          {task.error_message}
          {task.error_code ? `（${task.error_code}）` : ''}
        </p>
      )}
      {task.status === 'failed' && (
        <p className="form-help">失败不会发布知识；已完成的步骤会在重试时复用。</p>
      )}
    </section>
  );
}

export function KnowledgeWorkspace({ courseId }: { courseId: string }) {
  const [knowledge, setKnowledge] = useState<KnowledgeSnapshot | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [model, setModel] = useState<ModelStatus | null>(null);
  const [materials, setMaterials] = useState<MaterialDetail[]>([]);
  const [sources, setSources] = useState<string[]>([]);
  const [chapters, setChapters] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selected, setSelected] = useState<ConceptDetail | null>(null);
  const [source, setSource] = useState<SourceDetail | null>(null);
  const [sourceId, setSourceId] = useState<string | null>(null);
  const [error, setError] = useState('');

  const loadKnowledge = useCallback(async () => {
    const snapshot = await request<KnowledgeSnapshot>(knowledgeUrl(courseId));
    setKnowledge(snapshot);
    return snapshot;
  }, [courseId]);

  const loadTasks = useCallback(async () => {
    const items = await request<Task[]>(tasksUrl(courseId));
    setTasks(items);
    return items;
  }, [courseId]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setKnowledge(null);
    setTasks([]);
    setSelected(null);
    setSource(null);
    setSelectedId(null);
    setSources([]);
    setChapters([]);
    setError('');
    (async () => {
      const [snapshot, taskItems, status, list] = await Promise.all([
        request<KnowledgeSnapshot>(knowledgeUrl(courseId)),
        request<Task[]>(tasksUrl(courseId)),
        request<ModelStatus>('/api/model/status'),
        request<Array<{ id: string }>>(`/api/courses/${encodeURIComponent(courseId)}/materials`),
      ]);
      const details = await Promise.all(
        list.map(material => request<MaterialDetail>(materialUrl(courseId, material.id))),
      );
      if (cancelled) return;
      setKnowledge(snapshot);
      setTasks(taskItems);
      setModel(status);
      setMaterials(details);
    })()
      .catch(cause => {
        if (!cancelled) setError(cause instanceof Error ? cause.message : '无法读取课程知识。');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [courseId]);

  const activeTask = tasks.find(task => task.status === 'queued' || task.status === 'running');
  useEffect(() => {
    if (!activeTask) return;
    let cancelled = false;
    const timer = setInterval(async () => {
      try {
        const next = await request<Task[]>(tasksUrl(courseId));
        if (cancelled) return;
        setTasks(next);
        if (!next.some(task => task.status === 'queued' || task.status === 'running')) {
          await loadKnowledge();
        }
      } catch {
        // A transient read failure keeps the last visible state; the next poll retries.
      }
    }, 1500);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [activeTask?.id, courseId, loadKnowledge]);

  async function startBuild() {
    if (!sources.length && !chapters.length) {
      setError('请选择至少一份资料或一个章节。');
      return;
    }
    setCreating(true);
    setError('');
    try {
      const task = await request<Task>(tasksUrl(courseId), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ material_ids: sources, chapter_ids: chapters }),
      });
      setTasks(items => [task, ...items]);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '无法开始整理。');
    } finally {
      setCreating(false);
    }
  }

  async function retryTask(task: Task) {
    setError('');
    try {
      const next = await request<Task>(`${tasksUrl(courseId)}/${task.id}/retry`, { method: 'POST' });
      setTasks(items => items.map(item => (item.id === next.id ? next : item)));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '无法重试任务。');
    }
  }

  const versionId = knowledge?.version_id;
  useEffect(() => {
    setSelected(null);
    if (!selectedId || !versionId) return;
    const controller = new AbortController();
    request<ConceptDetail>(conceptUrl(courseId, versionId, selectedId), { signal: controller.signal })
      .then(detail => { if (!controller.signal.aborted) setSelected(detail); })
      .catch(cause => {
        if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : '无法读取知识点页面。');
      });
    return () => controller.abort();
  }, [courseId, versionId, selectedId]);

  function selectConcept(id: string) {
    setSourceId(null);
    setSelectedId(id);
  }

  useEffect(() => {
    setSource(null);
    if (!sourceId || !versionId) return;
    const controller = new AbortController();
    request<SourceDetail>(sourceUrl(courseId, versionId, sourceId), { signal: controller.signal })
      .then(detail => { if (!controller.signal.aborted) setSource(detail); })
      .catch(cause => {
        if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : '无法读取原文片段。');
      });
    return () => controller.abort();
  }, [courseId, versionId, sourceId]);

  function openSource(snippetId: string) {
    setSourceId(snippetId);
  }

  function toggleMaterial(material: MaterialDetail) {
    setSources(current =>
      current.includes(material.id) ? current.filter(id => id !== material.id) : [...current, material.id],
    );
    setChapters(current => current.filter(id => !material.chapters.some(chapter => chapter.id === id)));
  }

  function toggleChapter(materialId: string, chapterId: string) {
    setChapters(current =>
      current.includes(chapterId) ? current.filter(id => id !== chapterId) : [...current, chapterId],
    );
    setSources(current => current.filter(id => id !== materialId));
  }

  const organized = useMemo(
    () => new Set((knowledge?.chapters ?? []).map(chapter => chapter.id)),
    [knowledge],
  );
  const latest = tasks[0];
  const published = knowledge?.state === 'published';

  if (loading) {
    return <div className="empty-state" role="status">正在读取课程知识…</div>;
  }

  return (
    <div className="knowledge-workspace">
      {error && (
        <div className="message error" role="alert">
          <span>{error}</span>
          <button onClick={() => setError('')} aria-label="关闭错误提示">×</button>
        </div>
      )}
      {model && !model.configured && (
        <div className="message warning" role="status">
          {model.message}
        </div>
      )}

      {latest && <TaskPanel task={latest} onRetry={() => void retryTask(latest)} />}

      {!published ? (
        <section className="unpublished">
          <div className="empty-state">
            <div className="eyebrow">NOT ORGANIZED YET</div>
            <h2>尚未整理成课程知识</h2>
            <p>选择一小节资料发起整理。只有通过来源与结构校验的版本才会发布；失败时不会产生可用知识。</p>
          </div>
          <div className="scope-picker">
            <div className="section-bar">
              <h2>整理范围</h2>
              <span>资料按章节选择 · 单次上限 60,000 字符</span>
            </div>
            {materials.length === 0 && <p className="muted">这门课程还没有资料，请先在「资料阅读」中导入 Markdown。</p>}
            {materials.map(material => (
              <div className="scope-material" key={material.id}>
                <label className="check-row">
                  <input
                    type="checkbox"
                    checked={sources.includes(material.id)}
                    onChange={() => toggleMaterial(material)}
                  />
                  <span>{material.filename}</span>
                  <small>{material.chapters.length} 个章节</small>
                </label>
                <div className="chapter-chips">
                  {material.chapters.map(chapter => (
                    <button
                      key={chapter.id}
                      className={`chip-toggle ${chapters.includes(chapter.id) ? 'on' : ''} ${
                        organized.has(chapter.id) ? 'organized' : ''
                      }`}
                      onClick={() => toggleChapter(material.id, chapter.id)}
                      disabled={sources.includes(material.id)}
                    >
                      {chapter.title}
                    </button>
                  ))}
                </div>
              </div>
            ))}
            <div className="scope-actions">
              <span className="muted">
                已选择 {sources.length} 份资料、{chapters.length} 个章节
              </span>
              <button
                className="primary"
                onClick={() => void startBuild()}
                disabled={creating || Boolean(activeTask) || !model?.configured}
              >
                {creating ? '正在创建任务…' : '开始整理'}
              </button>
            </div>
            {!model?.configured && <p className="form-help">配置后端模型凭据后才能开始整理。</p>}
          </div>
        </section>
      ) : (
        <div className="knowledge-body">
          <div className="graph-panel">
            <div className="graph-toolbar">
              <div>
                <span className="badge published">已发布</span>
                <span className="muted">版本 {knowledge?.version_id?.slice(0, 8)}</span>
                <span className="muted">
                  {knowledge?.concepts.length} 个知识点 · {knowledge?.relations.length} 条关系
                </span>
              </div>
              <span className="muted">当前展示首次整理的知识</span>
            </div>
            {knowledge && (
              <KnowledgeGraph
                snapshot={knowledge}
                selectedId={selectedId}
                onSelectConcept={id => void selectConcept(id)}
              />
            )}
            <div className="concept-list" aria-label="知识点列表">
              <span className="pane-label">知识点</span>
              <div className="concept-chips">
                {knowledge?.concepts.map(concept => (
                  <button
                    key={concept.id}
                    className={`chip-toggle ${selectedId === concept.id ? 'on' : ''}`}
                    onClick={() => void selectConcept(concept.id)}
                  >
                    {concept.name}
                  </button>
                ))}
              </div>
            </div>
            <div className="graph-legend">
              <span><i className="dot chapter" />章节</span>
              <span><i className="dot concept" />知识点</span>
              <span><i className="line contains" />包含</span>
              <span><i className="line precedes" />前置（有方向）</span>
              <span><i className="line contrasts" />对比（无先后）</span>
              <span><i className="line suggested" />虚线 = 系统推断</span>
            </div>
          </div>
          {selected && knowledge && (
            <ConceptPanel
              concept={selected}
              snapshot={knowledge}
              onClose={() => {
                setSourceId(null);
                setSelected(null);
                setSelectedId(null);
              }}
              onOpenSource={snippetId => void openSource(snippetId)}
              onSelectConcept={id => void selectConcept(id)}
            />
          )}
        </div>
      )}

      {source && <SourceDialog source={source} onClose={() => setSourceId(null)} />}
    </div>
  );
}
