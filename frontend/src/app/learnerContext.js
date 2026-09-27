import { createContext, useContext, useEffect, useState } from 'react';

export const LearnerContext = createContext(null);

/**
 * The learner the screens show: `selected` is 'all' or a child id; `single` is
 * always one learner (the selected one, or the first) for screens that need one.
 */
export function useLearner() {
  const value = useContext(LearnerContext);
  if (!value) throw new Error('Wrap the screens in <LearnerProvider>');
  return value;
}

/** The current time, refreshed every minute (for "Now" and overdue lessons). */
export function useNow() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 60_000);
    return () => window.clearInterval(timer);
  }, []);
  return now;
}
