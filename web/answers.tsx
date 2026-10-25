import { useEffect, useMemo, useRef, useState } from 'react';
import {
  AnswerDetail,
  AnswerStart,
  AnswerStatus,
  AnswerSummary,
  KnowledgeSnapshot,
  request,
} from './api';

const STATUS_LABEL: Record<AnswerStatus, string> = {
  generating: '生成中',
  completed: '已完成',
  insufficient: '资料不足',
  citation_failed: '引用校验失败',
  interrupted: '已中断',
  failed: '失败',
};

const STATUS_HINT: Partial<Record<AnswerStatus, string>> = {
  insufficient: '没有足够的可引用原文，或回答未提供可核查依据；这不代表教材中没有该内容。',
  citation_failed: '回答引用了未提供的原文片段，不能视为完成答案。',
  interrupted: '回答没有正常结束，已显示内容不代表完整结论。',
  failed: '回答没有生成完成，可以重试。',
};

function parseEvent(block: string): { name: string; data: unknown } | null {
  let name = 'message';
  const data: string[] = [];
  for (const line of block.split('\n')) {
    if (line.startsWith('event:')) name = line.slice(6).trim();
    else if (line.startsWith('data:')) data.push(line.slice(5).trim());
  }
  if (!data.length) return null;
  try {
    return { name, data: JSON.parse(data.join('\n')) };
  } catch {
    return null;
  }
}

function liveText(text: string): string {
  return text.replace(/\[([^\]]+)\]\(snippet:[^)]+\)/g, '〔$1〕');
}

