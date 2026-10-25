import { useEffect, useMemo, useState } from 'react';
import {
  AnswerResult, FeedbackRecord, KnowledgeSnapshot, Material, MaterialDetail, RouteResult, StudyNote, request,
} from './api';

type View = 'ask' | 'notes' | 'route' | 'export' | 'feedback';

function message(error: unknown): string {
  return error instanceof Error ? error.message : '请求未完成';
}

function useSnapshot(courseId: string) {
  const [snapshot, setSnapshot] = useState<KnowledgeSnapshot | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    request<KnowledgeSnapshot>(`/api/courses/${encodeURIComponent(courseId)}/knowledge`, { signal: controller.signal })
      .then(value => setSnapshot(value.state === 'published' ? value : null))
      .catch((reason: unknown) => { if ((reason as Error).name !== 'AbortError') setError(message(reason)); });
    return () => controller.abort();
  }, [courseId]);
  return { snapshot, error };
}

function AnswersPanel({ courseId, materials, detail }: {
  courseId: string;
  materials: Material[];
  detail: MaterialDetail | null;
}) {
  const { snapshot, error: snapshotError } = useSnapshot(courseId);
  const [question, setQuestion] = useState('');
  const [scope, setScope] = useState<'course' | 'material' | 'chapter'>('course');
  const [chapterId, setChapterId] = useState('');
  const [conceptId, setConceptId] = useState('');
  const [expansion, setExpansion] = useState(false);
  const [answer, setAnswer] = useState<AnswerResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState('');

  async function ask() {
    if (!question.trim()) return;
    setBusy(true); setError(''); setAnswer(null); setSaved('');
    try {
      const materialIds = scope === 'course' ? [] : detail ? [detail.id] : [];
      const chapterIds = scope === 'chapter' && chapterId ? [chapterId] : [];
      const result = await request<AnswerResult>(`/api/courses/${encodeURIComponent(courseId)}/ask`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question, material_ids: materialIds, chapter_ids: chapterIds,
          concept_id: conceptId || null, expansion,
        }),
      });
      setAnswer(result);
    } catch (reason) { setError(message(reason)); } finally { setBusy(false); }
  }

  async function saveToNote() {
    if (!answer) return;
    setBusy(true); setSaved('');
    try {
      await request<StudyNote>(`/api/courses/${encodeURIComponent(courseId)}/notes`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: `问答：${question.slice(0, 40)}`, markdown: answer.answer,
          expansion: answer.status === 'completed_with_expansion',
          citations: answer.citations.map(citation => ({
            snippet_id: citation.snippet_id,
            quote: citation.quote,
          })).filter(citation => citation.quote),
        }),
      });
      setSaved('已保存为个人笔记。');
    } catch (reason) { setError(message(reason)); } finally { setBusy(false); }
  }

  return <section className="learning-panel">
    <header><div><div className="eyebrow">GROUNDED Q&amp;A</div><h2>围绕课程提问</h2>
      <p>回答绑定当前已发布版本；关键结论带原文引用，资料不足会明确说明。</p></div></header>
    {(snapshotError || error) && <div className="message error" role="alert">{snapshotError || error}</div>}
    {!snapshot && <div className="empty-learning">还没有已发布知识版本；先在“知识图谱”完成一次整理。</div>}
    {snapshot && <>
      <div className="ask-box">
        <textarea value={question} onChange={event => setQuestion(event.target.value)}
          placeholder="例如：进程和线程有什么区别？" aria-label="问题" />
        <div className="ask-options">
          <label>范围<select value={scope} onChange={event => setScope(event.target.value as typeof scope)}>
            <option value="course">当前课程全部资料</option>
            <option value="material">当前资料</option>
            <option value="chapter">当前章节</option>
          </select></label>
          {scope === 'chapter' && <label>章节<select value={chapterId} onChange={event => setChapterId(event.target.value)}>
            <option value="">选择章节</option>
            {detail?.chapters.map(chapter => <option key={chapter.id} value={chapter.id}>{chapter.title}</option>)}
          </select></label>}
          <label>提问焦点<select value={conceptId} onChange={event => setConceptId(event.target.value)}>
            <option value="">不限定</option>
            {snapshot.concepts.map(concept => <option key={concept.id} value={concept.id}>{concept.name}</option>)}
          </select></label>
          <label className="check-line"><input type="checkbox" checked={expansion}
            onChange={event => setExpansion(event.target.checked)} />需要资料外拓展</label>
          <button className="primary" onClick={() => void ask()} disabled={busy || !question.trim()}>
            {busy ? '正在生成…' : '提问'}
          </button>
        </div>
        {!materials.length && <p className="form-help">先在“资料阅读”导入 Markdown。</p>}
      </div>
      {saved && <div className="message success" role="status">{saved}</div>}
      {answer && <article className={`answer-card status-${answer.status}`}>
        <div className="answer-head"><strong>{answer.status === 'completed' ? '已完成回答'
          : answer.status === 'insufficient' ? '资料不足'
            : answer.status === 'invalid_citations' ? '引用校验未通过'
              : answer.status === 'completed_with_expansion' ? '含模型补充' : '未核实回答'}</strong>
          <span>版本 {answer.version_id.slice(0, 8)}</span></div>
        <div className="answer-body">{answer.answer}</div>
        {answer.citations.length > 0 && <div className="answer-citations">
          {answer.citations.map(citation => <div className="citation-item" key={citation.snippet_id}>
            <strong>{citation.filename} · L{citation.start_line}–{citation.end_line}</strong>
            {citation.chapter_title && <small>{citation.chapter_title}</small>}
          </div>)}
        </div>}
        {answer.warnings.map(warning => <p className="warning-text" key={warning}>{warning}</p>)}
        <button className="secondary" onClick={() => void saveToNote()} disabled={busy}>保存为笔记</button>
      </article>}
    </>}
  </section>;
}

