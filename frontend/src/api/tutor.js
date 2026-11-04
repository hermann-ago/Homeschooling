import { fetchApi, request } from './client';

export const tutorApi = {
  scriptReview: guide => fetchApi(`/tutor/guides/${encodeURIComponent(guide)}/review`),
  retryScriptReview: (guide,data) => fetchApi(`/tutor/guides/${encodeURIComponent(guide)}/review`,{method:'POST',body:JSON.stringify(data)}),
  approveAnswers: (guide,index,answers) => fetchApi(`/tutor/guides/${encodeURIComponent(guide)}/answers/${index}`,{method:'PUT',body:JSON.stringify({answers})}),
  withdrawAnswers: (guide,index) => fetchApi(`/tutor/guides/${encodeURIComponent(guide)}/answers/${index}`,{method:'DELETE'}),
  teachingStyle: () => fetchApi('/tutor/teaching-style'),
  saveTeachingStyle: (content, profiles, expectedVersion) => fetchApi('/tutor/teaching-style', {
    method:'PUT', body:JSON.stringify({content,profiles,expected_version:expectedVersion}),
  }),
  actionAudio: (session, actionId, dryRun = true) => fetchApi(`/tutor/sessions/${encodeURIComponent(session)}/action-audio`, {
    method: 'POST', body: JSON.stringify({ action_id: actionId, dry_run: dryRun }),
  }),
  feedbackAudio: (session, messageId, dryRun = true, trackId = null) => fetchApi(`/tutor/sessions/${encodeURIComponent(session)}/feedback-audio`, {
    method: 'POST', body: JSON.stringify({ message_id: messageId, dry_run: dryRun, ...(trackId ? {track_id:trackId} : {}) }),
  }),
  startInteractive: (learner, topic, guideId, slotId, activityVersion = null) => fetchApi('/tutor/interactive/start', {
    method: 'POST', body: JSON.stringify({ learner: Number(learner), topic: Number(topic), guide_id: guideId, slot_id: slotId ? Number(slotId) : null,
      ...(activityVersion ? { activity_contract_version: activityVersion } : {}) }),
  }),
  conversation: (session) => fetchApi(`/tutor/sessions/${encodeURIComponent(session)}/conversation`),
  interactiveAction: (session, action, data) => fetchApi(`/tutor/sessions/${encodeURIComponent(session)}/${action}`, {
    method: 'POST', body: JSON.stringify(data),
  }),
  attachWork: (session, revision, file, actionId) => {
    const form = new FormData();
    form.append('expected_revision', revision);
    form.append('file', file, file.name);
    if (actionId) form.append('action_id', actionId);
    return fetchApi(`/tutor/sessions/${encodeURIComponent(session)}/evidence`, { method: 'POST', body: form });
  },
  records: (childId) => fetchApi(`/tutor/records/${childId}`),
  amendAttempt: (attempt, text, note) => fetchApi(`/tutor/attempts/${encodeURIComponent(attempt.id)}/amend`, {
    method: 'POST', body: JSON.stringify({ expected_revision: attempt.revision, first_answer: text, source_note: note }),
  }),
  reader: (learner, topic, session) => {
    const params = new URLSearchParams({ learner, topic });
    if (session) params.set('session', session);
    return fetchApi(`/tutor/reader?${params}`);
  },
  buildNarration: (learner, topic, dryRun = true, guide = false, session = null, {retryMissing=false}={}) => fetchApi('/tutor/reader/narration', {
    method: 'POST', body: JSON.stringify({ learner: Number(learner), topic: Number(topic), dry_run: dryRun, guide, session, maximum_usd: DEFAULT_AUDIO_CAP_USD, ...(retryMissing?{retry_missing:true}:{}) }),
  }),
  /** Write (or, with rewrite, write again) the lesson's guided walk-through with the AI. */
  writeGuide: (learner, topic, rewrite = false, replaceInvalid = false) => fetchApi('/tutor/reader/guide', {
    method: 'POST', body: JSON.stringify({ learner: Number(learner), topic: Number(topic), rewrite, ...(replaceInvalid ? {replace_invalid:true} : {}) }),
  }),
  estimateGuide: (learner, topic, rewrite = false, maximum_usd = DEFAULT_SCRIPT_CAP_USD) => fetchApi('/tutor/reader/guide', {
    method: 'POST', body: JSON.stringify({ learner, topic, rewrite, dry_run: true, maximum_usd }),
  }),
  prepareGuide: (learner, topic, maximum_usd = DEFAULT_SCRIPT_CAP_USD) => fetchApi('/tutor/reader/guide', {
    method: 'POST', body: JSON.stringify({ learner, topic, maximum_usd }),
  }),
  readerState: (session) => fetchApi(`/tutor/reader/${encodeURIComponent(session)}/state`),
  audioManifest: (trackId) => fetchApi(`/tutor/audio/${encodeURIComponent(trackId)}/manifest`),
  audioPart: async (trackId, index) => {
    const response = await request(`/tutor/audio/${encodeURIComponent(trackId)}/parts/${index}`);
    if (!response.ok) throw new Error('Audio could not be loaded');
    return URL.createObjectURL(await response.blob());
  },
};
import { DEFAULT_SCRIPT_CAP_USD, DEFAULT_AUDIO_CAP_USD } from '../utils/preparationLimits';
