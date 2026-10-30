import { useEffect, useRef } from 'react';
import { MoreHorizontal } from 'lucide-react';

/** A keyboard-accessible menu anchored to the tutor header, outside the thread. */
export default function LessonOptions({ children, label = 'Lesson options', icon: Icon = MoreHorizontal }) {
  const menu = useRef(null);
  useEffect(() => {
    const close = (event) => {
      if (!menu.current?.open) return;
      if (event.type === 'keydown' && event.key === 'Escape') {
        menu.current.open = false;
        menu.current.querySelector('summary')?.focus();
      } else if (event.type === 'pointerdown' && !menu.current.contains(event.target)) menu.current.open = false;
    };
    document.addEventListener('pointerdown', close);
    document.addEventListener('keydown', close);
    return () => { document.removeEventListener('pointerdown', close); document.removeEventListener('keydown', close); };
  }, []);
  return <details ref={menu} className="lesson-options">
    <summary aria-label={label} title={label}><Icon size={20} aria-hidden="true" /><span className="sr-only">{label}</span></summary>
    <div className="lesson-options-content" onClick={(event) => {
      if (event.target.closest('[data-close-options]')) menu.current.open = false;
    }}>{children}</div>
  </details>;
}
