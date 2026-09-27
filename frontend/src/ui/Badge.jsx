import clsx from 'clsx';

const TONES = {
  neutral: 'bg-paper-deep text-ink',
  action: 'bg-action-soft text-action',
  attention: 'bg-attention-soft text-attention',
  problem: 'bg-problem-soft text-problem',
};

/**
 * A small rounded label. `tone` picks a status colour; `color`/`background`
 * (a learner's strong and soft shades) override it for learner badges.
 */
export default function Badge({ tone = 'neutral', color, background, solid = false, className, children }) {
  const style = color ? (solid ? { background: color, color: '#fff' } : { background, color }) : undefined;
  return (
    <span style={style} className={clsx(
      'inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[13px] font-semibold whitespace-nowrap',
      !color && TONES[tone], className,
    )}>
      {children}
    </span>
  );
}
