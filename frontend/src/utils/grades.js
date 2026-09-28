/** Grades offered in the app; a subject or learner may also keep another value typed earlier. */
export const GRADES = ['Pre-K', 'K', '1st', '2nd', '3rd', '4th', '5th', '6th', '7th', '8th', '9th', '10th', '11th', '12th'];

export const NO_GRADE = 'N/A';

const isNone = (grade) => !grade || ['n/a', 'na', 'none', '-'].includes(String(grade).trim().toLowerCase());
const isOrdinal = (grade) => /^\d+(st|nd|rd|th)$/i.test(String(grade).trim());

/** "3rd" → "3rd grade", "K" → "Kindergarten", "N/A" → "No grade". */
export function gradeLabel(grade) {
  if (isNone(grade)) return 'No grade';
  if (grade === 'K') return 'Kindergarten';
  return isOrdinal(grade) ? `${grade} grade` : grade;
}

/** The Drive folder a subject's files go to, as the home server names it: "Lucas › 4th Grade › Math". */
export function folderLabel(childName, grade, subjectName) {
  const level = isNone(grade) ? null : isOrdinal(grade) ? `${grade} Grade` : grade;
  return [childName, level, subjectName].filter(Boolean).join(' › ');
}

/** The choices for a grade picker, keeping an unusual current value. */
export function gradeOptions(current) {
  const options = [...GRADES];
  if (!isNone(current) && !options.includes(current)) options.push(current);
  return [...options.map((g) => ({ value: g, label: gradeLabel(g) })), { value: NO_GRADE, label: 'No grade' }];
}

export const sameGrade = (a, b) => (isNone(a) && isNone(b)) || String(a || '').trim() === String(b || '').trim();
