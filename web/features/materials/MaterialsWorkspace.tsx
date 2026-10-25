import { useEffect, useRef, useState } from 'react';
import { COVERAGE_LABEL, coverageUrl, materialUrl, request, type Course, type Fragment, type Material, type MaterialDetail, type KnowledgeCoverage } from '../../api';
import { Icon } from '../../shared/Icon';
import { Modal } from '../../shared/Modal';
import { ReadingContent } from './ReadingContent';
import './materials.css';

export function MaterialsWorkspace({ course, onMaterialCountChange }: {
  course: Course;
  onMaterialCountChange: (courseId: string, count: number) => void;
}) {
  const [materials, setMaterials] = useState<Material[]>([]);
  const [coverage, setCoverage] = useState<KnowledgeCoverage | null>(null);
  const [coverageUnavailable, setCoverageUnavailable] = useState(false);
  const [materialId, setMaterialId] = useState('');
  const [detail, setDetail] = useState<MaterialDetail | null>(null);
  const [chapterId, setChapterId] = useState('');
  const [fragments, setFragments] = useState<Fragment[]>([]);
  const [view, setView] = useState<'read' | 'source'>('read');
  const [source, setSource] = useState<Fragment | null>(null);
  const [uploading, setUploading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [reading, setReading] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const uploadRef = useRef<HTMLInputElement>(null);
  const uploadController = useRef<AbortController | null>(null);

  function report(error: unknown) {
    if (error instanceof Error && error.name !== 'AbortError') setError(error.message);
  }

  useEffect(() => {
    const controller = new AbortController();
    request<KnowledgeCoverage>(coverageUrl(course.id), { signal: controller.signal }).then(value => {
      if (!controller.signal.aborted) setCoverage(value);
    }).catch(error => { if (!controller.signal.aborted) { setCoverageUnavailable(true); report(error); } });
    request<Material[]>(`/api/courses/${encodeURIComponent(course.id)}/materials`, { signal: controller.signal }).then(items => {
      if (controller.signal.aborted) return;
      setMaterials(items);
      setMaterialId(items[0]?.id ?? '');
      onMaterialCountChange(course.id, items.length);
    }).catch(error => { if (!controller.signal.aborted) report(error); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => {
      controller.abort();
      uploadController.current?.abort();
    };
  }, [course.id, onMaterialCountChange]);

  useEffect(() => {
    setDetail(null);
    setFragments([]);
    setChapterId('');
    setSource(null);
    if (!materialId) return;
    const controller = new AbortController();
    request<MaterialDetail>(materialUrl(course.id, materialId), { signal: controller.signal }).then(value => {
      if (!controller.signal.aborted) setDetail(value);
    }).catch(error => { if (!controller.signal.aborted) report(error); });
    return () => controller.abort();
  }, [course.id, materialId]);

  useEffect(() => {
    setFragments([]);
    if (!detail) return;
    const controller = new AbortController();
    setReading(true);
    const query = chapterId ? `?chapter_id=${encodeURIComponent(chapterId)}` : '';
    request<Fragment[]>(materialUrl(detail.course_id, detail.id) + '/fragments' + query, { signal: controller.signal }).then(items => {
      if (!controller.signal.aborted) setFragments(items);
    }).catch(error => { if (!controller.signal.aborted) report(error); })
      .finally(() => { if (!controller.signal.aborted) setReading(false); });
    return () => controller.abort();
  }, [detail, chapterId]);

  async function upload(file?: File) {
    if (!file || uploading) return;
    if (!file.name.toLowerCase().endsWith('.md')) { setError('请选择 Markdown（.md）文件。'); return; }
    if (file.size > 20 * 1024 * 1024) { setError('单份资料不能超过 20 MB。'); return; }
    const controller = new AbortController();
    uploadController.current = controller;
    setUploading(true);
    setError('');
    setNotice('');
    try {
      const result = await request<Material>(`/api/courses/${encodeURIComponent(course.id)}/materials?filename=${encodeURIComponent(file.name)}`, {
        method: 'POST', body: file, signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      setMaterials(items => [...items, result]);
      setMaterialId(result.id);
      onMaterialCountChange(course.id, materials.length + 1);
      setNotice('资料已保存，可以按章节阅读原文。当前尚未进行知识整理。');
    } catch (error) {
      if (!controller.signal.aborted) report(error);
    } finally {
      if (!controller.signal.aborted) {
        setUploading(false);
        if (uploadRef.current) uploadRef.current.value = '';
      }
    }
  }

  return (
    <section className="materials-workspace" aria-label="课程资料工作区">
      <div className="page-heading">
        <div><div className="eyebrow">LEARNING MATERIALS</div><h1>{course.name}</h1><p>教材、课堂笔记与补充材料，在这里集中阅读。</p></div>
        <button className="primary" disabled={uploading || loading} onClick={() => uploadRef.current?.click()}><Icon name="upload" size={18} />{uploading ? '正在导入…' : '导入 Markdown'}</button>
        <input ref={uploadRef} className="visually-hidden" type="file" accept=".md,text/markdown" disabled={uploading || loading} aria-label="选择 Markdown 文件" onChange={event => void upload(event.target.files?.[0])} />
      </div>
      {error && <div className="message error" role="alert"><span>{error}</span><button onClick={() => setError('')} aria-label="关闭错误提示"><Icon name="close" size={16} /></button></div>}
      {notice && <div className="message success" role="status">{notice}</div>}
      <div className="section-bar"><h2>课程资料 <span>{materials.length}</span></h2><span>保留原文 · 按章节阅读</span></div>

      {loading ? <div className="empty-state" role="status">正在读取学习空间…</div> : !materials.length ? (
        <section className="empty-state">
          <div className="empty-book"><Icon name="book" size={45} /></div><div className="eyebrow">A PLACE FOR YOUR KNOWLEDGE</div>
          <h2>放入你的第一份学习资料</h2>
          <p>上传 Markdown 教材或笔记，按章节浏览，随时核查原文。</p>
          <button className="primary" onClick={() => uploadRef.current?.click()} disabled={uploading}><Icon name="upload" size={18} />选择 Markdown 文件</button>
          <div className="empty-footnote">支持 UTF-8 Markdown · 单份最大 20 MB</div>
        </section>
      ) : (
        <div className="materials-layout">
          <aside className="material-sidebar" aria-label="资料和章节">
            <div className="pane-label">已导入资料</div>
            {materials.map(material => (
              <button className={`material-button ${material.id === materialId ? 'selected' : ''}`} key={material.id} onClick={() => { setError(''); setMaterialId(material.id); }}>
                <Icon name="file" size={19} /><span>{material.filename}<small>{(material.byte_size / 1024).toFixed(1)} KB · 已导入</small></span>
              </button>
            ))}
            {detail && <>
              <div className="pane-label toc-title">章节目录 <span>{detail.chapters.length}</span></div>
              <nav className="toc" aria-label="章节目录">
                <button className={!chapterId ? 'selected' : ''} onClick={() => setChapterId('')}>全部原文</button>
                {detail.chapters.map(chapter => {
                  const state = coverage?.materials.find(item => item.id === detail.id)?.chapters.find(item => item.id === chapter.id)?.status;
                  return <button key={chapter.id} className={chapterId === chapter.id ? 'selected' : ''} style={{ paddingLeft: `${12 + (chapter.level - 1) * 10}px` }} onClick={() => setChapterId(chapter.id)}>{chapter.title}{state && <small className={`scope-status ${state}`}>{COVERAGE_LABEL[state]}</small>}</button>;
                })}
              </nav>
            </>}
          </aside>
          <article className="reader" aria-label="资料正文">
            {detail ? <>
              <div className="reader-toolbar">
                <div className="view-tabs" aria-label="阅读模式"><button className={view === 'read' ? 'selected' : ''} onClick={() => setView('read')}>阅读</button><button className={view === 'source' ? 'selected' : ''} onClick={() => setView('source')}>原文</button></div>
                <a className="download-link" href={materialUrl(course.id, materialId) + '/raw'}>下载原始文件 ↗</a>
              </div>
              <div className="document-heading">
                <div className="document-meta"><span className="imported-badge">已导入 · {coverage ? COVERAGE_LABEL[coverage.materials.find(item => item.id === detail.id)?.status ?? 'unorganized'] : coverageUnavailable ? '整理状态暂不可用' : '整理状态读取中'}</span><span>{detail.fragment_count} 个原文片段</span></div>
                <h2>{detail.filename.replace(/\.md$/i, '')}</h2>
                <p>保留上传内容，章节目录依据原文编号组织。</p>
                {detail.missing_image_count > 0 && <div className="image-notice">资料引用了 {detail.missing_image_count} 张未导入的图片，阅读时会标出缺失位置。</div>}
              </div>
              {reading ? <div className="reading-placeholder" role="status">正在读取原文…</div> : view === 'read' ? <ReadingContent fragments={fragments} onSource={setSource} /> : (
                <div className="raw-content">{fragments.map(fragment => <section key={fragment.id}><div className="raw-line-label">第 {fragment.start_line}—{fragment.end_line} 行</div><pre>{fragment.markdown}</pre></section>)}</div>
              )}
              <footer className="reader-footer">原文片段可追溯到上传文件 · 此页展示学习资料，不代表已建立课程知识库</footer>
            </> : <div className="reading-placeholder">正在打开资料…</div>}
          </article>
        </div>
      )}
      {source && detail && <Modal title="原文依据" onClose={() => setSource(null)}>
        <div className="source-meta">{detail.filename}<br />第 {source.start_line}—{source.end_line} 行</div>
        <pre className="source-original">{source.markdown}</pre>
        <p className="form-help">上方文字直接来自上传资料，保留原始 Markdown。</p>
      </Modal>}
    </section>
  );
}
