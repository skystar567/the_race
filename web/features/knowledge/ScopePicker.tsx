import { useEffect, useState } from 'react';
import { type KnowledgeSnapshot } from '../../api';
import { COVERAGE_LABEL, type KnowledgeCoverage } from './coverage-api';

type Selection = NonNullable<KnowledgeSnapshot['selection']>;

export function ScopePicker({ coverage, updating, busy, configured, onStart }: {
  coverage: KnowledgeCoverage;
  updating: boolean;
  busy: boolean;
  configured: boolean;
  onStart: (selection: Selection) => Promise<boolean>;
}) {
  const [materials, setMaterials] = useState<string[]>([]);
  const [chapters, setChapters] = useState<string[]>([]);
  useEffect(() => { setMaterials([]); setChapters([]); }, [coverage.version_id]);

  async function submit() {
    if (await onStart({ material_ids: materials, chapter_ids: chapters })) {
      setMaterials([]);
      setChapters([]);
    }
  }

  return <div className="scope-picker">
    <div className="section-bar"><h2>整理范围</h2><span>仅处理尚未整理的片段 · 单次上限 60,000 字符</span></div>
    {coverage.materials.length === 0 && <p className="muted">这门课程还没有资料，请先在「资料阅读」中导入 Markdown。</p>}
    {coverage.materials.map(material => <div className="scope-material" key={material.id}>
      <label className="check-row">
        <input type="checkbox" checked={materials.includes(material.id)} disabled={busy || material.status === 'organized'}
          onChange={() => {
            setMaterials(current => current.includes(material.id) ? current.filter(id => id !== material.id) : [...current, material.id]);
            setChapters(current => current.filter(id => !material.chapters.some(c => c.id === id)));
          }} />
        <span>{material.filename}</span><small>{COVERAGE_LABEL[material.status]}</small>
      </label>
      <div className="chapter-chips">{material.chapters.map(chapter => <button key={chapter.id}
        className={`chip-toggle ${chapters.includes(chapter.id) ? 'on' : ''} ${chapter.status === 'organized' ? 'organized' : ''}`}
        disabled={busy || materials.includes(material.id) || chapter.status === 'organized'}
        onClick={() => setChapters(current => current.includes(chapter.id) ? current.filter(id => id !== chapter.id) : [...current, chapter.id])}>
        {chapter.title}<small className={`scope-status ${chapter.status}`}>{COVERAGE_LABEL[chapter.status]}</small>
      </button>)}</div>
    </div>)}
    <div className="scope-actions">
      <span className="muted">已选择 {materials.length} 份资料、{chapters.length} 个章节</span>
      <button className="primary" onClick={() => void submit()} disabled={busy || !configured || (!materials.length && !chapters.length)}>
        {updating ? '追加整理' : '开始整理'}
      </button>
    </div>
    {!configured && <p className="form-help">配置后端模型凭据后才能开始整理。</p>}
  </div>;
}
