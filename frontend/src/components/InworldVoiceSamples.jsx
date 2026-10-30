import { useRef } from 'react';
import { Button } from '../ui';
import { modeHref } from '../api/mode';

export default function InworldVoiceSamples({ packet, english, portuguese, onChoose, disabled }) {
  const players = useRef(new Map());
  if (!packet) return null;
  return <section aria-label="Inworld voice samples" className="flex flex-col gap-3">
    <h3 className="font-semibold">Choose a voice</h3>
    <p className="text-xs text-muted">Free Inworld Flash previews. Selected for tutoring; Inworld does not publish popularity rankings. Save settings after choosing a voice.</p>
    {packet.groups.map(group => <details key={`${group.language}-${group.gender}`} open={group.language === 'en-US' && group.gender === 'male'} className="rounded-xl border border-line bg-surface p-3">
      <summary className="cursor-pointer font-semibold">{group.language === 'en-US' ? 'American English' : 'Brazilian Portuguese'} · {group.gender === 'male' ? 'Male' : 'Female'} · {group.voices.length} voices</summary>
      {group.language === 'pt-BR' && group.gender === 'male' && group.voices.length < 5 && <p className="mt-3 text-xs text-muted">All {group.voices.length} native Brazilian male voices available in the current catalog.</p>}
      <div className="mt-3 grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 16rem), 1fr))' }}>{group.voices.map(voice => {
        const chosen = voice.id === (group.language === 'en-US' ? english : portuguese);
        return <article key={voice.id} className="min-w-0 rounded-xl border border-line p-3 flex flex-col gap-2">
          <h4 className="font-semibold">{voice.name}{chosen ? ' · Selected' : ''}</h4>
          <p className="text-xs text-muted">{voice.description}</p>
          <audio ref={element => { if (element) players.current.set(voice.id, element); else players.current.delete(voice.id); }}
            controls preload="none" src={modeHref(voice.preview_url)} aria-label={`Preview ${voice.name}`}
            onPlay={event => { for (const player of players.current.values()) if (player !== event.currentTarget) player.pause(); }} className="w-full max-w-full" />
          <Button type="button" size="sm" disabled={disabled || chosen} onClick={() => onChoose(group.language, voice.id)}>Use {voice.name} for {group.language === 'en-US' ? 'English' : 'Portuguese'}</Button>
        </article>;
      })}</div>
    </details>)}
  </section>;
}
