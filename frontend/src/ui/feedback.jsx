import { useCallback, useRef, useState } from 'react';
import clsx from 'clsx';
import Button from './Button';
import Dialog from './Dialog';
import { FeedbackContext } from './useFeedback';

/** Provides useConfirm() and useToast() to everything inside it. */
export function FeedbackProvider({ children }) {
  const [request, setRequest] = useState(null);
  const [toasts, setToasts] = useState([]);
  const nextId = useRef(0);

  const confirm = useCallback((options) => new Promise((resolve) => setRequest({ ...options, resolve })), []);
  const answer = (value) => { request?.resolve(value); setRequest(null); };

  const toast = useCallback((input) => {
    const item = typeof input === 'string' ? { message: input } : input;
    const id = (nextId.current += 1);
    setToasts((list) => [...list, { tone: 'neutral', ...item, id }]);
    window.setTimeout(() => setToasts((list) => list.filter((t) => t.id !== id)), item.duration ?? 5000);
  }, []);

  return (
    <FeedbackContext.Provider value={{ confirm, toast }}>
      {children}
      <Dialog
        open={Boolean(request)}
        onClose={() => answer(false)}
        title={request?.title}
        description={request?.description}
        footer={request && (
          <>
            <Button onClick={() => answer(false)}>{request.cancelLabel || 'Cancel'}</Button>
            <Button variant={request.danger ? 'danger' : 'primary'} onClick={() => answer(true)}>
              {request.confirmLabel || 'OK'}
            </Button>
          </>
        )}
      />
      <div role="status" aria-live="polite" className="fixed bottom-6 right-6 z-50 flex flex-col gap-2 items-end pointer-events-none">
        {toasts.map((t) => (
          <div key={t.id} className={clsx(
            'pointer-events-auto max-w-sm rounded-xl px-4 py-3 text-sm font-medium shadow-lg',
            t.tone === 'problem' ? 'bg-problem text-white' : 'bg-ink text-white',
          )}>
            {t.message}
          </div>
        ))}
      </div>
    </FeedbackContext.Provider>
  );
}
