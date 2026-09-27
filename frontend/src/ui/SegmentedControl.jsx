import clsx from 'clsx';

/**
 * A row of mutually exclusive choices (Everyone · Lucas · Mila, Week | Month).
 * options: [{ value, label, dot? }]; `dot` is a colour shown before the label.
 */
export default function SegmentedControl({ options, value, onChange, label, size = 'md', className }) {
  const height = size === 'sm' ? 'h-8 text-[13px]' : 'h-9 text-sm';
  return (
    <div role="group" aria-label={label} className={clsx('inline-flex gap-1.5 p-1 rounded-xl bg-paper-deep', className)}>
      {options.map((option) => {
        const selected = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={selected}
            onClick={() => onChange(option.value)}
            className={clsx(
              height, 'px-3.5 rounded-[9px] inline-flex items-center gap-2 whitespace-nowrap transition-colors',
              'focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-action',
              selected ? 'bg-ink text-white font-semibold' : 'text-ink font-medium hover:bg-surface/70',
            )}
          >
            {option.dot && <span aria-hidden="true" className="w-2.5 h-2.5 rounded-full" style={{ background: option.dot }} />}
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

/** The learner switcher at the top of every screen. `value` is a child id or 'all'. */
export function LearnerSwitcher({ learners, value, onChange, includeEveryone = true }) {
  const options = [
    ...(includeEveryone ? [{ value: 'all', label: 'Everyone' }] : []),
    ...learners.map((child) => ({ value: child.id, label: child.name, dot: child.color })),
  ];
  return <SegmentedControl label="Learner" options={options} value={value} onChange={onChange} />;
}
