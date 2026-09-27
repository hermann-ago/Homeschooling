import { useEffect, useId, useRef } from 'react';
import { X } from 'lucide-react';
import { IconButton } from './Button';

/**
 * A modal dialog built on the browser's own <dialog>, so focus stays inside it
 * and Escape closes it. Put the action buttons in `footer`.
 */
export default function Dialog({ open, onClose, title, description, footer, children, width = 480 }) {
  const ref = useRef(null);
  const titleId = useId();
  const descriptionId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      if (dialog.showModal) dialog.showModal();
      else dialog.setAttribute('open', '');
    } else if (!open && dialog.open) {
      if (dialog.close) dialog.close();
      else dialog.removeAttribute('open');
    }
  }, [open]);

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      aria-describedby={description ? descriptionId : undefined}
      onCancel={(event) => { event.preventDefault(); onClose?.(); }}
      onClick={(event) => { if (event.target === ref.current) onClose?.(); }}
      style={{ width }}
      className="m-auto max-w-[calc(100vw-32px)] rounded-2xl bg-surface p-0 text-ink shadow-2xl backdrop:bg-ink/40"
    >
      {open && (
        <div className="flex flex-col">
          <header className="flex items-start gap-4 px-6 pt-6 pb-4">
            <div className="flex-1 min-w-0">
              <h2 id={titleId} className="text-lg font-bold">{title}</h2>
              {description && <p id={descriptionId} className="mt-1 text-sm text-muted">{description}</p>}
            </div>
            <IconButton icon={X} label="Close" variant="quiet" size="sm" onClick={onClose} className="-mr-2 -mt-1 text-muted" />
          </header>
          {children && <div className="px-6 pb-4">{children}</div>}
          {footer && <footer className="flex justify-end gap-2 px-6 py-4 bg-paper rounded-b-2xl">{footer}</footer>}
        </div>
      )}
    </dialog>
  );
}
