import { Field, inputClasses } from '../ui';
import { NO_GRADE, gradeOptions } from '../utils/grades';

/** A labelled grade picker (Pre-K … 12th, or no grade). */
export default function GradeSelect({ label = 'Grade', value, onChange, hint, className }) {
  const current = value || NO_GRADE;
  return (
    <Field label={label} hint={hint} className={className}>
      <select className={inputClasses} value={current} onChange={(e) => onChange(e.target.value)}>
        {gradeOptions(current).map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
      </select>
    </Field>
  );
}
