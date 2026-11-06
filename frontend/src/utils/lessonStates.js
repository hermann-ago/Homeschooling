import { useQuery } from '@tanstack/react-query';
import { fetchApi } from '../api/client';
import { currentMode } from '../api/mode';

/**
 * One small circle that says where a lesson stands, the same everywhere:
 * done, ready (script and voice), script only, preparing, needs attention, or not prepared.
 */
export const LESSON_STATES = {
  done: { label: 'Done', className: 'lesson-dot--done' },
  ready: { label: 'Ready: script and voice', className: 'lesson-dot--ready' },
  script: { label: 'Script ready, voice not yet', className: 'lesson-dot--script' },
  preparing: { label: 'Preparing…', className: 'lesson-dot--preparing' },
  attention: { label: 'Preparation needs attention', className: 'lesson-dot--attention' },
  none: { label: 'Not prepared yet', className: 'lesson-dot--none' },
};

/** Readiness for many lessons in one request; refreshes quickly while any is preparing. */
export function useLessonStates(topicIds) {
  const ids = [...new Set((topicIds || []).filter(Boolean))].sort((a, b) => a - b);
  const { data } = useQuery({
    queryKey: ['lesson-states', currentMode, ids],
    enabled: ids.length > 0,
    queryFn: async () => {
      const states = {};
      for (let first = 0; first < ids.length; first += 300) {
        const params = new URLSearchParams(ids.slice(first, first + 300).map((id) => ['topic_ids', id]));
        Object.assign(states, (await fetchApi(`/tutor/preparation/states?${params}`)).states);
      }
      return states;
    },
    refetchInterval: (query) => Object.values(query.state.data || {}).includes('preparing') ? 5000 : 60000,
  });
  return data || {};
}
