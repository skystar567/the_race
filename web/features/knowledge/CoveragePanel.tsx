import { COVERAGE_LABEL, type KnowledgeCoverage } from './coverage-api';

/** Display the same version-pinned coverage used by the scope picker. */
export function CoveragePanel({ coverage }: { coverage: KnowledgeCoverage }) {
  return <details className="coverage-panel">
    <summary>查看已整理与未整理范围</summary>
    <p className="form-help">范围按当前知识版本记录；选择部分章节不会把整份资料标为已整理。</p>
    {coverage.materials.map(material => <section key={material.id} className="coverage-material">
      <h3>{material.filename} <span className={`scope-status ${material.status}`}>{COVERAGE_LABEL[material.status]}</span></h3>
      <small>{material.organized_fragments} / {material.total_fragments} 个原文片段已整理</small>
      <ul>{material.chapters.map(chapter => <li key={chapter.id} style={{ paddingLeft: Math.max(0, chapter.level - 1) * 12 }}>
        <span>{chapter.title}</span><span className={`scope-status ${chapter.status}`}>{COVERAGE_LABEL[chapter.status]}</span>
      </li>)}</ul>
    </section>)}
  </details>;
}
