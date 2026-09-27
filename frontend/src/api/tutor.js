import { fetchApi, request } from './client';

export const tutorApi = {
  reader: (learner, topic, session) => {
    const params = new URLSearchParams({ learner, topic });
    if (session) params.set('session', session);
    return fetchApi(`/tutor/reader?${params}`);
  },
  buildNarration: (learner, topic, dryRun = true) => fetchApi('/tutor/reader/narration', {
    method: 'POST', body: JSON.stringify({ learner: Number(learner), topic: Number(topic), dry_run: dryRun }),
  }),
  readerState: (session) => fetchApi(`/tutor/reader/${encodeURIComponent(session)}/state`),
  audioManifest: (trackId) => fetchApi(`/tutor/audio/${encodeURIComponent(trackId)}/manifest`),
  audioPart: async (trackId, index) => {
    const response = await request(`/tutor/audio/${encodeURIComponent(trackId)}/parts/${index}`);
    if (!response.ok) throw new Error('Audio could not be loaded');
    return URL.createObjectURL(await response.blob());
  },
};
