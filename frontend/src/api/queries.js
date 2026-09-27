import { QueryClient, useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query';
import { calendarApi } from './calendar';
import { canvasApi } from './canvas';
import { childrenApi } from './children';
import { checklistApi } from './checklist';
import { progressApi } from './progress';
import { schedulerApi } from './scheduler';
import { subjectsApi } from './subjects';
import { systemApi } from './system';
import { timeWindowsApi } from './timeWindows';

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
  blockedDays: (childId, start, end) => ['blocked-days', childId, start, end],
  completedTopics: (childId) => ['completed-topics', childId],
  timeWindows: (childId) => ['time-windows', childId],
  schoolYear: ['school-year'],
  storage: ['storage'],
  narration: ['narration-usage'],
  inserts: (topicId) => ['inserts', topicId],
};

/** Refresh everything that a change to the plan can affect. */
export const refreshPlan = (client) => Promise.all(
  ['slots', 'progress', 'topics', 'completed-topics'].map((key) => client.invalidateQueries({ queryKey: [key] })),
);

export const useChildren = () => useQuery({ queryKey: keys.children, queryFn: childrenApi.getAll });

const slotFetchers = { today: checklistApi.getToday, week: checklistApi.getWeek, missed: checklistApi.getMissed };

function slotsQuery(childId, range) {
  if (typeof range === 'object') {  // { start, end }: any stretch of days
    return {
      queryKey: keys.slots(childId, `${range.start}..${range.end}`),
      queryFn: () => schedulerApi.getSchedule(childId, { start_date: range.start, end_date: range.end }),
      enabled: childId != null,
    };
  }
  return { queryKey: keys.slots(childId, range), queryFn: () => slotFetchers[range](childId), enabled: childId != null };
}

/** Scheduled lessons for one learner: range is 'today', 'week', 'missed' or { start, end } dates. */
export const useSlots = (childId, range) => useQuery(slotsQuery(childId, range));

/** The same range for several learners at once: returns [{ child, data, isLoading }]. */
export function useSlotsFor(children, range) {
  const results = useQueries({ queries: children.map((child) => slotsQuery(child.id, range)) });
  return children.map((child, index) => ({ child, data: results[index].data, isLoading: results[index].isLoading }));
}

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

export const useBlockedDays = (childId, start, end) => useQuery({
  queryKey: keys.blockedDays(childId, start, end),
  queryFn: () => calendarApi.getBlockedDays({ ...(childId != null ? { child_id: childId } : {}), start_date: start, end_date: end }),
});

export const useCompletedTopics = (childId) => useQuery({
  queryKey: keys.completedTopics(childId),
  queryFn: () => calendarApi.getCompletedTopics(childId),
  enabled: childId != null,
});

export const useTimeWindows = (childId) => useQuery({
  queryKey: keys.timeWindows(childId),
  queryFn: () => timeWindowsApi.getByChildId(childId),
  enabled: childId != null,
});

export const useSchoolYear = () => useQuery({ queryKey: keys.schoolYear, queryFn: calendarApi.getSchoolYearSettings });

export const useStorageStatus = () => useQuery({
  queryKey: keys.storage, queryFn: systemApi.storageStatus, refetchInterval: 30_000, retry: 0,
});

export const useNarrationUsage = () => useQuery({ queryKey: keys.narration, queryFn: systemApi.narrationUsage });

export const useInserts = (topicId) => useQuery({
  queryKey: keys.inserts(topicId),
  queryFn: () => canvasApi.getInsertsForTopic(topicId),
  enabled: topicId != null,
});

/** Plan every unfinished lesson again from today, for one learner or several. */
export function useReplan() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (childIds) => {
      const results = [];
      for (const id of childIds) results.push({ childId: id, ...(await schedulerApi.recalculate(id)) });
      return results;
    },
    onSettled: () => refreshPlan(client),
  });
}

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
    onSettled: () => refreshPlan(client),
  });
}
