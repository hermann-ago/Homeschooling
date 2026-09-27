import clsx from 'clsx';
import { Check } from 'lucide-react';

/**
 * The round "done" button on a lesson. `current` gives the ring the learner's
 * colour; `done` fills it. `label` names the lesson for screen readers.
 */
export default function CheckButton({ done = false, current = false, color = '#2d5f54', label, size = 36, onToggle, disabled }) {
  return (
    <button
      type="button"
      aria-pressed={done}
      aria-label={done ? `${label}: done. Mark as not done` : `Mark ${label} done`}
      disabled={disabled}
      onClick={() => onToggle?.(!done)}
      style={{ width: size, height: size, ...(done ? { background: color } : { borderColor: current ? color : undefined }) }}
      className={clsx(
        'shrink-0 rounded-full flex items-center justify-center transition-transform active:scale-90',
        'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-action disabled:opacity-50',
        done ? 'text-white' : 'border-2 bg-surface',
        !done && !current && 'border-line hover:border-muted',
      )}
    >
      {done && <Check aria-hidden="true" strokeWidth={2.6} className="w-1/2 h-1/2" />}
    </button>
  );
}
