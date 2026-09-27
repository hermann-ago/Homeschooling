import { useReplan } from '../api/queries';
import { useConfirm, useToast } from '../ui';

/** Ask, then plan every unfinished chapter again from today for the given learners. */
export default function useReplanAction() {
  const replan = useReplan();
  const confirm = useConfirm();
  const toast = useToast();

  const apply = (learners) => new Promise((resolve) => {
    replan.mutate(learners.map((c) => c.id), {
      onSuccess: (results) => {
        const created = results.reduce((sum, r) => sum + (r.slots_created || 0), 0);
        const warnings = results.flatMap((r) => (r.warnings || []).map((w) => w.message));
        toast(warnings.length ? warnings.join(' ') : `Re-planned: ${created} lessons from today.`);
        resolve(true);
      },
      onError: (error) => {
        toast({ tone: 'problem', message: `Could not re-plan: ${error.message}` });
        resolve(false);
      },
    });
  });

  const run = async (learners) => {
    if (!learners.length) return false;
    const names = learners.map((c) => c.name).join(' and ');
    const ok = await confirm({
      title: `Re-plan ${names} from today?`,
      description: 'Every chapter not yet done is planned again from today, in order, in the study times you set. '
        + 'Lessons from earlier days that were not marked done move into the coming school days.',
      confirmLabel: 'Re-plan',
    });
    return ok ? apply(learners) : false;
  };

  return { run, apply, busy: replan.isPending };
}
