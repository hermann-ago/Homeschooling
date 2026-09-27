/* @vitest-environment jsdom */
import React from 'react';
import { QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({
  children: { getAll: vi.fn() },
  checklist: { getToday: vi.fn(), getWeek: vi.fn(), getMissed: vi.fn(), completeSlot: vi.fn(), uncompleteSlot: vi.fn() },
  progress: { getChildProgress: vi.fn(), getFamilyOverview: vi.fn() },
  scheduler: { getSchedule: vi.fn(), recalculate: vi.fn() },
}));
vi.mock('../api/children', () => ({ childrenApi: api.children }));
vi.mock('../api/checklist', () => ({ checklistApi: api.checklist }));
vi.mock('../api/progress', () => ({ progressApi: api.progress }));
vi.mock('../api/scheduler', () => ({ schedulerApi: api.scheduler }));

import { createQueryClient } from '../api/queries';
import LearnerProvider from '../app/LearnerProvider';
import { FeedbackProvider } from '../ui/feedback';
import Today from './Today';

const LUCAS = { id: 1, name: 'Lucas', color: '#4A90D9', grade_year: '3rd' };
const MILA = { id: 2, name: 'Mila', color: '#E88AB5', grade_year: '1st' };
const slot = (id, child, subject, title, start, end, extra = {}) => ({
  id, child_id: child, subject_id: 1, topic_id: 100 + id, subject_name: subject, topic_title: title,
  date: '2026-09-28', time_start: start, time_end: end, page_from: 1, page_to: 2, is_completed: false, ...extra,
});

function renderToday() {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <FeedbackProvider>
        <MemoryRouter><LearnerProvider><Today /></LearnerProvider></MemoryRouter>
      </FeedbackProvider>
    </QueryClientProvider>,
  );
}

describe('Today', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date(2026, 8, 28, 8, 40));  // Monday 8:40
    localStorage.clear();
    api.children.getAll.mockResolvedValue([LUCAS, MILA]);
    api.progress.getFamilyOverview.mockResolvedValue({ children: [
      { child_id: 1, subjects: [{ subject_id: 1 }] }, { child_id: 2, subjects: [{ subject_id: 2 }] },
    ] });
    api.progress.getChildProgress.mockResolvedValue({ subjects: [] });
    api.checklist.getToday.mockImplementation(async (child) => (child === 1
      ? [slot(1, 1, 'History', 'The Rus Come to Constantinople', '08:00', '09:00'), slot(2, 1, 'Language Arts', 'Lesson 71', '09:00', '10:00')]
      : [slot(3, 2, 'Math', 'Lesson 105', '08:45', '09:30')]));
    api.checklist.getMissed.mockImplementation(async (child) => (child === 1 ? [slot(9, 1, 'History', 'Marco Polo', '08:00', '09:00', { date: '2026-09-22' })] : []));
    api.checklist.getWeek.mockResolvedValue([]);
    api.scheduler.getSchedule.mockResolvedValue([]);
    api.checklist.completeSlot.mockResolvedValue({});
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    Object.values(api).forEach((group) => Object.values(group).forEach((fn) => fn.mockReset()));
  });

  it('shows every learner with the lesson happening now', async () => {
    renderToday();
    expect(await screen.findByText('Good morning')).toBeTruthy();
    expect(await screen.findByText('The Rus Come to Constantinople')).toBeTruthy();
    expect(screen.getByText(/3 lessons for 2 learners · 0 done/)).toBeTruthy();
    expect(screen.getAllByText('Now')).toHaveLength(1);  // Lucas's History
    expect(screen.getAllByText('Next')).toHaveLength(1); // Mila's Math starts at 8:45
    expect(screen.getByText('1 lesson was planned before today and not marked done.')).toBeTruthy();
  });

  it('gives one learner a Now card and marks a lesson done', async () => {
    localStorage.setItem('homeschool:learner', '1');
    renderToday();
    expect(await screen.findByText("Lucas's Monday")).toBeTruthy();
    const nowCard = (await screen.findByText('NOW · 8:00–9:00')).closest('article');
    expect(within(nowCard).getByText('The Rus Come to Constantinople')).toBeTruthy();

    fireEvent.click(within(nowCard).getByRole('button', { name: 'Mark done' }));
    await waitFor(() => expect(api.checklist.completeSlot).toHaveBeenCalledWith(1));
  });
});
