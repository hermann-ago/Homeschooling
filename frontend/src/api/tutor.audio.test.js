import { beforeEach, describe, expect, it, vi } from 'vitest';

const client = vi.hoisted(() => ({ fetchApi: vi.fn(), request: vi.fn() }));
vi.mock('./client', () => client);

import { tutorApi } from './tutor';

describe('lesson voice downloads', () => {
  beforeEach(() => {
    client.fetchApi.mockReset();
    client.request.mockReset().mockImplementation(async () => ({ ok: true, blob: async () => new Blob(['wav']) }));
    vi.stubGlobal('URL', { ...URL, createObjectURL: vi.fn(() => 'blob:part'), revokeObjectURL: vi.fn() });
  });

  it('downloads a part once: a preloaded or replayed part comes from memory', async () => {
    tutorApi.preloadAudioPart('track-a', 3);
    await tutorApi.audioPart('track-a', 3);
    await tutorApi.audioPart('track-a', 3);
    expect(client.request).toHaveBeenCalledTimes(1);
    expect(client.request).toHaveBeenCalledWith('/tutor/audio/track-a/parts/3');
  });

  it('asks again for a part that failed to load', async () => {
    client.request.mockResolvedValueOnce({ ok: false });
    await expect(tutorApi.audioPart('track-b', 0)).rejects.toThrow('Audio could not be loaded');
    await tutorApi.audioPart('track-b', 0);
    expect(client.request).toHaveBeenCalledTimes(2);
  });

  it('keeps a finished manifest but asks again while a recording is unfinished', async () => {
    client.fetchApi.mockResolvedValue({ job_status: 'ready', fallback_parts: 0, tracks: [] });
    await tutorApi.audioManifest('done');
    await tutorApi.audioManifest('done');
    expect(client.fetchApi).toHaveBeenCalledTimes(1);
    client.fetchApi.mockResolvedValue({ job_status: 'ready', fallback_parts: 2, tracks: [] });
    await tutorApi.audioManifest('gaps');
    await tutorApi.audioManifest('gaps');
    client.fetchApi.mockResolvedValue({ job_status: 'running', tracks: [] });
    await tutorApi.audioManifest('making');
    await tutorApi.audioManifest('making');
    expect(client.fetchApi).toHaveBeenCalledTimes(5);
  });
});
