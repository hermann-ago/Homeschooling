import clsx from 'clsx';

/**
 * A rounded bar. `marker` (0–100) draws a thin line, for example where the
 * school year is today, so a subject behind it reads at a glance.
 */
export default function ProgressBar({ value, color = 'var(--color-action)', marker, label, height = 10, className }) {
  const percent = Math.max(0, Math.min(100, value || 0));
  return (
    <div
      role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(percent)}
      className={clsx('relative rounded-full bg-paper-deep', className)} style={{ height }}
    >
      <div className="rounded-full h-full transition-[width] duration-500" style={{ width: `${percent}%`, background: color }} />
      {marker != null && (
        <div aria-hidden="true" className="absolute w-0.5 bg-ink" style={{ left: `${marker}%`, top: -4, bottom: -4 }} />
      )}
    </div>
  );
}