function NotesPanel({ courseId }: { courseId: string }) {
  const [notes, setNotes] = useState<StudyNote[]>([]);
  const [selected, setSelected] = useState<StudyNote | null>(null);
  const [title, setTitle] = useState('');
  const [markdown, setMarkdown] = useState('');
  const [health, setHealth] = useState<{ healthy: boolean; reasons: string[] } | null>(null);
  const [messageText, setMessageText] = useState('');
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      const items = await request<StudyNote[]>(`/api/courses/${encodeURIComponent(courseId)}/notes`);
      setNotes(items);
      if (!selected && items.length) choose(items[0]);
    } catch (reason) { setMessageText(message(reason)); }
  }
  useEffect(() => { void load(); }, [courseId]);

  function choose(note: StudyNote) {
    setSelected(note); setTitle(note.title); setMarkdown(note.markdown); setMessageText('');
    void request<{ healthy: boolean; reasons: string[] }>(`/api/notes/${encodeURIComponent(note.id)}/health`)
      .then(setHealth).catch(() => setHealth(null));
  }

  async function save() {
    setBusy(true); setMessageText('');
    try {
      if (selected) {
        const updated = await request<StudyNote>(`/api/notes/${encodeURIComponent(selected.id)}`, {
          method: 'PATCH', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ title, markdown }),
        });
        setSelected(updated); setMessageText('笔记已保存。');
        await request<{ healthy: boolean; reasons: string[] }>(`/api/notes/${encodeURIComponent(updated.id)}/health`)
          .then(setHealth).catch(() => setHealth(null));
      } else {
        const created = await request<StudyNote>(`/api/courses/${encodeURIComponent(courseId)}/notes`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ title, markdown }),
        });
        setSelected(created); setMessageText('笔记已创建。');
      }
      await load();
    } catch (reason) { setMessageText(message(reason)); } finally { setBusy(false); }
  }

  return <section className="learning-panel">
    <header><div><div className="eyebrow">PERSONAL NOTES</div><h2>个人笔记</h2>
      <p>课程知识更新不会自动改写正文；引用变化时提示检查。</p></div>
      <button className="secondary" onClick={() => { setSelected(null); setTitle(''); setMarkdown(''); setHealth(null); }}>
        新建笔记
      </button></header>
    {messageText && <div className="message success" role="status">{messageText}</div>}
    <div className="notes-layout">
      <aside className="notes-list">{notes.map(note => <button key={note.id}
        className={selected?.id === note.id ? 'selected' : ''} onClick={() => choose(note)}>
        <strong>{note.title}</strong><small>{note.expansion ? '含模型拓展 · ' : ''}{note.updated_at.slice(0, 10)}</small>
      </button>)}{!notes.length && <p className="form-help">还没有笔记。可以在问答里保存，或新建一篇。</p>}</aside>
      <div className="note-editor">
        <input value={title} onChange={event => setTitle(event.target.value)} placeholder="笔记标题" aria-label="笔记标题" />
        <textarea value={markdown} onChange={event => setMarkdown(event.target.value)} placeholder="写下你的理解…" aria-label="笔记正文" />
        {health && !health.healthy && <div className="message error" role="status">
          来源变化：{health.reasons.join('；')}。请检查引用后再决定是否修改正文。
        </div>}
        {selected?.citations.length ? <div className="note-citations">{selected.citations.map(citation =>
          <div className="citation-item" key={citation.id}><strong>原文依据</strong><small>{citation.quote}</small></div>)}</div> : null}
        <button className="primary" onClick={() => void save()} disabled={busy || !title.trim() || !markdown.trim()}>
          {selected ? '保存修改' : '创建笔记'}
        </button>
      </div>
    </div>
  </section>;
}

