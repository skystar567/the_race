import { useEffect, useRef, useState } from 'react';
import katex from 'katex';
import { request, type SourceDetail } from '../api';
import './study.css';

export function useMath(ref: React.RefObject<HTMLElement | null>, html: string | undefined) {
  useEffect(() => {
    ref.current?.querySelectorAll<HTMLElement>('[data-math]').forEach(element => {
      katex.render(element.dataset.math ?? '', element, {
        displayMode: element.dataset.display === 'true', throwOnError: false, trust: false, strict: 'ignore',
      });
    });
  }, [ref, html]);
}

// One lifetime per keyed course/target panel; every asynchronous path checks it.
export function useRequestScope() {
  const scope = useRef(new AbortController());
  useEffect(() => {
    if (scope.current.signal.aborted) scope.current = new AbortController();
    const controller = scope.current;
    return () => controller.abort();
  }, []);
  return scope;
}

export class StudyError extends Error {
  constructor(message: string, public status: number) { super(message); }
}

export async function studyRequest<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  const body = await response.json();
  if (!response.ok) throw new StudyError(typeof body.detail === 'string' ? body.detail : `请求失败（${response.status}）`, response.status);
  return body as T;
}

export function SourcePreview({ url, onClose }: { url: string; onClose: () => void }) {
  const [source, setSource] = useState<SourceDetail | null>(null);
  const [error, setError] = useState('');
  const dialog = useRef<HTMLDialogElement>(null);
  const content = useRef<HTMLDivElement>(null);
  useMath(content, source?.html);
  useEffect(() => {
    const controller = new AbortController();
    setSource(null); setError('');
    request<SourceDetail>(url, { signal: controller.signal }).then(value => {
      if (!controller.signal.aborted) setSource(value);
    }).catch(cause => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : '无法读取原文。'); });
    return () => controller.abort();
  }, [url]);
  useEffect(() => { const element = dialog.current; element?.showModal(); return () => element?.close(); }, []);
  return <dialog ref={dialog} className="source-dialog" aria-label="原文依据"
    onCancel={event => { event.preventDefault(); onClose(); }} onClick={event => { if (event.target === dialog.current) onClose(); }}>
    <div className="modal-head"><h2>原文依据</h2><button className="icon-button" aria-label="关闭" onClick={onClose}>×</button></div>
    {error && <p className="message error" role="alert">{error}</p>}
    {!source && !error && <p role="status">正在读取原文…</p>}
    {source && <><p className="source-meta">{source.filename} · {source.chapter_title} · 第 {source.start_line}—{source.end_line} 行 · 版本 {source.version_id.slice(0, 8)}</p>
      <div ref={content} className="reading-content compact" dangerouslySetInnerHTML={{ __html: source.html }} />
      <details><summary>查看原始 Markdown</summary><pre className="source-original">{source.markdown}</pre></details>
      <p className="form-help">内容来自本次学习使用的固定原文，未经模型改写。</p></>}
  </dialog>;
}
