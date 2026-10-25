import { useEffect, useRef, useState } from 'react';
import { request } from '../../api';
import { SourcePreview, StudyError, studyRequest, useMath, useRequestScope } from '../../shared/study';
import type { NoteDetail, NoteSummary } from './types';
import './notes.css';

const SOURCE_LABEL: Record<NoteSummary['source_type'], string> = {
  manual: '手写', concept: '来自知识点', answer: '来自问答', expansion: '来自拓展解释',
};
const formatTime = (value: number) => new Date(value * 1000).toLocaleString('zh-CN');

export function NotesWorkspace({ courseId, selectedNoteId, active, onDirtyChange }: {
  courseId: string; selectedNoteId: string | null; active: boolean; onDirtyChange: (dirty: boolean) => void;
}) {
  const scope = useRequestScope();
  const [notes, setNotes] = useState<NoteSummary[]>([]);
  const [note, setNote] = useState<NoteDetail | null>(null);
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [dirty, setDirty] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [creating, setCreating] = useState(false);
  const [conflict, setConflict] = useState(false);
  const [error, setError] = useState('');
  const [preview, setPreview] = useState(true);
  const [sourceUrl, setSourceUrl] = useState<string | null>(null);
  const previewRef = useRef<HTMLDivElement>(null);
  const edits = useRef(0);
  const selection = useRef(0);
  const editorPending = useRef(false);
  const detailController = useRef<AbortController | null>(null);
  const current = useRef({ note, dirty });
  current.current = { note, dirty };
  const url = `/api/courses/${encodeURIComponent(courseId)}/notes`;
  useMath(previewRef, preview && !dirty ? note?.html : undefined);

  useEffect(() => { onDirtyChange(dirty); }, [dirty, onDirtyChange]);
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { if (current.current.dirty) { event.preventDefault(); event.returnValue = ''; } };
    window.addEventListener('beforeunload', warn);
    return () => { window.removeEventListener('beforeunload', warn); detailController.current?.abort(); };
  }, []);

  function apply(detail: NoteDetail) {
    current.current = { note: detail, dirty: false };
    setNote(detail); setTitle(detail.title); setBody(detail.body_md); setDirty(false);
    setConflict(false); setPreview(true); setSourceUrl(null); edits.current += 1;
  }

  async function openNote(id: string, reload = false) {
    if (saving || creating) return;
    if (current.current.note?.id === id && !reload) return;
    if (current.current.dirty && !window.confirm('当前笔记有未保存的修改，确定丢弃草稿并读取另一版本或笔记吗？')) return;
    const controller = new AbortController();
    detailController.current?.abort(); detailController.current = controller;
    selection.current += 1;
    editorPending.current = true;
    setLoading(true); setError('');
    try {
      const detail = await request<NoteDetail>(`${url}/${encodeURIComponent(id)}`, { signal: controller.signal });
      if (!controller.signal.aborted && !scope.current.signal.aborted) apply(detail);
    } catch (cause) {
      if (!controller.signal.aborted && !scope.current.signal.aborted) setError(cause instanceof Error ? cause.message : '无法打开笔记。');
    } finally { if (!controller.signal.aborted && !scope.current.signal.aborted) { editorPending.current = false; setLoading(false); } }
  }

  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    (async () => {
      const items = await request<NoteSummary[]>(url, { signal: controller.signal });
      if (controller.signal.aborted) return;
      setNotes(items);
      const target = selectedNoteId ?? current.current.note?.id ?? items[0]?.id;
      if (!editorPending.current && target && target !== current.current.note?.id) await openNote(target);
      if (!controller.signal.aborted && !editorPending.current) setLoading(false);
    })().catch(cause => {
      if (!controller.signal.aborted) { setError(cause instanceof Error ? cause.message : '无法读取笔记。'); if (!editorPending.current) setLoading(false); }
    });
    return () => controller.abort();
  }, [courseId, selectedNoteId, active]);

  async function createManual() {
    if (saving || creating) return;
    if (dirty && !window.confirm('当前笔记有未保存的修改，确定丢弃草稿并新建吗？')) return;
    detailController.current?.abort(); selection.current += 1;
    editorPending.current = true;
    setCreating(true); setLoading(true); setError('');
    try {
      const created = await request<NoteDetail>(url, { method: 'POST', signal: scope.current.signal,
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title: '未命名笔记', body_md: '在这里写下你的理解。' }) });
      if (scope.current.signal.aborted) return;
      apply(created); setPreview(false); setNotes(items => [created, ...items.filter(item => item.id !== created.id)]);
    } catch (cause) { if (!scope.current.signal.aborted) setError(cause instanceof Error ? cause.message : '无法新建笔记。'); }
    finally { if (!scope.current.signal.aborted) { editorPending.current = false; setCreating(false); setLoading(false); } }
  }

  async function save() {
    if (!note || !dirty || saving || conflict) return;
    const submittedEdit = edits.current;
    const submittedSelection = selection.current;
    setSaving(true); setError('');
    try {
      const updated = await studyRequest<NoteDetail>(`${url}/${encodeURIComponent(note.id)}`, {
        method: 'PUT', signal: scope.current.signal, headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, body_md: body, revision: note.revision }),
      });
      if (scope.current.signal.aborted || submittedSelection !== selection.current) return;
      // Advance the server revision even if the user typed more while saving.
      setNote(updated);
      setNotes(items => items.map(item => item.id === updated.id ? updated : item));
      if (edits.current === submittedEdit) { setTitle(updated.title); setBody(updated.body_md); setDirty(false); }
    } catch (cause) {
      if (scope.current.signal.aborted || submittedSelection !== selection.current) return;
      setError(cause instanceof Error ? cause.message : '保存失败。');
      if (cause instanceof StudyError && cause.status === 409) setConflict(true);
    } finally { if (!scope.current.signal.aborted) setSaving(false); }
  }

  function openCitation(snippetId: string) {
    if (note) setSourceUrl(`${url}/${encodeURIComponent(note.id)}/sources/${encodeURIComponent(snippetId)}`);
  }

  if (loading) return <div className="empty-state" role="status">正在读取个人笔记…</div>;

  return (
    <div className="notes-workspace">
      {error && (
        <div className="message error" role="alert">
          <span>{error}</span>
          <button onClick={() => setError('')} aria-label="关闭错误提示">×</button>
        </div>
      )}
      {conflict && <div className="message warning" role="status">服务器已有新修订，你的草稿仍保留。请先复制需要保留的文字，再主动重载。<button className="secondary" onClick={() => note && void openNote(note.id, true)}>重新读取服务器版本</button></div>}
      <div className="notes-layout">
        <aside className="note-list" aria-label="个人笔记列表">
          <div className="note-list-head">
            <h2>我的笔记</h2>
            <button className="secondary" onClick={() => void createManual()} disabled={creating || saving || loading}>
              {creating ? '正在新建…' : '新建手写笔记'}
            </button>
          </div>
          {notes.length === 0 && (
            <div className="note-empty">
              <p>还没有笔记。</p>
              <p className="muted">可从知识点或已完成的问答生成，也可以新建手写笔记。</p>
            </div>
          )}
          {notes.map(item => (
            <button
              key={item.id}
              className={`note-item ${note?.id === item.id ? 'selected' : ''}`}
              disabled={saving || creating || loading}
              onClick={() => void openNote(item.id)}
            >
              <span className="note-item-title">{item.title}</span>
              <span className="note-item-meta">
                {SOURCE_LABEL[item.source_type]} · {formatTime(item.updated_at)}
              </span>
              <span className="note-item-badges">
                {item.expansion && <span className="badge expansion">模型补充</span>}
                {item.needs_review && <span className="badge review">需检查依据</span>}
                {item.citation_count > 0 && <span className="muted">{item.citation_count} 条引用</span>}
              </span>
            </button>
          ))}
        </aside>

        <section className="note-editor" aria-label="笔记编辑器">
          {!note ? (
            <div className="empty-state">
              <div className="eyebrow">PERSONAL NOTES</div>
              <h2>从学习内容生成你的笔记</h2>
              <p>在知识点页面或已完成的问答中点击“保存为笔记”，也可以直接新建手写笔记。</p>
            </div>
          ) : (
            <>
              <div className="note-editor-head">
                <input
                  className="note-title-input"
                  value={title}
                  onChange={event => { setTitle(event.target.value); edits.current += 1; setDirty(true); }}
                  aria-label="笔记标题"
                  maxLength={200}
                />
                <div className="note-editor-actions">
                  <button className="secondary" disabled={dirty}
                    onClick={() => setPreview(value => !value)}>
                    {preview ? '编辑' : '预览'}
                  </button>
                  <button className="primary" onClick={() => void save()} disabled={!dirty || saving || conflict || !title.trim()}>
                    {saving ? '正在保存…' : dirty ? '保存修改' : '已保存'}
                  </button>
                </div>
              </div>
              <div className="note-meta">
                <span>{SOURCE_LABEL[note.source_type]}</span>
                {note.version_id && <span>依据版本 {note.version_id.slice(0, 8)}</span>}
                <span>修订 {note.revision}</span>
                {note.expansion && <span className="badge expansion">模型补充（超出课程资料）</span>}
              </div>
              {note.needs_review && (
                <div className="message warning" role="status">
                  {note.review_reason ?? '相关依据已变化，请检查笔记。'} 正文不会被自动改写，是否调整由你决定。
                </div>
              )}
              {dirty && <p className="form-help">有未保存的修改；保存后可预览。</p>}
              {preview && !dirty ? (
                <div ref={previewRef} className="note-preview" onClick={event => { const href = (event.target as HTMLElement).closest('a')?.getAttribute('href'); if (href?.startsWith('snippet:')) { event.preventDefault(); openCitation(href.slice(8)); } }} dangerouslySetInnerHTML={{ __html: note.html }} />
              ) : (
                <textarea
                  className="note-body-input"
                  value={body}
                  onChange={event => { setBody(event.target.value); edits.current += 1; setDirty(true); }}
                  aria-label="笔记正文"
                />
              )}
              <section className="note-citations">
                <h3>原文依据</h3>
                {note.citations.length === 0 ? (
                  <p className="muted">
                    {note.expansion ? '这份笔记来自拓展解释，没有课程原文依据。' : '这份笔记没有关联原文引用。'}
                  </p>
                ) : (
                  note.citations.map(citation => (
                    <button
                      className="citation"
                      key={citation.snippet_id}
                      onClick={() => void openCitation(citation.snippet_id)}
                    >
                      <span className="citation-lines">
                        {citation.chapter_title ?? citation.filename} · L{citation.start_line}–{citation.end_line}
                      </span>
                      <span className="citation-quote">{citation.excerpt}</span>
                    </button>
                  ))
                )}
              </section>
              <p className="form-help">笔记独立于课程知识保存；知识更新不会覆盖你编辑的正文。</p>
            </>
          )}
        </section>
      </div>
      {sourceUrl && <SourcePreview url={sourceUrl} onClose={() => setSourceUrl(null)} />}
    </div>
  );
}
