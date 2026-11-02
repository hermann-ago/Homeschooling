import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { systemApi } from '../api/system';
import { booksApi } from '../api/books';
import { useDevice } from './deviceContext';
import { modeHref } from '../api/mode';
import { Button } from '../ui';
import InworldVoiceSamples from './InworldVoiceSamples';

const preferences = data => ({ english_voice: data.english_voice, portuguese_voice: data.portuguese_voice,
  learners: data.learners.map(({ child_id, english_voice, portuguese_voice }) => ({ child_id, english_voice, portuguese_voice })) });
const languages = [['english_voice', 'English narrator', 'en-US'], ['portuguese_voice', 'Portuguese narrator', 'pt-BR']];

export default function NarratorVoiceSettings() {
  const client = useQueryClient();
  const device = useDevice();
  const [draft, setDraft] = useState(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [problem, setProblem] = useState('');
  const { data, error, refetch } = useQuery({ queryKey: ['inworld-narrators'], queryFn: systemApi.narratorSettings });
  const { data: catalog, error: catalogError } = useQuery({ queryKey: ['inworld-voices'], queryFn: () => booksApi.voices('inworld'),
    enabled: Boolean(data?.connected), staleTime: 300000, retry: false });
  const selected = draft || (data && preferences(data));
  const disabled = busy || Boolean(device?.test_mode);
  const choose = changes => { setDraft({ ...selected, ...changes }); setMessage(''); };
  const save = async event => {
    event.preventDefault(); setBusy(true); setProblem(''); setMessage('');
    try {
      const saved = await systemApi.saveNarratorSettings(selected);
      client.setQueryData(['inworld-narrators'], saved); setDraft(null);
      await Promise.all(['narrator-voices', 'lesson-narrator', 'reader', 'curriculum-preparation'].map(key => client.invalidateQueries({ queryKey: [key] })));
      setMessage('Narrator choices saved. New recordings will use these voices.');
    } catch (error) { setProblem(error.message); }
    finally { setBusy(false); }
  };
  return <section id="narrator-voices" aria-label="Narrator voices" className="scroll-mt-6 bg-surface border border-line rounded-2xl p-5 md:p-6 flex flex-col gap-4">
    <h2 className="font-display text-2xl font-medium">Narrator voices</h2>
    <p className="text-sm text-muted">Listen to samples and choose English and Portuguese narrators for your family or each child. Available on your phone, tablet and home computer.</p>
    {error && <><p role="alert">{error.message}</p><Button onClick={() => refetch()}>Retry voice settings</Button></>}
    {!data && !error && <p role="status">Loading narrator voices…</p>}
    {data && !data.connected && <p>Connect Inworld in <a className="underline" href={modeHref('/settings#ai-voice')}>Teaching and voice</a> on the home computer to listen to samples.</p>}
    {data?.connected && <form onSubmit={save} className="flex flex-col gap-4">
      <p className="text-xs text-muted">Inworld Flash · sample playback is free. Saving a choice starts no lesson generation. Saved recordings remain available.</p>
      <p className="text-xs text-muted">These defaults apply when preparing new recordings. A lesson with its own selected narrator keeps that choice.</p>
      {data.provider !== 'inworld' && <p className="text-sm text-attention">These are your Inworld choices. Select Inworld Flash as the narration provider in Teaching and voice on the home computer to use them.</p>}
      {device?.test_mode && <p className="text-sm text-muted">Leave test mode to save family narrator choices. You can still listen to samples.</p>}
      <fieldset disabled={disabled} className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <legend className="font-semibold mb-2">Family narrators</legend>
        {languages.map(([field, label, language]) => <VoiceChoice key={field} label={label} value={selected[field]} voices={catalog?.voices} language={language} onChange={voice => choose({ [field]: voice })} />)}
      </fieldset>
      <details className="rounded-xl border border-line p-3">
        <summary className="font-semibold cursor-pointer">Separate voices for each child</summary>
        <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">{selected.learners.map((row, index) => <fieldset disabled={disabled} key={row.child_id} className="rounded-xl border border-line p-3 flex flex-col gap-3">
          <legend className="font-semibold">{data.learners.find(child => child.child_id === row.child_id)?.name}</legend>
          {languages.map(([field, label, language]) => <VoiceChoice key={field} label={label} value={row[field] || ''} inherit voices={catalog?.voices} language={language}
            onChange={voice => choose({ learners: selected.learners.map((child, i) => i === index ? { ...child, [field]: voice || null } : child) })} />)}
        </fieldset>)}</div>
      </details>
      {catalogError && <p role="alert">{catalogError.message}</p>}
      <InworldVoiceSamples packet={catalog} english={selected.english_voice} portuguese={selected.portuguese_voice}
        disabled={disabled} instruction="Sample buttons choose the family narrator. Save your choices below."
        onChoose={(language, voice) => choose({ [language === 'en-US' ? 'english_voice' : 'portuguese_voice']: voice })} />
      <Button type="submit" variant="primary" disabled={disabled || !catalog}>{busy ? 'Saving…' : 'Save narrator choices'}</Button>
      {message && <p role="status" className="text-sm text-action">{message}</p>}
      {problem && <p role="alert" className="text-sm text-problem">{problem}</p>}
    </form>}
  </section>;
}

function VoiceChoice({ label, value, voices = [], language, inherit, onChange }) {
  const choices = voices.filter(voice => voice.language === language);
  return <label className="text-sm">{label}<select value={value} onChange={event => onChange(event.target.value)} className="block w-full mt-1 rounded-lg border border-line bg-surface p-2">
    {inherit && <option value="">Use family narrator</option>}
    {choices.map(voice => <option key={voice.id} value={voice.id}>{voice.name} · {voice.gender}</option>)}
    {value && !choices.some(voice => voice.id === value) && <option value={value}>{value}</option>}
  </select></label>;
}