function formatTime(value: number): string {
  return new Date(value * 1000).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function QuestionPanel({
  courseId,
  snapshot,
  modelConfigured,
  focus,
  onClearFocus,
  onClose,
  onOpenSource,
}: {
  courseId: string;
  snapshot: KnowledgeSnapshot;
  modelConfigured: boolean;
  focus: { id: string; name: string } | null;
  onClearFocus: () => void;
  onClose: () => void;
  onOpenSource: (snippetId: string, versionId: string) => void;
}) {
  const [question, setQuestion] = useState('');
  const [scopeMaterials, setScopeMaterials] = useState<string[]>([]);
  const [scopeChapters, setScopeChapters] = useState<string[]>([]);
  const [scopeOpen, setScopeOpen] = useState(false);
  const [history, setHistory] = useState<AnswerSummary[]>([]);
  const [answer, setAnswer] = useState<AnswerDetail | null>(null);
  const [started, setStarted] = useState<AnswerStart | null>(null);
  const [status, setStatus] = useState<AnswerStatus | null>(null);
  const [live, setLive] = useState('');
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState('');
  const abort = useRef<AbortController | null>(null);

  const groups = useMemo(() => {
    const map = new Map<string, { id: string; filename: string; chapters: Array<{ id: string; title: string }> }>();
    for (const chapter of snapshot.chapters) {
      const group = map.get(chapter.material_id) ?? {
        id: chapter.material_id,
        filename: chapter.filename,
        chapters: [],
      };
      group.chapters.push({ id: chapter.id, title: chapter.title });
      map.set(chapter.material_id, group);
    }
    return [...map.values()];
  }, [snapshot.chapters]);

  const chapterNames = useMemo(
    () => new Map(snapshot.chapters.map(chapter => [chapter.id, chapter.title])),
    [snapshot.chapters],
  );

  const pendingLabel = scopeMaterials.length
    ? `${scopeMaterials.length} 份资料的全部原文`
    : scopeChapters.length
      ? scopeChapters.map(id => chapterNames.get(id) ?? id).join('、')
      : '全部已整理内容';

  const suggestions = useMemo(() => {
    const names = snapshot.concepts.slice(0, 2).map(concept => concept.name);
    const list: string[] = [];
    if (names.length >= 2) list.push(`${names[0]}和${names[1]}有什么区别？`);
    if (names[0]) list.push(`什么是${names[0]}？`);
    return list;
  }, [snapshot.concepts]);

  async function loadHistory() {
    try {
      setHistory(await request<AnswerSummary[]>(`/api/courses/${courseId}/answers`));
    } catch {
      // History is secondary; the current answer stays readable.
    }
  }

  useEffect(() => {
    setQuestion('');
    setAnswer(null);
    setStarted(null);
    setStatus(null);
    setLive('');
    setError('');
    setScopeMaterials([]);
    setScopeChapters([]);
    void loadHistory();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [courseId]);

  function toggleMaterial(materialId: string) {
    setScopeMaterials(current =>
      current.includes(materialId) ? current.filter(id => id !== materialId) : [...current, materialId],
    );
    setScopeChapters(current =>
      current.filter(id => {
        const chapter = snapshot.chapters.find(item => item.id === id);
        return chapter?.material_id !== materialId;
      }),
    );
  }

  function toggleChapter(materialId: string, chapterId: string) {
    setScopeChapters(current =>
      current.includes(chapterId) ? current.filter(id => id !== chapterId) : [...current, chapterId],
    );
    setScopeMaterials(current => current.filter(id => id !== materialId));
  }

  async function submit() {
    const value = question.trim();
    if (!value || asking || !modelConfigured) return;
    setAsking(true);
    setLive('');
    setAnswer(null);
    setStarted(null);
    setStatus('generating');
    setError('');
    const controller = new AbortController();
    abort.current = controller;
    let done = false;
    try {
      const response = await fetch(`/api/courses/${encodeURIComponent(courseId)}/answers/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: value,
          material_ids: scopeMaterials,
          chapter_ids: scopeChapters,
          focus_concept_id: focus?.id ?? null,
        }),
        signal: controller.signal,
      });
      if (!response.ok) {
        const body: { detail?: unknown } = await response.json().catch(() => ({}));
        throw new Error(typeof body.detail === 'string' ? body.detail : `提问未完成（${response.status}）。`);
      }
      const reader = response.body?.getReader();
      if (!reader) throw new Error('当前浏览器无法读取流式回答。');
      const decoder = new TextDecoder();
      let buffer = '';
      while (!done) {
        const chunk = await reader.read();
        if (chunk.done) break;
        buffer += decoder.decode(chunk.value, { stream: true });
        let index = buffer.indexOf('\n\n');
        while (index >= 0) {
          const event = parseEvent(buffer.slice(0, index));
          buffer = buffer.slice(index + 2);
          index = buffer.indexOf('\n\n');
          if (!event) continue;
          if (event.name === 'start') {
            setStarted(event.data as AnswerStart);
          } else if (event.name === 'delta') {
            const text = (event.data as { text?: string }).text ?? '';
            setLive(current => current + text);
          } else if (event.name === 'done') {
            const payload = event.data as { answer: AnswerDetail };
            setAnswer(payload.answer);
            setStatus(payload.answer.status);
            setStarted(null);
            setLive('');
            done = true;
            void loadHistory();
          }
        }
      }
      if (!done) {
        setStatus('interrupted');
        setError('回答连接已结束，但没有收到完成事件；已显示内容不代表完整答案。');
      }
    } catch (cause) {
      if (controller.signal.aborted) {
        setStatus('interrupted');
      } else {
        setStatus('failed');
        setError(cause instanceof Error ? cause.message : '提问未完成。');
      }
    } finally {
      setAsking(false);
      abort.current = null;
    }
  }

  async function openHistory(item: AnswerSummary) {
    setError('');
    try {
      const detail = await request<AnswerDetail>(
        `/api/courses/${encodeURIComponent(courseId)}/answers/${encodeURIComponent(item.id)}`,
      );
      setAnswer(detail);
      setStatus(detail.status);
      setQuestion(detail.question);
      setStarted(null);
      setLive('');
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '无法读取历史回答。');
    }
  }

  function handleCitationClick(event: React.MouseEvent<HTMLDivElement>) {
    const anchor = (event.target as HTMLElement).closest('a');
    const href = anchor?.getAttribute('href') ?? '';
    if (!href.startsWith('snippet:')) return;
    event.preventDefault();
    const version = answer?.version_id ?? started?.version_id;
    if (version) onOpenSource(href.slice('snippet:'.length), version);
  }

  const displayStatus = status ?? (asking ? 'generating' : null);
  const currentLabel = answer?.scope.label ?? started?.scope.label ?? pendingLabel;
  const evidenceCount = answer?.citation_count ?? started?.evidence_count ?? 0;

  return (
    <aside className="concept-panel qa-panel" aria-label="课程问答">
      <div className="concept-panel-head">
        <div>
          <div className="eyebrow">GROUNDED Q&amp;A</div>
          <h2>课程问答</h2>
        </div>
        <button className="icon-button" onClick={onClose} aria-label="关闭课程问答">×</button>
      </div>
      <p className="muted">回答只依据当前知识版本的原文；引用可打开核对。检索未命中和资料不足会如实说明。</p>
      {!modelConfigured && (
        <div className="message warning">后端尚未配置模型凭据，暂时不能提问。</div>
      )}

      <section className="qa-scope">
        <div className="qa-scope-row">
          <span>范围</span>
          <strong>{currentLabel}</strong>
          <button className="link-button" onClick={() => setScopeOpen(value => !value)}>调整</button>
        </div>
        {scopeOpen && (
          <div className="scope-selector">
            <button className="link-button" onClick={() => { setScopeMaterials([]); setScopeChapters([]); }}>
              恢复全部已整理内容
            </button>
            {groups.map(group => (
              <div className="scope-group" key={group.id}>
                <label className="check-row">
                  <input
                    type="checkbox"
                    checked={scopeMaterials.includes(group.id)}
                    onChange={() => toggleMaterial(group.id)}
                    disabled={asking}
                  />
                  <span>{group.filename}</span>
                </label>
                <div className="chapter-chips">
                  {group.chapters.map(chapter => (
                    <button
                      key={chapter.id}
                      className={`chip-toggle ${scopeChapters.includes(chapter.id) ? 'on' : ''}`}
                      onClick={() => toggleChapter(group.id, chapter.id)}
                      disabled={asking || scopeMaterials.includes(group.id)}
                    >
                      {chapter.title}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
        {focus && (
          <div className="focus-chip">
            提问焦点：{focus.name}
            <button onClick={onClearFocus} aria-label="清除提问焦点">×</button>
          </div>
        )}
      </section>

      <form
        className="qa-form"
        onSubmit={event => {
          event.preventDefault();
          void submit();
        }}
      >
        <textarea
          value={question}
          onChange={event => setQuestion(event.target.value)}
          onKeyDown={event => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault();
              void submit();
            }
          }}
          placeholder="围绕当前课程已整理内容提问，例如：进程和线程有什么区别？"
          maxLength={2000}
          disabled={asking}
          aria-label="课程问题"
        />
        <div className="qa-actions">
          <span className="muted">Enter 提问 · Shift+Enter 换行</span>
          {asking ? (
            <button type="button" className="secondary" onClick={() => abort.current?.abort()}>停止</button>
          ) : (
            <button className="primary" type="submit" disabled={!modelConfigured || question.trim().length < 2}>
              提问
            </button>
          )}
        </div>
      </form>

      {!answer && !asking && suggestions.length > 0 && (
        <div className="qa-suggestions">
          {suggestions.map(text => (
            <button key={text} className="chip-toggle" onClick={() => setQuestion(text)}>{text}</button>
          ))}
        </div>
      )}

      {error && <div className="message error" role="alert">{error}</div>}

      {(answer || asking || live) && displayStatus && (
        <section className="qa-answer" aria-live="polite">
          <div className="qa-answer-head">
            <span className={`badge ${displayStatus}`}>{STATUS_LABEL[displayStatus]}</span>
            <span className="muted">
              版本 {answer?.version_id.slice(0, 8) ?? started?.version_id.slice(0, 8) ?? '—'} · 引用 {evidenceCount}
            </span>
            {started?.resolution === 'model' && <span className="muted">模型辅助定位</span>}
          </div>
          {started && started.missing_image_count > 0 && (
            <div className="message warning">
              引用范围内有 {started.missing_image_count} 处缺失图片，涉及图片的判断不可靠。
            </div>
          )}
          {answer ? (
            <div
              className="answer-body"
              onClick={handleCitationClick}
              dangerouslySetInnerHTML={{ __html: answer.html }}
            />
          ) : (
            <div className="answer-body live">{liveText(live)}<span className="cursor">▌</span></div>
          )}
          {answer && (
            <div className="answer-citations">
              <h3>引用依据</h3>
              {answer.citations.length === 0 ? (
                <p className="muted">这份回答没有可核查的原文引用，因此未标为完成。</p>
              ) : (
                answer.citations.map(citation => (
                  <button
                    className="citation"
                    key={citation.snippet_id}
                    onClick={() => onOpenSource(citation.snippet_id, answer.version_id)}
                  >
                    <span className="citation-lines">
                      {citation.chapter_title ?? citation.filename} · L{citation.start_line}–{citation.end_line}
                    </span>
                    <span className="citation-quote">{citation.excerpt}</span>
                  </button>
                ))
              )}
            </div>
          )}
          {answer?.error_message && <p className="task-error">{answer.error_message}</p>}
          {displayStatus && STATUS_HINT[displayStatus] && (
            <p className="form-help">{STATUS_HINT[displayStatus]}</p>
          )}
        </section>
      )}

      {history.length > 0 && (
        <section className="qa-history">
          <h3>最近提问</h3>
          {history.slice(0, 6).map(item => (
            <button key={item.id} className="qa-history-item" onClick={() => void openHistory(item)}>
              <span className={`badge ${item.status}`}>{STATUS_LABEL[item.status]}</span>
              <span className="qa-history-question">{item.question}</span>
              <small>{formatTime(item.created_at)} · {item.citation_count} 引用</small>
            </button>
          ))}
        </section>
      )}
    </aside>
  );
}
