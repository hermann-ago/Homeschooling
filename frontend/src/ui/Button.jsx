import clsx from 'clsx';
import { buttonClasses } from './classes';

/**
 * The app's button. `as` renders another element with the same look, for
 * example a router Link: <Button as={Link} to="/plan">Open plan</Button>.
 */
export default function Button({ as: Component = 'button', variant, size, icon: Icon, className, children, ...props }) {
  const extra = Component === 'button' ? { type: props.type || 'button' } : {};
  return (
    <Component {...extra} {...props} className={buttonClasses({ variant, size, className })}>
      {Icon && <Icon aria-hidden="true" className="w-[18px] h-[18px] shrink-0" />}
      {children}
    </Component>
  );
}

/** A square button with only an icon; `label` is read out by screen readers. */
export function IconButton({ icon, label, variant = 'secondary', size = 'md', className, ...props }) {
  const Icon = icon;
  const square = { sm: 'w-10 px-0', md: 'w-11 px-0', lg: 'w-12 px-0' }[size];
  return (
    <button type="button" aria-label={label} title={label} {...props}
      className={buttonClasses({ variant, size, className: clsx(square, className) })}>
      <Icon aria-hidden="true" className="w-5 h-5" />
    </button>
  );
}
