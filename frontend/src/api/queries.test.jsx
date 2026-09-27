/* @vitest-environment jsdom */
import React from 'react';
import { QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

const checklist = vi.hoisted(() => ({
  getToday: vi.fn(), getWeek: vi.fn(), getMissed: vi.fn(), completeSlot: vi.fn(), uncompleteSlot: vi.fn(),
}));
vi.mock('./checklist', () => ({ checklistApi: checklist }));

import { createQueryClient, keys, useSetLessonDone } from './queries';

function setup() {
  const client = createQueryClient();
  client.setQueryData(keys.slots(1, 'today'), [{ id: 5, is_completed: false }, { id: 6, is_completed: false }]);
  const wrapper = ({ children }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  return { client, ...renderHook(() => useSetLessonDone(), { wrapper }) };
}

describe('useSetLessonDone', () => {
  afterEach(() => {
    cleanup();
    Object.values(checklist).forEach((fn) => fn.mockReset());
  });

  it('ticks the lesson on every loaded list straight away', async () => {
    let finish;
    checklist.completeSlot.mockReturnValue(new Promise((resolve) => { finish = resolve; }));
    checklist.getToday.mockResolvedValue([{ id: 5, is_completed: true }, { id: 6, is_completed: false }]);
    const { client, result } = setup();

    act(() => result.current.mutate({ slotId: 5, done: true }));
    await waitFor(() => expect(client.getQueryData(keys.slots(1, 'today'))[0].is_completed).toBe(true));
    expect(checklist.completeSlot).toHaveBeenCalledWith(5);
    await act(async () => finish({}));
  });

  it('puts the list back when saving fails', async () => {
    checklist.completeSlot.mockRejectedValue(new Error('offline'));
    checklist.getToday.mockRejectedValue(new Error('offline'));
    const { client, result } = setup();

    act(() => result.current.mutate({ slotId: 6, done: true }));
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(client.getQueryData(keys.slots(1, 'today'))[1].is_completed).toBe(false);
  });
});
