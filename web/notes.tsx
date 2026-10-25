import { useEffect, useRef, useState } from 'react';
import katex from 'katex';
import {
  NoteDetail,
  NoteSummary,
  SourceDetail,
  request,
  sourceUrl,
} from './api';

const SOURCE_LABEL: Record<NoteSummary['source_type'], string> = {
  manual: '手写',
  concept: '来自知识点',
  answer: '来自问答',
  expansion: '来自拓展解释',
};

function formatTime(value: number): string {
  return new Date(value * 1000).toLocaleString('zh-CN', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  });
}

function useMath(ref: React.RefObject<HTMLElement | null>, html: string | undefined) {
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
  useMath(content, source.html);
  useEffect(() => { dialog.current?.showModal(); }, []);
  return (
    <dialog
      ref={dialog}
      className="source-dialog"
      onCancel={event => { event.preventDefault(); onClose(); }}
      onClick={event => { if (event.target === dialog.current) onClose(); }}
    >
      <div className="modal-head">
        <div>
          <h2>原文依据</h2>
          <p className="source-meta">
            {source.filename}
            {source.chapter_title ? ` · ${source.chapter_title}` : ''} · 第 {source.start_line}—{source.end_line} 行
            {` · 版本 ${source.version_id.slice(0, 8)}`}
          </p>
        </div>
        <button className="icon-button" onClick={onClose} aria-label="关闭">×</button>
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

export function NotesWorkspace({ courseId }: { courseId: string }) {
  const [notes, setNotes] = useState<NoteSummary[]>([]);
  const [note, setNote] = useState<NoteDetail | null>(null);
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [revision, setRevision] = useState(1);
  const [dirty, setDirty] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState('');
  const [preview, setPreview] = useState(true);
  const [source, setSource] = useState<SourceDetail | null>(null);
  const previewRef = useRef<HTMLDivElement>(null);
  useMath(previewRef, note?.html);

  function apply(detail: NoteDetail) {
    setNote(detail);
    setTitle(detail.title);
    setBody(detail.body_md);
    setRevision(detail.revision);
    setDirty(false);
    setPreview(true);
  }

  async function loadList(selectId?: string) {
    const items = await request<NoteSummary[]>(`/api/courses/${encodeURIComponent(courseId)}/notes`);
    setNotes(items);
    const target = selectId ?? items[0]?.id;
    if (!target) { setNote(null); return; }
    const detail = await request<NoteDetail>(
      `/api/courses/${encodeURIComponent(courseId)}/notes/${encodeURIComponent(target)}`,
    );
    apply(detail);
  }

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError('');
    setNotes([]);
    setNote(null);
    (async () => {
      const items = await request<NoteSummary[]>(`/api/courses/${encodeURIComponent(courseId)}/notes`);
      if (cancelled) return;
      setNotes(items);
      if (items.length) {
        const detail = await request<NoteDetail>(
          `/api/courses/${encodeURIComponent(courseId)}/notes/${encodeURIComponent(items[0].id)}`,
        );
        if (!cancelled) apply(detail);
      }
    })()
      .catch(cause => { if (!cancelled) setError(cause instanceof Error ? cause.message : '无法读取笔记。'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [courseId]);

  async function openNote(id: string) {
    if (dirty && !window.confirm('当前笔记有未保存的修改，确定切换吗？')) return;
    setError('');
    try {
      apply(await request<NoteDetail>(
        `/api/courses/${encodeURIComponent(courseId)}/notes/${encodeURIComponent(id)}`,
      ));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '无法打开笔记。');
    }
  }

  async function createManual() {
    if (dirty && !window.confirm('当前笔记有未保存的修改，确定新建吗？')) return;
    setCreating(true);
    setError('');
    try {
      const created = await request<NoteDetail>(`/api/courses/${encodeURIComponent(courseId)}/notes`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: '未命名笔记', body_md: '在这里写下你的理解。' }),
      });
      apply(created);
      await loadList(created.id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '无法新建笔记。');
    } finally {
      setCreating(false);
    }
  }

  async function save() {
    if (!note || !dirty) return;
    setSaving(true);
    setError('');
    try {
      const updated = await request<NoteDetail>(
        `/api/courses/${encodeURIComponent(courseId)}/notes/${encodeURIComponent(note.id)}`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ title, body_md: body, revision }),
        },
      );
      apply(updated);
      setNotes(items => items.map(item => item.id === updated.id
        ? { ...item, title: updated.title, revision: updated.revision, updated_at: updated.updated_at }
        : item));
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : '保存失败。';
      setError(message);
      if (message.includes('已在别处更新')) {
        try { await loadList(note.id); } catch { /* keep the current editor */ }
      }
    } finally {
      setSaving(false);
    }
  }

  async function openCitation(snippetId: string) {
    if (!note?.version_id) {
      setError('这份笔记没有关联知识版本，无法打开原文。');
      return;
    }
    try {
      setSource(await request<SourceDetail>(
        sourceUrl(courseId, note.version_id, snippetId),
      ));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '无法读取原文。');
    }
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
      <div className="notes-layout">
        <aside className="note-list" aria-label="个人笔记列表">
          <div className="note-list-head">
            <h2>我的笔记</h2>
            <button className="secondary" onClick={() => void createManual()} disabled={creating}>
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
                  onChange={event => { setTitle(event.target.value); setDirty(true); }}
                  aria-label="笔记标题"
                  maxLength={200}
                />
                <div className="note-editor-actions">
                  <button className="secondary" onClick={() => setPreview(value => !value)}>
                    {preview ? '编辑' : '预览'}
                  </button>
                  <button className="primary" onClick={() => void save()} disabled={!dirty || saving}>
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
              {preview ? (
                <div ref={previewRef} className="note-preview" dangerouslySetInnerHTML={{ __html: note.html }} />
              ) : (
                <textarea
                  className="note-body-input"
                  value={body}
                  onChange={event => { setBody(event.target.value); setDirty(true); }}
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
      {source && <SourceDialog source={source} onClose={() => setSource(null)} />}
    </div>
  );
}
