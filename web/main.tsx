import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import katex from 'katex';
import 'katex/dist/katex.min.css';
import { Course, KnowledgeVersion, Material, MaterialDetail, Fragment, request, materialUrl } from './api';
import { KnowledgeWorkspace } from './knowledge';
import { LearningWorkspace } from './learning';
import './style.css';

function Icon({ name, size = 20 }: { name: 'book' | 'plus' | 'upload' | 'file' | 'arrow' | 'close'; size?: number }) {
  const shapes = {
    book: <><path d="M12 6C8 3 4 4 2 5v14c3-2 7-1 10 1 3-2 7-3 10-1V5c-2-1-6-2-10 1Z" /><path d="M12 6v14" /></>,
    plus: <path d="M12 5v14M5 12h14" />,
    upload: <><path d="M12 16V3m-5 5 5-5 5 5" /><path d="M4 15v5h16v-5" /></>,
    file: <><path d="M14 2H5v20h14V7Z" /><path d="M14 2v6h5M8 13h8M8 17h6" /></>,
    arrow: <path d="m9 5 7 7-7 7" />,
    close: <path d="m6 6 12 12M6 18 18 6" />,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{shapes[name]}</svg>;
}

function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => { ref.current?.showModal(); }, []);
  return <dialog ref={ref} onCancel={event => { event.preventDefault(); onClose(); }} onClick={event => { if (event.target === ref.current) onClose(); }}>
    <div className="modal-head"><h2>{title}</h2><button className="icon-button" onClick={onClose} aria-label="关闭"><Icon name="close" /></button></div>
    {children}
  </dialog>;
}

function ReadingContent({ fragments, onSource }: { fragments: Fragment[]; onSource: (fragment: Fragment) => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.querySelectorAll<HTMLElement>('[data-math]').forEach(element => {
      katex.render(element.dataset.math ?? '', element, { displayMode: element.dataset.display === 'true', throwOnError: false, trust: false, strict: 'ignore' });
    });
  }, [fragments]);
  return <div ref={ref} className="reading-content">{fragments.map(fragment => <section className="source-block" key={fragment.id}>
    <div dangerouslySetInnerHTML={{ __html: fragment.html }} />
    <button className="source-link" onClick={() => onSource(fragment)} aria-label={`查看第 ${fragment.start_line} 至 ${fragment.end_line} 行原文`}>L{fragment.start_line}{fragment.end_line !== fragment.start_line ? `–${fragment.end_line}` : ''} <span>查看原文</span></button>
  </section>)}</div>;
}

