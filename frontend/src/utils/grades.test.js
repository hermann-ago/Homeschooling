import { describe, expect, it } from 'vitest';
import { folderLabel, gradeLabel, gradeOptions, sameGrade } from './grades';

describe('grades', () => {
  it('reads grades the way the family says them', () => {
    expect(['3rd', 'K', 'Pre-K', 'N/A', '', null].map(gradeLabel))
      .toEqual(['3rd grade', 'Kindergarten', 'Pre-K', 'No grade', 'No grade', 'No grade']);
  });

  it('names the folder like the home server does', () => {
    expect(folderLabel('Lucas', '4th', 'Math')).toBe('Lucas › 4th Grade › Math');
    expect(folderLabel('Olivia', 'Pre-K', 'Math')).toBe('Olivia › Pre-K › Math');
    expect(folderLabel('Joshua', 'N/A', 'Reading')).toBe('Joshua › Reading');
  });

  it('keeps an unusual current grade among the choices', () => {
    expect(gradeOptions('Year 5').map((o) => o.value)).toContain('Year 5');
    expect(gradeOptions('4th').filter((o) => o.value === '4th')).toHaveLength(1);
  });

  it('treats every way of saying "no grade" as the same', () => {
    expect(sameGrade('N/A', '')).toBe(true);
    expect(sameGrade('3rd', '4th')).toBe(false);
  });
});
