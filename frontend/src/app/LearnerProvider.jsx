import { useState } from 'react';
import { useChildren } from '../api/queries';
import { LearnerContext } from './learnerContext';

const STORAGE_KEY = 'homeschool:learner';

function readStored() {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    if (value === null || value === 'all') return 'all';
    return Number(value);
  } catch {
    return 'all';
  }
}

/** Remembers the chosen learner on this device, so a child's tablet stays on that child. */
export default function LearnerProvider({ children: content }) {
  const { data: learners = [], isLoading, error, refetch } = useChildren();
  const [stored, setStored] = useState(readStored);
  const selected = stored === 'all' || learners.some((c) => c.id === stored) ? stored : 'all';
  const single = selected === 'all' ? learners[0]?.id ?? null : selected;

  const select = (value) => {
    setStored(value);
    try {
      localStorage.setItem(STORAGE_KEY, String(value));
    } catch {
      // The choice still holds for this visit.
    }
  };

  const value = {
    learners, isLoading, error, refetch, selected, single, select,
    learner: (id) => learners.find((c) => c.id === id),
  };
  return <LearnerContext.Provider value={value}>{content}</LearnerContext.Provider>;
}