function App() {
  const [courses, setCourses] = useState<Course[]>([]);
  const [courseId, setCourseId] = useState('');
  const [materials, setMaterials] = useState<Material[]>([]);
  const [materialId, setMaterialId] = useState('');
  const [detail, setDetail] = useState<MaterialDetail | null>(null);
  const [chapterId, setChapterId] = useState('');
  const [fragments, setFragments] = useState<Fragment[]>([]);
  const [workspace, setWorkspace] = useState<'materials' | 'knowledge' | 'ask' | 'notes' | 'route' | 'export' | 'feedback'>('materials');
  const [readerMode, setReaderMode] = useState<'read' | 'source'>('read');
  const [source, setSource] = useState<Fragment | null>(null);
  const [creating, setCreating] = useState(false);
  const [courseName, setCourseName] = useState('');
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [reading, setReading] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [knowledgeReady, setKnowledgeReady] = useState(false);
  const uploadRef = useRef<HTMLInputElement>(null);
  const uploadController = useRef<AbortController | null>(null);
  const currentCourse = useRef(courseId);
  currentCourse.current = courseId;
  const course = courses.find(c => c.id === courseId);

  function report(error: unknown) {
    if (error instanceof Error && error.name !== 'AbortError') setError(error.message);
  }

  useEffect(() => {
    const controller = new AbortController();
    request<Course[]>('/api/courses', { signal: controller.signal }).then(items => {
      setCourses(items);
      const saved = localStorage.getItem('campus-course');
      setCourseId(items.find(c => c.id === saved)?.id ?? items[0]?.id ?? '');
    }).catch(report).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    uploadController.current?.abort();
    setUploading(false); setMaterialId(''); setMaterials([]); setDetail(null); setFragments([]); setSource(null); setNotice('');
    if (!courseId) return;
    localStorage.setItem('campus-course', courseId);
    const controller = new AbortController();
    setLoading(true);
    request<Material[]>(`/api/courses/${courseId}/materials`, { signal: controller.signal }).then(items => {
      setMaterials(items); setMaterialId(items[0]?.id ?? '');
    }).catch(report).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [courseId]);

  useEffect(() => {
    setKnowledgeReady(false);
    if (!courseId) return;
    const controller = new AbortController();
    request<KnowledgeVersion[]>(`/api/courses/${courseId}/knowledge/versions`, { signal: controller.signal })
      .then(versions => setKnowledgeReady(versions.some(version => version.is_current)))
      .catch(() => setKnowledgeReady(false));
    return () => controller.abort();
  }, [courseId, workspace]);

  useEffect(() => {
    setDetail(null); setFragments([]); setChapterId(''); setSource(null);
    if (!courseId || !materialId) return;
    const controller = new AbortController();
    request<MaterialDetail>(materialUrl(courseId, materialId), { signal: controller.signal }).then(value => {
      setDetail(value);
    }).catch(report);
    return () => controller.abort();
  }, [courseId, materialId]);

  useEffect(() => {
    setFragments([]);
    if (!detail) return;
    const controller = new AbortController();
    setReading(true);
    const query = chapterId ? `?chapter_id=${encodeURIComponent(chapterId)}` : '';
    request<Fragment[]>(materialUrl(detail.course_id, detail.id) + '/fragments' + query, { signal: controller.signal }).then(setFragments).catch(report)
      .finally(() => { if (!controller.signal.aborted) setReading(false); });
    return () => controller.abort();
  }, [detail, chapterId]);

  async function createCourse(event: React.FormEvent) {
    event.preventDefault(); setSaving(true); setError('');
    try {
      const created = await request<Course>('/api/courses', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: courseName }) });
      setCourses(items => [...items, created]); setCourseId(created.id); setCreating(false); setCourseName('');
    } catch (error) { report(error); } finally { setSaving(false); }
  }

  async function upload(file?: File) {
    if (!file || !courseId) return;
    if (!file.name.toLowerCase().endsWith('.md')) { setError('请选择 Markdown（.md）文件。'); return; }
    if (file.size > 20 * 1024 * 1024) { setError('单份资料不能超过 20 MB。'); return; }
    const targetCourse = courseId;
    const controller = new AbortController(); uploadController.current = controller;
    setUploading(true); setError(''); setNotice('');
    try {
      const result = await request<Material>(`/api/courses/${targetCourse}/materials?filename=${encodeURIComponent(file.name)}`, { method: 'POST', body: file, signal: controller.signal });
      if (currentCourse.current !== targetCourse) return;
      setMaterials(items => [...items, result]); setMaterialId(result.id);
      setCourses(items => items.map(c => c.id === targetCourse ? { ...c, material_count: c.material_count + 1 } : c));
      setNotice('资料已保存，可以按章节阅读原文。当前尚未进行知识整理。');
    } catch (error) { report(error); } finally {
      if (uploadController.current === controller) setUploading(false);
      if (uploadRef.current) uploadRef.current.value = '';
    }
  }

  return <div className="app-shell">
    <aside className="sidebar">
      <a className="brand" href="/" aria-label="课程学习空间首页"><span className="brand-mark"><Icon name="book" size={25} /></span><span>课程学习空间<small>COURSE WORKSPACE</small></span></a>
      <div className="sidebar-label">我的课程 <span>{courses.length.toString().padStart(2, '0')}</span></div>
      <nav className="course-list" aria-label="课程">{courses.map((c, i) => <button key={c.id} className={`course-button ${c.id === courseId ? 'active' : ''}`} onClick={() => { setError(''); setCourseId(c.id); }} aria-current={c.id === courseId ? 'page' : undefined}>
        <span className="course-monogram">{String(i + 1).padStart(2, '0')}</span><span className="course-name">{c.name}<small>{c.material_count} 份学习资料</small></span><Icon name="arrow" size={14} />
      </button>)}</nav>
      <button className="new-course" onClick={() => setCreating(true)}><Icon name="plus" size={17} />新建课程</button>
      <div className="sidebar-footer"><span className="status-dot" />本机学习空间<p>资料保存在这台电脑，<br />随时回来继续阅读。</p></div>
    </aside>

    <main>
      <header className="topbar"><span>我的学习空间 <span className="breadcrumb-slash">/</span> <strong>{course?.name ?? '欢迎'}</strong></span>
        <nav className="workspace-tabs" aria-label="工作区视图">
          <button className={workspace === 'materials' ? 'active' : ''} onClick={() => setWorkspace('materials')}>资料阅读</button>
          <button className={workspace === 'knowledge' ? 'active' : ''} onClick={() => setWorkspace('knowledge')}>知识图谱</button>
          <button className={workspace === 'ask' ? 'active' : ''} onClick={() => setWorkspace('ask')}>问答</button>
          <button className={workspace === 'notes' ? 'active' : ''} onClick={() => setWorkspace('notes')}>笔记</button>
          <button className={workspace === 'route' ? 'active' : ''} onClick={() => setWorkspace('route')}>路线</button>
          <button className={workspace === 'feedback' ? 'active' : ''} onClick={() => setWorkspace('feedback')}>反馈</button>
          <button className={workspace === 'export' ? 'active' : ''} onClick={() => setWorkspace('export')}>导出</button>
        </nav>
        <span className="local-badge">LOCAL · 本机</span></header>
      <div className="workspace">
        {workspace === 'knowledge' ? (<>
          <div className="page-heading"><div><div className="eyebrow">COURSE KNOWLEDGE</div><h1>{course?.name ?? '课程知识'}</h1><p>章节与知识点、包含 / 前置 / 对比关系，以及可核查的原文依据。</p></div></div>
          {courseId ? <KnowledgeWorkspace key={courseId} courseId={courseId} /> : <div className="empty-state">请先创建或选择一门课程。</div>}
        </>) : workspace !== 'materials' ? (<>
          <div className="page-heading"><div><div className="eyebrow">LEARNING WORKSPACE</div><h1>{course?.name ?? '学习工作区'}</h1><p>带依据问答、个人笔记、学习路线与可移植资料包。</p></div></div>
          {courseId ? <LearningWorkspace courseId={courseId} materials={materials} detail={detail} view={workspace} /> : <div className="empty-state">请先创建或选择一门课程。</div>}
        </>) : (<>
        <div className="page-heading"><div><div className="eyebrow">LEARNING MATERIALS</div><h1>{course?.name ?? '从一门课程开始'}</h1><p>{course ? '教材、课堂笔记与补充材料，在这里集中阅读。' : '建立自己的学习空间，把散落的资料放在一起。'}</p></div>
          <button className="primary" disabled={uploading || !courseId} onClick={() => uploadRef.current?.click()}><Icon name="upload" size={18} />{uploading ? '正在导入…' : '导入 Markdown'}</button>
          <input ref={uploadRef} className="visually-hidden" type="file" accept=".md,text/markdown" aria-label="选择 Markdown 文件" onChange={e => void upload(e.target.files?.[0])} />
        </div>
        {error && !creating && <div className="message error" role="alert"><span>{error}</span><button onClick={() => setError('')} aria-label="关闭错误提示"><Icon name="close" size={16} /></button></div>}
        {notice && <div className="message success" role="status">{notice}</div>}
        <div className="section-bar"><h2>课程资料 <span>{materials.length}</span></h2><span>保留原文 · 按章节阅读</span></div>

        {loading ? <div className="empty-state" role="status">正在读取学习空间…</div> : !materials.length ? <section className="empty-state">
          <div className="empty-book"><Icon name="book" size={45} /></div><div className="eyebrow">A PLACE FOR YOUR KNOWLEDGE</div>
          <h2>{course ? '放入你的第一份学习资料' : '为这学期的学习留一个位置'}</h2>
          <p>{course ? '上传 Markdown 教材或笔记，按章节浏览，随时核查原文。' : '每门课程独立保存资料，从操作系统或你正在学习的课程开始。'}</p>
          <button className="primary" onClick={() => course ? uploadRef.current?.click() : setCreating(true)} disabled={uploading}><Icon name={course ? 'upload' : 'plus'} size={18} />{course ? '选择 Markdown 文件' : '创建第一门课程'}</button>
          <div className="empty-footnote">支持 UTF-8 Markdown · 单份最大 20 MB</div>
        </section> : <div className="materials-layout">
          <aside className="material-sidebar" aria-label="资料和章节"><div className="pane-label">已导入资料</div>
            {materials.map(m => <button className={`material-button ${m.id === materialId ? 'selected' : ''}`} key={m.id} onClick={() => setMaterialId(m.id)}><Icon name="file" size={19} /><span>{m.filename}<small>{(m.byte_size / 1024).toFixed(1)} KB · 已导入</small></span></button>)}
            {detail && <><div className="pane-label toc-title">章节目录 <span>{detail.chapters.length}</span></div><nav className="toc" aria-label="章节目录"><button className={!chapterId ? 'selected' : ''} onClick={() => setChapterId('')}>全部原文</button>{detail.chapters.map(chapter => <button key={chapter.id} className={chapterId === chapter.id ? 'selected' : ''} style={{ paddingLeft: `${12 + (chapter.level - 1) * 10}px` }} onClick={() => setChapterId(chapter.id)}>{chapter.title}</button>)}</nav></>}
          </aside>
          <article className="reader" aria-label="资料正文">
            {detail ? <><div className="reader-toolbar"><div className="view-tabs" aria-label="阅读模式"><button className={readerMode === 'read' ? 'selected' : ''} onClick={() => setReaderMode('read')}>阅读</button><button className={readerMode === 'source' ? 'selected' : ''} onClick={() => setReaderMode('source')}>原文</button></div><a className="download-link" href={materialUrl(courseId, materialId) + '/raw'}>下载原始文件 ↗</a></div>
              <div className="document-heading"><div className="document-meta"><span className={`imported-badge ${knowledgeReady ? 'ready' : ''}`}>{knowledgeReady ? '已整理 · 知识图谱可用' : '已导入 · 尚未整理'}</span><span>{detail.fragment_count} 个原文片段</span></div><h2>{detail.filename.replace(/\.md$/i, '')}</h2><p>保留上传内容，章节目录依据原文编号组织。</p>{detail.missing_image_count > 0 && <div className="image-notice">资料引用了 {detail.missing_image_count} 张未导入的图片，阅读时会标出缺失位置。</div>}</div>
              {reading ? <div className="reading-placeholder" role="status">正在读取原文…</div> : readerMode === 'read' ? <ReadingContent fragments={fragments} onSource={setSource} /> : <div className="raw-content">{fragments.map(fragment => <section key={fragment.id}><div className="raw-line-label">第 {fragment.start_line}—{fragment.end_line} 行</div><pre>{fragment.markdown}</pre></section>)}</div>}
              <footer className="reader-footer">{knowledgeReady ? '原文片段可追溯到上传文件 · 课程已发布知识版本，可在「知识图谱」查看' : '原文片段可追溯到上传文件 · 此页展示学习资料，尚未整理为课程知识'}</footer>
            </> : <div className="reading-placeholder">正在打开资料…</div>}
          </article>
        </div>}
        </>)}
      </div>
    </main>
    {creating && <Modal title="新建课程" onClose={() => { if (!saving) setCreating(false); }}><form onSubmit={event => void createCourse(event)}><label htmlFor="course-name">课程名称</label><input id="course-name" autoFocus required maxLength={120} placeholder="例如：计算机操作系统" value={courseName} onChange={e => setCourseName(e.target.value)} /><p className="form-help">每门课程分别保存自己的资料与学习内容。</p>{error && <p className="message error" role="alert">{error}</p>}<button className="primary" type="submit" disabled={saving || !courseName.trim()}>{saving ? '正在创建…' : '创建课程'}</button></form></Modal>}
    {source && detail && <Modal title="原文依据" onClose={() => setSource(null)}><div className="source-meta">{detail.filename}<br />第 {source.start_line}—{source.end_line} 行</div><pre className="source-original">{source.markdown}</pre><p className="form-help">上方文字直接来自上传资料，保留原始 Markdown。</p></Modal>}
  </div>;
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><App /></React.StrictMode>);
