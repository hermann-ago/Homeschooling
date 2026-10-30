export const narrationPlace = (activity) => activity ? `${activity.id}.${activity.interaction?.id || ''}.${activity.interaction?.stage || activity.stage || ''}` : '';
const normalize = (text) => String(text || '').replace(/\s+/g, ' ').trim();

/** Never borrow a planned recording for a changed prompt or a live follow-up. */
export function narrationRange(guide, activity) {
  if (!activity) return null;
  const interaction = activity.interaction;
  const replay = interaction?.is_replay || interaction?.replay_of;
  const responses = replay ? activity.responses?.filter((row) => row.interaction_id === interaction.id) : activity.responses;
  const messages = replay ? activity.messages?.filter((row) => row.sequence > interaction.dialogue_start_sequence) : activity.messages;
  if (activity.kind !== 'read_source' && (responses?.length || messages?.length || !replay && (interaction?.sequence || 1) > 1)) return null;
  const planned = guide.activities?.find((item) => item.id === activity.id);
  if (!planned || planned.kind !== activity.kind) return null;
  const start = planned.start_sentence;
  const end = planned.end_sentence;
  if (!Number.isInteger(start) || !Number.isInteger(end) || start < 0 || end < start || end >= guide.sentences.length) return null;
  const recorded = normalize(guide.sentences.slice(start, end + 1).map((item) => item.text).join(' '));
  const current = normalize(activity.interaction?.prompt || activity.content?.prompt || activity.content?.text);
  if (activity.kind !== 'read_source' && recorded !== current) return null;
  return { start, end };
}
