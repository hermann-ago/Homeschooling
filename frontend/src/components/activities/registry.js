/** This allowlist owns presentation. AI content can select a kind, never UI code. */
export const activityRegistry = {
  review_progress: { label: 'Review progress', family: 'internal', internal: true },
  prepare_lesson: { label: 'Prepare the lesson', family: 'internal', internal: true },
  introduce: { label: 'Welcome', family: 'introduction' },
  read_source: { label: 'Read', family: 'reading' },
  explain_or_observe: { label: 'Notice and understand', family: 'explanation' },
  ask_question: { label: 'Your turn', family: 'question', response: true },
  request_book_work: { label: 'Work in your book', family: 'physical', response: true },
  capture_and_confirm: { label: 'Capture your answer', family: 'question', response: true },
  hint_or_follow_up: { label: 'Think it through', family: 'explanation' },
  give_feedback: { label: 'Feedback', family: 'feedback' },
  record_learning_evidence: { label: 'Save learning evidence', family: 'internal', internal: true },
  close_lesson: { label: 'Lesson recap', family: 'closing' },
  worked_example: { label: 'See an example', family: 'worked' },
  explain_thinking: { label: 'Explain your thinking', family: 'question', response: true },
  check_prerequisite: { label: 'Try a smaller step', family: 'question', response: true },
  visual_demonstration: { label: 'Look closely', family: 'visual' },
  take_break_and_return: { label: 'Take a break', family: 'break' },
  tell_it_back: { label: 'Tell it back', family: 'question', response: true },
  compare_and_connect: { label: 'Compare and connect', family: 'comparison', response: true },
  predict_then_check: { label: 'Predict, then check', family: 'prediction', response: true },
  find_and_fix_mistake: { label: 'Find the mistake puzzle', family: 'puzzle', response: true },
  apply_somewhere_new: { label: 'Try somewhere new', family: 'transfer', response: true },
  recall_later: { label: 'Remember it yourself', family: 'question', response: true },
};

export function activityDefinition(activity) {
  if (activity?.version && activity.version !== 1) return { label: 'Activity needs review', family: 'unsupported' };
  return activityRegistry[activity?.kind] || { label: 'Activity needs review', family: 'unsupported' };
}

export function needsResponse(activity) {
  return Boolean(activityDefinition(activity).response ||
    activity?.kind === 'worked_example' && activity.content?.practice_prompt ||
    activity?.kind === 'hint_or_follow_up' && activity.content?.follow_up_prompt);
}

export function responseStage(activity) {
  return activity?.interaction?.stage || activity?.stage || '';
}

export function visibleActivities(state) {
  const activeId = state?.active_activity?.id;
  return (state?.activities || []).filter((activity) =>
    activity.status !== 'not_assigned' && !activityDefinition(activity).internal && activity.id !== activeId &&
    (activity.status === 'answered' || activity.status === 'skipped' || activity.upcoming === false && activity.interaction));
}

export function practiceHistory(activities) {
  const groups=[];
  for (const activity of activities) {
    const section=activity.practice_section;
    const previous=groups.at(-1);
    if (section && previous?.section?.id===section.id) previous.items.push(activity);
    else groups.push({key:section?.id || activity.id,section,items:[activity]});
  }
  return groups;
}
