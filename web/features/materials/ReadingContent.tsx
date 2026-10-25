import { useEffect, useRef } from 'react';
import katex from 'katex';
import 'katex/dist/katex.min.css';
import type { Fragment } from '../../api';

export function ReadingContent({ fragments, onSource }: { fragments: Fragment[]; onSource: (fragment: Fragment) => void }) {
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
