/* @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { AttemptNavigation, CatchUpNotice, ClosingSummary, LessonPosition } from './LessonOverview';

afterEach(cleanup);
const reading = { id: 'read', kind: 'read_source', status: 'answered' };
const question = { id: 'question', kind: 'ask_question', status: 'pending', content: { prompt: 'NEVER expose a future prompt' } };
const recap = { id: 'recap', kind: 'close_lesson', status: 'pending' };

it('shows only generic step labels and preserves the position during a help detour or break', () => {
  render(<LessonPosition state={{ activities: [reading, question, recap], active_activity: { id: 'help', parent_activity_id: 'question' }, on_break: true }} />);
  expect(screen.getByText('Step 2 of 3 · On a break')).toBeTruthy();
  expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('2');
  expect(screen.queryByText('NEVER expose a future prompt')).toBeNull();
  expect(screen.getByText('2. Your turn').getAttribute('aria-current')).toBe('step');
});

const summary = { reading: { reached: 1, total: 1 }, answers: { captured: 2, checked: 1 }, help: { activity_count: 1, activity_labels: ['Reading about joining groups'] },
  pending_work: [{ activity_id: 'unfinished', prompt: 'Describe the joined groups.', reason: 'skipped', has_response: false, can_revisit: true }] };

it('counts a practice section once while preserving its active item and help return',()=>{
  const first={...question,id:'word1',practice_section:{id:'words',title:'Spelling practice'}};
  const second={...first,id:'word2'};
  render(<LessonPosition state={{activities:[reading,first,second,recap],active_activity:{id:'help',parent_activity_id:'word2'}}} />);
  expect(screen.getByText('Step 2 of 3')).toBeTruthy();
  expect(screen.getByText('2. Spelling practice').getAttribute('aria-current')).toBe('step');
});

it('shows observed counts and returns directly to unfinished work before finishing', () => {
  const revisit = vi.fn();
  render(<ClosingSummary state={{ learning_summary: summary, status: 'active' }} onRevisit={revisit} />);
  expect(screen.getByText('1 of 2 saved answers')).toBeTruthy();
  fireEvent.click(screen.getByText('Where you used help'));
  expect(screen.getByText('Reading about joining groups')).toBeTruthy();
  expect(screen.getByText('Left to revisit · No answer recorded')).toBeTruthy();
  expect(screen.queryByText(/mastered/i)).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Return to this activity' }));
  expect(revisit).toHaveBeenCalledWith('unfinished');
});

it('offers continuation and the next lesson after saving, without editing the original', () => {
  const repeat = vi.fn();
  render(<ClosingSummary state={{ learning_summary: summary, status: 'completed', attempt_navigation: { next_lesson: { title: 'The next chapter', path: '/lesson?topic=3', resume: false } } }} onRepeat={repeat} />);
  fireEvent.click(screen.getByRole('button', { name: 'Continue unfinished work' }));
  expect(repeat).toHaveBeenCalledTimes(1);
  expect(repeat).toHaveBeenCalledWith({ unfinishedOnly: true });
  expect(screen.getByRole('link', { name: 'Open next lesson' }).getAttribute('href')).toContain('topic=3');
  expect(screen.queryByRole('button', { name: 'Return to this activity' })).toBeNull();
});

it('explains that the original is complete and identifies the saved work already addressed', () => {
  const focus = vi.fn();
  render(<CatchUpNotice state={{ status: 'unfinished', catch_up: { remaining: 0, total: 1,
    original_path: '/lesson?session=original', items: [{ activity_id: 'q5', prompt: 'Workbook page 83, exercise 5.', status: 'answered' }] } }} onFocus={focus} />);
  expect(screen.getByText('Your original lesson is complete')).toBeTruthy();
  expect(screen.getByText(/without repeating the reading/)).toBeTruthy();
  expect(screen.getByText('Workbook page 83, exercise 5.')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Review and finish saved work' }));
  expect(focus).toHaveBeenCalledTimes(1);
});

it('shows manual completion separately from unassessed work without requiring continuation', () => {
  render(<ClosingSummary state={{ learning_summary: summary, status: 'completed', completion_summary: { completion_source: 'manual' } }} />);
  expect(screen.getByText(/Marked complete by you/)).toBeTruthy();
  expect(screen.getByText('Unassessed work')).toBeTruthy();
  expect(screen.getByText('1 of 2 saved answers')).toBeTruthy();
  expect(screen.queryByRole('button', { name: 'Continue unfinished work' })).toBeNull();
});

it('links the original and repeat, marks the current attempt and resumes saved unfinished work', () => {
  const navigation = { attempts: [{ id: 'original', label: 'Original lesson', status: 'completed', path: '/lesson?session=original', current: false }, { id: 'repeat', label: 'Repeat 1', status: 'unfinished', current: true }],
    resume_repeat: { path: '/lesson?session=repeat' } };
  render(<><AttemptNavigation navigation={navigation} /><ClosingSummary state={{ status: 'completed', learning_summary: summary, attempt_navigation: navigation }} /></>);
  expect(within(screen.getByRole('navigation', { name: 'Lesson attempts' })).getByRole('link', { name: 'Original lesson · Saved' }).getAttribute('href')).toContain('session=original');
  expect(screen.getByText('Repeat 1 · You are here').getAttribute('aria-current')).toBe('page');
  expect(screen.getByRole('link', { name: 'Continue unfinished work' }).getAttribute('href')).toContain('session=repeat');
});
