import { useState } from 'react';
import { Expansion, NoteDetail, request } from './api';

export function ExpansionPanel({
  courseId,
  answerId,
  conceptId,
  modelConfigured,
  onOpenNotes,
}: {
  courseId: string;
  answerId?: string;
  conceptId?: string;
  modelConfigured: boolean;
  onOpenNotes: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [item, setItem] = useState<Expansion | null>(null);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  async function load() {
    setOpen(true);
    if (item || loading) return;
    setLoading(true);
    setError('');
    try {
      const result = await request<Expansion>(`/api/courses/${encodeURIComponent(courseId)}/expansions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(answerId ? { answer_id: answerId } : { concept_id: conceptId }),
      });
      setItem(result);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '无法获取拓展解释。');
    } finally {
      setLoading(false);
    }
  }

  async function saveAsNote() {
    if (!item || item.status !== 'completed') return;
    setSaving(true);
    setError('');
    try {
      await request<NoteDetail>(`/api/courses/${encodeURIComponent(courseId)}/notes/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source_type: 'expansion', source_id: item.id }),
      });
      setSaved(true);
      onOpenNotes();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '保存笔记失败。');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="expansion">
      <button
        className="secondary"
        onClick={() => void load()}
        disabled={!modelConfigured || loading}
        title={modelConfigured ? undefined : '后端尚未配置模型凭据'}
      >
        {loading ? '正在获取拓展解释…' : '获取资料外拓展解释'}
      </button>
      {open && (
        <div className="expansion-box">
          <div className="expansion-head">
            <span className="badge expansion">模型补充</span>
            <span className="muted">超出课程资料，不是教材事实</span>
          </div>
          {loading && <p className="muted">正在生成，请稍候…</p>}
          {item?.status === 'completed' && (
            <>
              <div className="expansion-text">{item.text}</div>
              <div className="expansion-actions">
                <button className="secondary" onClick={() => void saveAsNote()} disabled={saving || saved}>
                  {saved ? '已保存到个人笔记' : saving ? '正在保存…' : '保存为个人笔记'}
                </button>
              </div>
            </>
          )}
          {item?.status === 'failed' && (
            <p className="task-error" role="alert">
              拓展解释未完成：{item.error_message ?? '模型调用失败'}
              {item.error_code ? `（${item.error_code}）` : ''}
            </p>
          )}
          {error && <p className="task-error" role="alert">{error}</p>}
          <p className="form-help">只有你主动点击才会生成；它不会自动写入课程知识。</p>
        </div>
      )}
    </div>
  );
}
