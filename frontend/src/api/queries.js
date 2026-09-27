import { QueryClient, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { childrenApi } from './children';
import { checklistApi } from './checklist';
import { progressApi } from './progress';
import { subjectsApi } from './subjects';

/**
 * Shared data access for the screens. Every screen reads through these hooks,
 * so a change saved on one screen (a lesson marked done) refreshes every other
 * screen that shows it.
 */
export function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      // request() already retries network failures, so one more try is enough.
      queries: { staleTime: 30_000, retry: 1 },
      mutations: { retry: 0 },
    },
  });
}

export const keys = {
  children: ['children'],
  slots: (childId, range) => ['slots', childId, range],
  progress: (childId) => ['progress', childId ?? 'family'],
  subjects: (childId) => ['subjects', childId],
  topics: (subjectId) => ['topics', subjectId],
};

export const useChildren = () => useQuery({ queryKey: keys.children, queryFn: childrenApi.getAll });

const slotFetchers = { today: checklistApi.getToday, week: checklistApi.getWeek, missed: checklistApi.getMissed };

/** Scheduled lessons for one learner: range is 'today', 'week' or 'missed'. */
export const useSlots = (childId, range) => useQuery({
  queryKey: keys.slots(childId, range),
  queryFn: () => slotFetchers[range](childId),
  enabled: childId != null,
});

export const useChildProgress = (childId) => useQuery({
  queryKey: keys.progress(childId),
  queryFn: () => progressApi.getChildProgress(childId),
  enabled: childId != null,
});

export const useFamilyProgress = () => useQuery({
  queryKey: keys.progress(),
  queryFn: progressApi.getFamilyOverview,
});

export const useSubjects = (childId) => useQuery({
  queryKey: keys.subjects(childId),
  queryFn: () => subjectsApi.getByChildId(childId),
  enabled: childId != null,
});

export const useTopics = (subjectId) => useQuery({
  queryKey: keys.topics(subjectId),
  queryFn: () => subjectsApi.getTopics(subjectId),
  enabled: subjectId != null,
});

/**
 * Mark a scheduled lesson done or not done. The tick shows at once on every
 * loaded list; if saving fails the lists go back to what the server has.
 */
export function useSetLessonDone() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ slotId, done }) => (done ? checklistApi.completeSlot(slotId) : checklistApi.uncompleteSlot(slotId)),
    onMutate: async ({ slotId, done }) => {
      await client.cancelQueries({ queryKey: ['slots'] });
      const previous = client.getQueriesData({ queryKey: ['slots'] });
      client.setQueriesData({ queryKey: ['slots'] }, (slots) => (
        Array.isArray(slots) ? slots.map((s) => (s.id === slotId ? { ...s, is_completed: done } : s)) : slots
      ));
      return { previous };
    },
    onError: (_error, _vars, context) => {
      context?.previous.forEach(([key, data]) => client.setQueryData(key, data));
    },
    onSettled: () => Promise.all([
      client.invalidateQueries({ queryKey: ['slots'] }),
      client.invalidateQueries({ queryKey: ['progress'] }),
      client.invalidateQueries({ queryKey: ['topics'] }),
    ]),
  });
}
