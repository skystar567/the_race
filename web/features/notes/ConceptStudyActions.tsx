import { useState } from 'react';
import { request } from '../../api';
import { useRequestScope } from '../../shared/study';
import { ExpansionPanel } from '../expansions/ExpansionPanel';
import type { NoteDetail } from './types';

export function ConceptStudyActions({ courseId, conceptId, versionId, modelConfigured, onAsk, onOpenNotes }: {
  courseId: string; conceptId: string; versionId: string; modelConfigured: boolean;
  onAsk: () => void; onOpenNotes: (id: string) => void;
}) {
  const scope = useRequestScope();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  async function generate() {
    setSaving(true); setError('');
    try {
      const note = await request<NoteDetail>(`/api/courses/${encodeURIComponent(courseId)}/notes/generate`, {
        method: 'POST', signal: scope.current.signal, headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source_type: 'concept', source_id: conceptId, version_id: versionId }),
      });
      if (!scope.current.signal.aborted) onOpenNotes(note.id);
    } catch (cause) { if (!scope.current.signal.aborted) setError(cause instanceof Error ? cause.message : '无法生成笔记。'); }
    finally { if (!scope.current.signal.aborted) setSaving(false); }
  }
  return <div className="study-actions">
    <button className="secondary" onClick={onAsk}>围绕此知识点提问</button>
    <button className="secondary" disabled={saving || !modelConfigured} onClick={() => void generate()}>{saving ? '正在生成笔记…' : '生成个人笔记'}</button>
    <ExpansionPanel courseId={courseId} versionId={versionId} conceptId={conceptId} modelConfigured={modelConfigured} onOpenNotes={onOpenNotes} />
    {error && <p className="message error" role="alert">{error}</p>}
  </div>;
}
