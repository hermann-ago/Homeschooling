import clsx from 'clsx';

const VARIANTS = {
  primary: 'bg-action text-white hover:bg-action-hover',
  strong: 'bg-ink text-white hover:bg-black',
  secondary: 'bg-surface text-ink border border-line hover:bg-paper',
  quiet: 'bg-transparent text-action hover:bg-action-soft',
  danger: 'bg-surface text-problem border border-line hover:bg-problem-soft',
};

const SIZES = {
  sm: 'h-10 px-3.5 text-sm rounded-[10px] gap-2',
  md: 'h-11 px-4 text-[15px] rounded-xl gap-2',
  lg: 'h-12 px-5 text-[15px] rounded-xl gap-2.5',
};

/** The button look, for elements that must not be a <Button> (a label for a file input, say). */
export const buttonClasses = ({ variant = 'secondary', size = 'md', className } = {}) => clsx(
  'inline-flex items-center justify-center font-semibold whitespace-nowrap transition-colors',
  'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-action',
  'disabled:opacity-50 disabled:cursor-not-allowed',
  VARIANTS[variant], SIZES[size], className,
);

/** The text-input look, shared by inputs, selects and date fields. */
export const inputClasses = 'h-11 w-full box-border px-3 rounded-[10px] border border-line bg-surface text-[15px] text-ink '
  + 'focus:outline-2 focus:outline-offset-0 focus:outline-action disabled:opacity-60';
