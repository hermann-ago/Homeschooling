import { format } from 'date-fns';
import { LearnerSwitcher } from '../ui';
import { useLearner, useNow } from './learnerContext';

/**
 * The bar at the top of a screen: the learner switcher on the left, the date
 * and time (or the screen's own actions) on the right.
 */
export default function ScreenHeader({ everyone = true, actions }) {
  const { learners, selected, single, select } = useLearner();
  const now = useNow();
  const value = everyone ? selected : single;
  return (
    <header className="min-h-[72px] flex flex-wrap items-center justify-between gap-3 px-4 md:px-10 py-3 border-b border-line">
      <div className="max-w-full overflow-x-auto">
        <LearnerSwitcher learners={learners} value={value} onChange={select} includeEveryone={everyone} />
      </div>
      {actions ?? (
        <span className="text-sm text-muted">{format(now, 'EEEE, d MMMM · h:mm a')}</span>
      )}
    </header>
  );
}