function RoutePanel({ courseId }: { courseId: string }) {
  const { snapshot, error } = useSnapshot(courseId);
  const [target, setTarget] = useState('');
  const [current, setCurrent] = useState('');
  const [route, setRoute] = useState<RouteResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [routeError, setRouteError] = useState('');
  useEffect(() => { if (!target && snapshot?.concepts.length) setTarget(snapshot.concepts[0].id); }, [snapshot, target]);
  const names = useMemo(() => new Map((snapshot?.concepts ?? []).map(item => [item.id, item.name])), [snapshot]);

  async function plan() {
    if (!target) return;
    setBusy(true); setRouteError('');
    try {
      const search = new URLSearchParams({ target });
      if (current) search.set('current', current);
      setRoute(await request<RouteResult>(`/api/courses/${encodeURIComponent(courseId)}/route?${search}`));
    } catch (reason) { setRouteError(message(reason)); } finally { setBusy(false); }
  }

  return <section className="learning-panel">
    <header><div><div className="eyebrow">LEARNING ROUTE</div><h2>围绕目标的学习顺序</h2>
      <p>只使用前置关系；包含和对比不参与排序。路线是建议，不表示掌握程度。</p></div></header>
    {(error || routeError) && <div className="message error" role="alert">{error || routeError}</div>}
    {!snapshot && <div className="empty-learning">还没有已发布知识版本。</div>}
    {snapshot && <>
      <div className="route-options">
        <label>目标知识点<select value={target} onChange={event => setTarget(event.target.value)}>
          {snapshot.concepts.map(concept => <option key={concept.id} value={concept.id}>{concept.name}</option>)}
        </select></label>
        <label>当前学习位置<select value={current} onChange={event => setCurrent(event.target.value)}>
          <option value="">不指定</option>
          {snapshot.concepts.map(concept => <option key={concept.id} value={concept.id}>{concept.name}</option>)}
        </select></label>
        <button className="primary" onClick={() => void plan()} disabled={busy || !target}>
          {busy ? '计算中…' : '计算路线'}
        </button>
      </div>
      {route && <article className={`route-card status-${route.status}`}>
        <div className="answer-head"><strong>{route.status === 'complete' ? '可确定路线'
          : route.status === 'partial' ? '部分路线' : '无法确定完整路线'}</strong>
          <span>{route.status === 'partial' ? '存在循环/缺口/待核对' : ''}</span></div>
        {route.prior.length > 0 && <p className="form-help">起点之前（非掌握度）：{route.prior.map(id => names.get(id) ?? id).join(' → ')}</p>}
        <ol>{route.route.map(id => <li key={id}>{names.get(id) ?? id}</li>)}</ol>
        {route.cycles.map(cycle => <p className="warning-text" key={cycle.join('-')}>循环：{cycle.map(id => names.get(id) ?? id).join(' → ')}</p>)}
        {route.gaps.map(gap => <p className="warning-text" key={gap.node}>缺口：{names.get(gap.node) ?? gap.node}</p>)}
        {route.unverified.map(edge => <p className="warning-text" key={`${edge.from}-${edge.to}`}>
          待核对：{names.get(edge.from) ?? edge.from} → {names.get(edge.to) ?? edge.to}
        </p>)}
        {route.warnings.map(warning => <p className="form-help" key={warning}>{warning}</p>)}
      </article>}
    </>}
  </section>;
}

