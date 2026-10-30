/** Presentation only: saved evidence and learner wording remain unchanged. */
const labels = {
  assessed: 'Answer checked', confirmed: 'Answer saved', saved: 'Saved',
  awaiting_confirmation: 'Check the captured words', awaiting_input: 'Ready for your answer',
  awaiting_followup: 'Ready for your next answer', ready_to_assess: 'Ready to check',
  assessment_pending: 'Waiting for feedback', assessment_failed: 'Feedback needs another try',
  parent_review: 'Original work needs checking', with_help: 'With help',
  independent: 'Without help', assisted: 'With help', unknown: 'Not yet known',
  not_assessed: 'Independence not established',
  unassessed: 'Not checked yet', completed: 'Finished', unfinished: 'Saved to continue',
  active: 'In progress', not_requested: 'Not checked yet', not_assigned: 'Not assigned',
};
export const learningLabel = (value) => labels[value] || value?.replaceAll('_', ' ') || '';
