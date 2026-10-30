export const NARRATION_SPEEDS = [0.75, 0.9, 1, 1.15, 1.3];

export function narrationVoiceLabel(track, session = false) {
  const localNames = { af_heart: 'Heart', pf_dora: 'Dora', pm_alex: 'Alex', am_michael: 'Michael' };
  const name = track.provider === 'kokoro-local' ? `Home voice · ${localNames[track.voice] || 'Michael'}`
    : track.provider === 'elevenlabs' ? `ElevenLabs · ${track.voice_name || { hpp4J3VqNfWAUOO0d1Us: 'Bella', nczLZ6GvJGozyc3FlLte: 'Juliana', nuwpqeXdykQWOB3gY2BP: 'Adam', '3ULAAai0IVN00DTWA6vF': 'Henrique', JBFqnCBsd6RMkjVDRZzb: 'George' }[track.voice] || track.voice}`
    : track.provider === 'inworld' ? `Inworld ${track.model === 'inworld-tts-2-flash' ? 'Flash' : 'TTS-2'} · ${track.voice}`
    : session && track.provider === 'google-gemini' ? `Google voice · ${track.voice}` : track.voice || track.provider || track.track_id;
  return name + (track.fallback_parts ? session ? ' (some passages text-only)' : ' (includes device voice)' : '') + (track.synchronized ? '' : ' (no highlighting)');
}
