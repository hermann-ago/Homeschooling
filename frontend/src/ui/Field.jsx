import clsx from 'clsx';
import { inputClasses } from './classes';

/** A labelled form control: <Field label="Name"><input … /></Field>, or pass input props directly. */
export default function Field({ label, hint, className, children, ...inputProps }) {
  return (
    <label className={clsx('flex flex-col gap-1.5 text-[13px] font-semibold text-muted', className)}>
      {label}
      {children ?? <input className={inputClasses} {...inputProps} />}
      {hint && <span className="text-[13px] font-normal text-subtle">{hint}</span>}
    </label>
  );
}
