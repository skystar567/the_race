export function Icon({ name, size = 20 }: { name: 'book' | 'plus' | 'upload' | 'file' | 'arrow' | 'close'; size?: number }) {
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