function FeedbackPanel({ courseId }: { courseId: string }) {
  const { snapshot, error } = useSnapshot(courseId);
  const [targetType, setTargetType] = useState<'concept' | 'relation'>('concept');
  const [targetId, setTargetId] = useState('');
  const [body, setBody] = useState('');
  const [feedback, setFeedback] = useState<FeedbackRecord | null>(null);
  const [busy, setBusy] = useState(false);
  const [messageText, setMessageText] = useState('');
  const names = useMemo(() => new Map((snapshot?.concepts ?? []).map(item => [item.id, item.name])), [snapshot]);

  useEffect(() => {
    if (!snapshot) return;
    const first = targetType === 'concept' ? snapshot.concepts[0]?.id : snapshot.relations[0]?.id;
    setTargetId(first ?? '');
  }, [snapshot, targetType]);

  async function submit() {
    if (!targetId || !body.trim()) return;
    setBusy(true); setMessageText('');
    try {
      const created = await request<FeedbackRecord>(`/api/courses/${encodeURIComponent(courseId)}/feedback`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target_type: targetType, target_id: targetId, body }),
      });
      setFeedback(created); setMessageText('反馈已记录。'); setBody('');
    } catch (reason) { setMessageText(message(reason)); } finally { setBusy(false); }
  }

  async function recheck() {
    if (!feedback) return;
    setBusy(true); setMessageText('');
    try {
      const result = await request<{ feedback: FeedbackRecord; task: { status: string }; changed?: boolean }>(
        `/api/feedback/${encodeURIComponent(feedback.id)}/recheck`, { method: 'POST' });
      setFeedback(result.feedback);
      setMessageText(result.feedback.status === 'resolved'
        ? (result.changed ? '重新整理完成，相关知识已变化。' : '重新整理完成，相关知识没有变化。')
        : result.feedback.status === 'checking' ? '整理任务运行中，请稍后查看任务状态。' : '核对未完成，任务失败。');
    } catch (reason) { setMessageText(message(reason)); } finally { setBusy(false); }
  }

  return <section className="learning-panel">
    <header><div><div className="eyebrow">FEEDBACK LOOP</div><h2>问题反馈</h2>
      <p>指出知识点或关系的具体问题；重新核对会建立新的知识版本，而不是覆盖旧版本。</p></div></header>
    {(error || messageText) && <div className={`message ${error ? 'error' : 'success'}`} role="status">{error || messageText}</div>}
    {!snapshot && <div className="empty-learning">还没有已发布知识版本。</div>}
    {snapshot && <div className="feedback-form">
      <div className="route-options">
        <label>对象<select value={targetType} onChange={event => setTargetType(event.target.value as typeof targetType)}>
          <option value="concept">知识点</option><option value="relation">关系</option>
        </select></label>
        <label>具体条目<select value={targetId} onChange={event => setTargetId(event.target.value)}>
          {(targetType === 'concept' ? snapshot.concepts : snapshot.relations).map(item =>
            <option key={item.id} value={item.id}>
              {targetType === 'concept' ? (item as typeof snapshot.concepts[number]).name
                : `${names.get((item as typeof snapshot.relations[number]).from_id) ?? '章节'} → ${names.get((item as typeof snapshot.relations[number]).to_id) ?? '知识点'}`}
            </option>)}
        </select></label>
      </div>
      <textarea value={body} onChange={event => setBody(event.target.value)} placeholder="例如：这条关系缺少原文依据" aria-label="反馈内容" />
      <button className="primary" onClick={() => void submit()} disabled={busy || !targetId || !body.trim()}>提交反馈</button>
      {feedback && <div className="feedback-record">
        <p><strong>状态：</strong>{feedback.status} / {feedback.resolution}</p>
        <p className="form-help">{feedback.body}</p>
        <button className="secondary" onClick={() => void recheck()} disabled={busy || feedback.status === 'checking'}>
          {busy ? '核对中…' : '重新核对'}
        </button>
      </div>}
    </div>}
  </section>;
}

function ExportPanel({ courseId }: { courseId: string }) {
  const { snapshot, error } = useSnapshot(courseId);
  return <section className="learning-panel">
    <header><div><div className="eyebrow">PORTABLE PACKAGE</div><h2>导出课程资料包</h2>
      <p>固定当前知识版本、个人笔记和原文，离线可读；缺图保留明确标记。</p></div></header>
    {error && <div className="message error" role="alert">{error}</div>}
    <div className="export-card">
      {snapshot ? <>
        <p>当前版本：{snapshot.version_id?.slice(0, 8)} · {snapshot.concepts.length} 个知识点 · {snapshot.relations.length} 条关系</p>
        <p className="form-help">包含知识页面、关系索引、个人笔记、已导入原始 Markdown 和引用来源。</p>
        <a className="primary" href={`/api/courses/${encodeURIComponent(courseId)}/export`} download>
          下载课程资料包（.zip）
        </a>
      </> : <p className="form-help">还没有已发布知识版本；导出需要固定的知识版本。</p>}
    </div>
  </section>;
}

export function LearningWorkspace({ courseId, materials, detail, view }: {
  courseId: string;
  materials: Material[];
  detail: MaterialDetail | null;
  view: View;
}) {
  if (view === 'ask') return <AnswersPanel courseId={courseId} materials={materials} detail={detail} />;
  if (view === 'notes') return <NotesPanel courseId={courseId} />;
  if (view === 'route') return <RoutePanel courseId={courseId} />;
  if (view === 'feedback') return <FeedbackPanel courseId={courseId} />;
  return <ExportPanel courseId={courseId} />;
}
