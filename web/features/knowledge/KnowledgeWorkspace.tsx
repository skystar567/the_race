import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { GraphExplorer } from './GraphExplorer';
import { CoveragePanel } from './CoveragePanel';
import { ScopePicker } from './ScopePicker';
import { coverageUrl, type KnowledgeCoverage } from './coverage-api';
import katex from 'katex';
import {
  ConceptDetail,
  KnowledgeSnapshot,
  ModelStatus,
  SourceDetail,
  Task,
  conceptUrl,
  knowledgeUrl,
  request,
  sourceUrl,
  tasksUrl,
} from '../../api';
import './knowledge.css';
import { QuestionPanel } from '../questions/QuestionPanel';
import { ConceptStudyActions } from '../notes/ConceptStudyActions';

const KIND_LABEL = { contains: '包含', precedes: '前置', contrasts: '对比' } as const;
const STATUS_LABEL: Record<Task['status'], string> = {
  queued: '等待执行',
  running: '整理中',
  completed: '已完成',
  failed: '失败',
};
const RECOVERY_LABEL: Record<Task['status'], string> = {
  queued: '等待继续执行。',
  running: '继续未完成步骤。',
  completed: '任务已完成。',
  failed: '恢复后仍未完成，请查看失败原因后重试。',
};
const STEP_MARK: Record<Task['steps'][number]['status'], string> = {
  pending: '待处理',
  running: '进行中',
  completed: '完成',
  failed: '失败',
};

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
  courseId, modelConfigured, onAsk, onOpenNotes,
}: {
  courseId: string; modelConfigured: boolean; onAsk: () => void; onOpenNotes: (id: string) => void;
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
  const conflicts = concept.conflicts ?? [];
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
      <ConceptStudyActions key={`${concept.version_id}:${concept.id}`} courseId={courseId} conceptId={concept.id} versionId={concept.version_id}
        modelConfigured={modelConfigured} onAsk={onAsk} onOpenNotes={onOpenNotes} />
      <div className="concept-chapters">
        {chapters.map(chapter => (
          <span className="chip" key={chapter.id}>
            {chapter.title}
          </span>
        ))}
      </div>
      {concept.status === 'needs_review' && <p className="identity-review" role="note">待核对：{concept.identity_reason ?? '尚不能确认概念身份，暂时独立保留。'}</p>}
      {concept.is_updated && <p className="concept-change">本次资料补充了此知识点，原有身份与出处已保留。</p>}
      {conflicts.length > 0 && <section className="concept-conflicts" aria-label="资料冲突">
        <h3>资料冲突 · {conflicts.length}</h3>
        <p className="conflict-help">以下资料存在不相容的表述。各方依据均已保留，请结合语境查看原文。</p>
        {conflicts.map(conflict => <article className="conflict-card" key={conflict.id}>
          <p className="conflict-reason">{conflict.reason}</p>
          {conflict.claims.map((claim, index) => {
            const source = concept.citations.find(citation => citation.snippet_id === claim.citation.snippet_id);
            return <div className="conflict-claim" key={`${claim.citation.snippet_id}-${index}`}>
              <h4>表述 {index + 1}</h4>
              <p>{claim.statement}</p>
              <p className="conflict-context">适用语境：{claim.context}</p>
              <blockquote>{claim.citation.quote}</blockquote>
              <button className="conflict-source" onClick={() => onOpenSource(claim.citation.snippet_id)}>
                查看表述 {index + 1} 原文
                {source && <small>{source.filename} · L{source.start_line}–{source.end_line}</small>}
              </button>
            </div>;
          })}
        </article>)}
      </section>}
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

function TaskPanel({ task, onRetry, busy }: { task: Task; onRetry: () => void; busy: boolean }) {
  return (
    <section className={`task-panel ${task.status}`} aria-live="polite">
      <div className="task-head">
        <div>
          <span className={`badge ${task.status}`}>{STATUS_LABEL[task.status]}</span>
          <strong>{task.parent_version_id ? '追加整理任务' : '整理任务'}</strong>
          <span className="muted">
            {task.scope.chapters} 个章节 · {task.scope.fragments} 个片段 · {task.scope.characters.toLocaleString()} 字符
          </span>
        </div>
        {task.status === 'failed' && (
          <button className="secondary" onClick={onRetry} disabled={busy}>
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
      {(task.recovery_count ?? 0) > 0 && <p className="task-recovery" role="status">
        已恢复 {task.recovery_count} 次，{RECOVERY_LABEL[task.status]}
      </p>}
      {task.error_message && (
        <p className="task-error" role="alert">
          {task.error_message}
          {task.error_code ? `（${task.error_code}）` : ''}
        </p>
      )}
      {task.status === 'failed' && (
        <p className="form-help">{task.parent_version_id ? '更新失败，原有知识仍可阅读；已完成步骤会在重试时复用。' : '失败不会发布知识；已完成的步骤会在重试时复用。'}</p>
      )}
    </section>
  );
}

export function KnowledgeWorkspace({ courseId, onOpenNotes }: { courseId: string; onOpenNotes: (id: string) => void }) {
  const [asking, setAsking] = useState(false);
  const [focus, setFocus] = useState<{ id: string; name: string } | null>(null);
  const [knowledge, setKnowledge] = useState<KnowledgeSnapshot | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [model, setModel] = useState<ModelStatus | null>(null);
  const [coverage, setCoverage] = useState<KnowledgeCoverage | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const displayedVersion = useRef<string | null>(null);
  const refreshController = useRef<AbortController | null>(null);
  const mutationController = useRef<AbortController | null>(null);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selected, setSelected] = useState<ConceptDetail | null>(null);
  const [source, setSource] = useState<SourceDetail | null>(null);
  const [sourceId, setSourceId] = useState<string | null>(null);
  const [error, setError] = useState('');

  const readPublished = useCallback(async (signal: AbortSignal) => {
    let snapshot = await request<KnowledgeSnapshot>(knowledgeUrl(courseId), { signal });
    const coverage = await request<KnowledgeCoverage>(coverageUrl(courseId, snapshot.version_id), { signal });
    // A first publication can occur between the two reads; null cannot pin a version.
    if (!snapshot.version_id && coverage.version_id) {
      snapshot = await request<KnowledgeSnapshot>(knowledgeUrl(courseId) + `?version_id=${encodeURIComponent(coverage.version_id)}`, { signal });
    }
    return { snapshot, coverage };
  }, [courseId]);

  const applyPublished = useCallback(({ snapshot, coverage }: { snapshot: KnowledgeSnapshot; coverage: KnowledgeCoverage }) => {
    if (displayedVersion.current !== snapshot.version_id) {
      setSelected(null);
      setSource(null);
      setSourceId(null);
      setSelectedId(id => snapshot.concepts.some(concept => concept.id === id) ? id : null);
      setFocus(current => {
        const concept = snapshot.concepts.find(item => item.id === current?.id);
        return concept ? { id: concept.id, name: concept.name } : null;
      });
    }
    displayedVersion.current = snapshot.version_id;
    setKnowledge(snapshot);
    setCoverage(coverage);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    displayedVersion.current = null;
    setLoading(true);
    setKnowledge(null);
    setCoverage(null);
    setTasks([]);
    setSelected(null);
    setSource(null);
    setSourceId(null);
    setSelectedId(null);
    setError('');
    (async () => {
      const [taskItems, status] = await Promise.all([
        request<Task[]>(tasksUrl(courseId), { signal: controller.signal }),
        request<ModelStatus>('/api/model/status', { signal: controller.signal }),
      ]);
      const bundle = await readPublished(controller.signal);
      if (controller.signal.aborted) return;
      applyPublished(bundle);
      setTasks(taskItems);
      setModel(status);
    })().catch(cause => {
      if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : '无法读取课程知识。');
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => {
      controller.abort();
      refreshController.current?.abort();
      mutationController.current?.abort();
    };
  }, [courseId, readPublished, applyPublished]);

  const activeTask = tasks.find(task => task.status === 'queued' || task.status === 'running');
  useEffect(() => {
    if (!activeTask) return;
    const controller = new AbortController();
    let timer: number;
    async function poll() {
      try {
        const next = await request<Task[]>(tasksUrl(courseId), { signal: controller.signal });
        const finished = next.find(task => task.id === activeTask!.id);
        if (finished?.status === 'completed' && finished.version_id !== displayedVersion.current) {
          const bundle = await readPublished(controller.signal);
          if (controller.signal.aborted) return;
          applyPublished(bundle);
        }
        if (controller.signal.aborted) return;
        setTasks(next);
        if (next.some(task => task.status === 'queued' || task.status === 'running')) timer = window.setTimeout(poll, 1500);
      } catch {
        if (!controller.signal.aborted) {
          setError('暂时无法读取整理结果，正在重试；已显示的知识仍可阅读。');
          timer = window.setTimeout(poll, 1500);
        }
      }
    }
    timer = window.setTimeout(poll, 1500);
    return () => { controller.abort(); clearTimeout(timer); };
  }, [activeTask?.id, courseId, readPublished, applyPublished]);

  async function refreshKnowledge() {
    refreshController.current?.abort();
    const controller = new AbortController();
    refreshController.current = controller;
    setRefreshing(true);
    setError('');
    try {
      const bundle = await readPublished(controller.signal);
      if (!controller.signal.aborted) applyPublished(bundle);
    } catch (cause) {
      if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : '无法刷新知识。');
    } finally { if (!controller.signal.aborted) setRefreshing(false); }
  }

  async function startBuild(selection: NonNullable<KnowledgeSnapshot['selection']>) {
    const controller = new AbortController();
    mutationController.current = controller;
    setCreating(true);
    setError('');
    try {
      const task = await request<Task>(tasksUrl(courseId), {
        method: 'POST', signal: controller.signal,
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(selection),
      });
      if (controller.signal.aborted) return false;
      setTasks(items => [task, ...items]);
      return true;
    } catch (cause) {
      if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : '无法开始整理。');
      return false;
    } finally { if (!controller.signal.aborted) setCreating(false); }
  }

  async function retryTask(task: Task) {
    const controller = new AbortController();
    mutationController.current = controller;
    setCreating(true);
    setError('');
    try {
      const next = await request<Task>(`${tasksUrl(courseId)}/${task.id}/retry`, { method: 'POST', signal: controller.signal });
      if (!controller.signal.aborted) setTasks(items => items.map(item => item.id === next.id ? next : item));
    } catch (cause) {
      if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : '无法重试任务。');
    } finally { if (!controller.signal.aborted) setCreating(false); }
  }

  const versionId = knowledge?.version_id;
  useEffect(() => {
    setSelected(null);
    if (!selectedId || !versionId) return;
    const controller = new AbortController();
    request<ConceptDetail>(conceptUrl(courseId, versionId, selectedId), { signal: controller.signal })
      .then(detail => { if (!controller.signal.aborted) setSelected(detail); })
      .catch(cause => {
        if (!controller.signal.aborted) {
          setSelectedId(null);
          setError(cause instanceof Error ? cause.message : '无法读取知识点页面。');
        }
      });
    return () => controller.abort();
  }, [courseId, versionId, selectedId]);

  function selectConcept(id: string) {
    setAsking(false);
    setError('');
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
        if (!controller.signal.aborted) {
          setSourceId(null);
          setError(cause instanceof Error ? cause.message : '无法读取原文片段。');
        }
      });
    return () => controller.abort();
  }, [courseId, versionId, sourceId]);

  function openSource(snippetId: string) {
    setError('');
    setSourceId(snippetId);
  }

  const latest = tasks[0];
  const published = knowledge?.state === 'published';
  const busy = creating || refreshing || Boolean(activeTask);
  const scopePicker = coverage && <ScopePicker coverage={coverage} updating={published} busy={busy}
    configured={Boolean(model?.configured)} onStart={startBuild} />;

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

      {latest && <TaskPanel task={latest} onRetry={() => void retryTask(latest)} busy={busy || !model?.configured} />}
      {published && activeTask && <p className="update-reading" role="status">追加整理期间，当前版本仍可阅读；成功后将一起更新知识和来源。</p>}
      {published && <details className="update-picker"><summary>选择追加整理范围</summary>{scopePicker}</details>}
      {published && knowledge?.parent_version_id && knowledge.summary && <p className="update-summary" role="status">
        当前版本更新：新增 {knowledge.summary.new_concepts} · 补充 {knowledge.summary.updated_concepts} · 待核对 {knowledge.summary.needs_review ?? 0} · 冲突 {knowledge.summary.conflicts}
      </p>}
      {published && coverage && <CoveragePanel coverage={coverage} />}

      {!published ? (
        <section className="unpublished">
          <div className="empty-state">
            <div className="eyebrow">NOT ORGANIZED YET</div>
            <h2>尚未整理成课程知识</h2>
            <p>选择一小节资料发起整理。只有通过来源与结构校验的版本才会发布；失败时不会产生可用知识。</p>
          </div>
          {scopePicker}
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
              <div className="study-toolbar-actions"><button className="secondary" onClick={() => { setFocus(null); setAsking(true); }}>课程提问</button>
              <button className="secondary" disabled={busy} onClick={() => void refreshKnowledge()}>{refreshing ? '正在刷新…' : '刷新知识'}</button></div>
            </div>
            {knowledge && <GraphExplorer key={knowledge.version_id} snapshot={knowledge} selectedId={selectedId} onSelectConcept={selectConcept} />}

          </div>
          {asking && knowledge && coverage && <QuestionPanel key={`${courseId}:${knowledge.version_id}:${focus?.id ?? "course"}`}
            courseId={courseId} snapshot={knowledge} coverage={coverage} modelConfigured={Boolean(model?.configured)} focus={focus}
            onClearFocus={() => setFocus(null)} onClose={() => setAsking(false)} onOpenNotes={onOpenNotes} />}
          <div className="concept-panel-holder" hidden={asking}>
          {selected && knowledge && selected.version_id === knowledge.version_id && (
            <ConceptPanel
              courseId={courseId} modelConfigured={Boolean(model?.configured)}
              onAsk={() => { setFocus({ id: selected.id, name: selected.name }); setAsking(true); }} onOpenNotes={onOpenNotes}
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
        </div>
      )}

      {source && source.version_id === versionId && <SourceDialog source={source} onClose={() => setSourceId(null)} />}
    </div>
  );
}
