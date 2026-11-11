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

const escape = (text) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/** Where the sentence being spoken sits in the text on screen. `spoken` lists
 *  the step's sentences up to and including the current one, so a repeated
 *  sentence is found in its own place. Null when the text does not contain it. */
export function spokenParts(text, spoken) {
  if (!text || !spoken?.length) return null;
  let from = 0;
  let match = null;
  for (const sentence of spoken) {
    const words = normalize(sentence).split(' ').filter(Boolean).map(escape);
    const pattern = new RegExp(words.join('\\s+'), 'g');
    pattern.lastIndex = from;
    match = words.length ? pattern.exec(text) : null;
    // An earlier sentence shown elsewhere (another line of the card) is passed over.
    if (match) from = match.index + match[0].length;
  }
  if (!match) return null;
  return { before: text.slice(0, match.index), spoken: match[0], after: text.slice(from) };
}
