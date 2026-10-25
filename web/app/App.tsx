import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { request, type Course } from '../api';
import { MaterialsWorkspace } from '../features/materials/MaterialsWorkspace';
import { NotesWorkspace } from '../features/notes/NotesWorkspace';
import { KnowledgeWorkspace } from '../features/knowledge/KnowledgeWorkspace';
import { Icon } from '../shared/Icon';
import { Modal } from '../shared/Modal';
import './app.css';

function CreateCourseDialog({ onCreated, onClose }: {
  onCreated: (course: Course) => void;
  onClose: () => void;
}) {
  const [name, setName] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  async function createCourse(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError('');
    try {
      const course = await request<Course>('/api/courses', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      });
      onCreated(course);
    } catch (error) {
      if (error instanceof Error) setError(error.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal title="新建课程" onClose={() => { if (!saving) onClose(); }}>
      <form onSubmit={event => void createCourse(event)}>
        <label htmlFor="course-name">课程名称</label>
        <input id="course-name" autoFocus required maxLength={120} placeholder="例如：计算机操作系统" value={name} onChange={event => setName(event.target.value)} />
        <p className="form-help">每门课程分别保存自己的资料与学习内容。</p>
        {error && <p className="message error" role="alert">{error}</p>}
        <button className="primary" type="submit" disabled={saving || !name.trim()}>{saving ? '正在创建…' : '创建课程'}</button>
      </form>
    </Modal>
  );
}

export function App() {
  const [courses, setCourses] = useState<Course[]>([]);
  const [courseId, setCourseId] = useState('');
  const [creating, setCreating] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const course = courses.find(item => item.id === courseId);
  const [workspace, setWorkspace] = useState<'materials' | 'knowledge' | 'notes'>('materials');
  const [notesOpened, setNotesOpened] = useState(false);
  const [knowledgeOpened, setKnowledgeOpened] = useState(false);
  const [selectedNoteId, setSelectedNoteId] = useState<string | null>(null);
  const [dirtyNote, setDirtyNote] = useState(false);
  function chooseCourse(id: string) {
    if (id === courseId) return;
    if (dirtyNote && !window.confirm('当前笔记有未保存的修改，确定丢弃草稿并切换课程吗？')) return;
    setCourseId(id); setDirtyNote(false); setSelectedNoteId(null);
  }
  function openNotes(id?: string) {
    setSelectedNoteId(id ?? null); setNotesOpened(true); setWorkspace('notes');
  }
  const syncMaterialCount = useCallback((targetCourse: string, count: number) => {
    setCourses(items => items.map(item => item.id === targetCourse ? { ...item, material_count: count } : item));
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    request<Course[]>('/api/courses', { signal: controller.signal }).then(items => {
      if (controller.signal.aborted) return;
      setCourses(items);
      const saved = localStorage.getItem('campus-course');
      setCourseId(items.find(item => item.id === saved)?.id ?? items[0]?.id ?? '');
    }).catch(error => {
      if (!controller.signal.aborted && error instanceof Error) setError(error.message);
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (courseId) localStorage.setItem('campus-course', courseId);
  }, [courseId]);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="/" aria-label="课程学习空间首页"><span className="brand-mark"><Icon name="book" size={25} /></span><span>课程学习空间<small>COURSE WORKSPACE</small></span></a>
        <div className="sidebar-label">我的课程 <span>{courses.length.toString().padStart(2, '0')}</span></div>
        <nav className="course-list" aria-label="课程">
          {courses.map((item, index) => (
            <button key={item.id} className={`course-button ${item.id === courseId ? 'active' : ''}`} onClick={() => chooseCourse(item.id)} aria-current={item.id === courseId ? 'page' : undefined}>
              <span className="course-monogram">{String(index + 1).padStart(2, '0')}</span>
              <span className="course-name">{item.name}<small>{item.material_count} 份学习资料</small></span>
              <Icon name="arrow" size={14} />
            </button>
          ))}
        </nav>
        <button className="new-course" onClick={() => { if (!dirtyNote || window.confirm('当前笔记有未保存的修改，确定新建并切换课程吗？')) setCreating(true); }}><Icon name="plus" size={17} />新建课程</button>
        <div className="sidebar-footer"><span className="status-dot" />本机学习空间<p>资料保存在这台电脑，<br />随时回来继续阅读。</p></div>
      </aside>
      <main>
        <header className="topbar">
          <span>我的学习空间 <span className="breadcrumb-slash">/</span> <strong>{course?.name ?? '欢迎'}</strong></span>
          {course && <nav className="workspace-tabs" aria-label="课程工作区">
            <button className={workspace === 'materials' ? 'active' : ''} onClick={() => setWorkspace('materials')}>资料阅读</button>
            <button className={workspace === 'knowledge' ? 'active' : ''} onClick={() => { setKnowledgeOpened(true); setWorkspace('knowledge'); }}>知识图谱</button>
            <button className={workspace === 'notes' ? 'active' : ''} onClick={() => openNotes()}>个人笔记</button>
          </nav>}
          <span className="local-badge">LOCAL · 本机</span>
        </header>
        <div className="workspace">
          {error && <div className="message error" role="alert">{error}</div>}
          {loading ? <div className="empty-state" role="status">正在读取学习空间…</div> : course ? (
            <>
              {knowledgeOpened && <div hidden={workspace !== 'knowledge'}>
                <div className="page-heading"><div><div className="eyebrow">COURSE KNOWLEDGE</div><h1>{course.name}</h1><p>沿着关系理解课程，回到原文核对，也可以提问并记录自己的理解。</p></div></div>
                <KnowledgeWorkspace key={course.id} courseId={course.id} onOpenNotes={openNotes} />
              </div>}
              {notesOpened && <div hidden={workspace !== 'notes'}>
                <div className="page-heading"><div><div className="eyebrow">PERSONAL NOTES</div><h1>{course.name} · 个人笔记</h1><p>保存自己的理解，保留原文依据与模型补充标记。</p></div></div>
                <NotesWorkspace key={course.id} courseId={course.id} selectedNoteId={selectedNoteId} active={workspace === 'notes'} onDirtyChange={setDirtyNote} />
              </div>}
              {workspace === 'materials' && <MaterialsWorkspace key={course.id} course={course} onMaterialCountChange={syncMaterialCount} />}
            </>
          ) : (
            <>
              <div className="page-heading"><div><div className="eyebrow">LEARNING MATERIALS</div><h1>从一门课程开始</h1><p>建立自己的学习空间，把散落的资料放在一起。</p></div></div>
              <section className="empty-state welcome-state">
                <div className="empty-book"><Icon name="book" size={45} /></div>
                <div className="eyebrow">A PLACE FOR YOUR KNOWLEDGE</div>
                <h2>为这学期的学习留一个位置</h2>
                <p>每门课程独立保存资料，从操作系统或你正在学习的课程开始。</p>
                <button className="primary" onClick={() => { if (!dirtyNote || window.confirm('当前笔记有未保存的修改，确定新建并切换课程吗？')) setCreating(true); }}><Icon name="plus" size={18} />创建第一门课程</button>
                <div className="empty-footnote">支持 UTF-8 Markdown · 单份最大 20 MB</div>
              </section>
            </>
          )}
        </div>
      </main>
      {creating && <CreateCourseDialog onClose={() => setCreating(false)} onCreated={created => {
        setCourses(items => [...items, created]);
        setCourseId(created.id); setDirtyNote(false); setSelectedNoteId(null);
        setWorkspace('materials');
        setCreating(false);
      }} />}
    </div>
  );
}
