import { useEffect, useState } from 'react';
import { COVERAGE_LABEL, coverageUrl, request, type KnowledgeCoverage } from '../../api';

/** Read coverage against the same version as the graph, including unprocessed sources. */
export function CoveragePanel({ courseId, versionId }: { courseId: string; versionId: string }) {
  const [coverage, setCoverage] = useState<KnowledgeCoverage | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    setCoverage(null);
    setError('');
    request<KnowledgeCoverage>(coverageUrl(courseId, versionId), { signal: controller.signal })
      .then(value => { if (!controller.signal.aborted) setCoverage(value); })
      .catch(cause => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : '无法读取整理范围。'); });
    return () => controller.abort();
  }, [courseId, versionId]);
  return <details className="coverage-panel">
    <summary>查看已整理与未整理范围</summary>
    <p className="form-help">范围按当前知识版本记录；选择部分章节不会把整份资料标为已整理。</p>
    {error ? <p role="alert">{error}</p> : !coverage ? <p role="status">正在读取范围…</p> : coverage.materials.map(material => <section key={material.id} className="coverage-material">
      <h3>{material.filename} <span className={`scope-status ${material.status}`}>{COVERAGE_LABEL[material.status]}</span></h3>
      <small>{material.organized_fragments} / {material.total_fragments} 个原文片段已整理</small>
      <ul>{material.chapters.map(chapter => <li key={chapter.id} style={{ paddingLeft: Math.max(0, chapter.level - 1) * 12 }}>
        <span>{chapter.title}</span><span className={`scope-status ${chapter.status}`}>{COVERAGE_LABEL[chapter.status]}</span>
      </li>)}</ul>
    </section>)}
  </details>;
}
