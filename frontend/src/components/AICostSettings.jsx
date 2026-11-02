import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { systemApi } from '../api/system';
import { booksApi } from '../api/books';
import { useDevice } from './deviceContext';
import { Button, Field } from '../ui';
import { voiceLabel } from '../utils/narratorVoices';

const money = (n) => `US$${Number(n || 0).toFixed(2)}`;
const clean = (e) => e.message.replace(/^\/[^:]+: /, '');
const narrators = {
  english_voice: [['hpp4J3VqNfWAUOO0d1Us', 'Bella · female · US English'], ['nuwpqeXdykQWOB3gY2BP', 'Adam · male · US English']],
  portuguese_voice: [['nczLZ6GvJGozyc3FlLte', 'Juliana · female · Brazilian Portuguese'], ['3ULAAai0IVN00DTWA6vF', 'Henrique · male · Brazilian Portuguese']],
};

export default function AICostSettings() {
  const queryClient = useQueryClient();
  const device = useDevice();
  const isHost = Boolean(device?.host) && !device?.test_mode;
  const [status, setStatus] = useState(null);
  const [draft, setDraft] = useState(null);
  const [key, setKey] = useState('');
  const [keyProvider, setKeyProvider] = useState('openai');
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState('');
  const [connection, setConnection] = useState(null);
  const {data:voiceCatalog}=useQuery({queryKey:['elevenlabs-voices'],queryFn:()=>booksApi.voices('elevenlabs'),enabled:Boolean(status?.keys?.elevenlabs) && draft?.voice_provider==='elevenlabs',staleTime:300000,retry:false});
  const load = async () => {
    const next = await systemApi.aiStatus();
    setStatus(next);
    setDraft({ provider: next.provider,
      google_voice_enabled: next.voice.google_enabled ?? next.voice.enabled,
      voice_provider: next.voice.provider || 'google-gemini',
      ...(next.keys.inworld ? {
        inworld_enabled: Boolean(next.voice.inworld_enabled),
      } : {}),
      elevenlabs_enabled: Boolean(next.voice.elevenlabs_enabled),
      elevenlabs_voice_en: next.voice.elevenlabs_voice_en || 'hpp4J3VqNfWAUOO0d1Us',
      elevenlabs_voice_pt: next.voice.elevenlabs_voice_pt || 'hpp4J3VqNfWAUOO0d1Us',
      elevenlabs_learner_voices: (next.voice.elevenlabs_learner_voices || []).map(({ child_id, english_voice, portuguese_voice }) => ({ child_id, english_voice, portuguese_voice })),
      aligned_voice_blocks: Boolean(next.voice.aligned_blocks),
      local_voice_en: next.voice.local_voice_en || 'am_michael', local_voice_pt: next.voice.local_voice_pt || 'pf_dora' });
  };
  useEffect(() => { load().catch((e) => setProblem(clean(e))); }, []);
  const run = async (work) => {
    setBusy(true); setProblem('');
    try { await work(); await load(); }
    catch (e) { setProblem(clean(e)); }
    finally { setBusy(false); }
  };
  return <section id="ai-voice" className="scroll-mt-6 bg-surface border border-line rounded-2xl p-5 md:p-6 flex flex-col gap-4">
    <h2 className="font-display text-2xl font-medium">Teaching and voice</h2>
    {device?.test_mode && <p className="rounded-xl bg-attention-soft p-3 text-sm">Test mode tracks real provider costs too. Leave test mode to change keys or voice settings.</p>}
    <p className="text-sm text-muted">Prepare lessons from their original pages and your child’s teaching guidance. Narration can use Inworld Flash, ElevenLabs, Google, or the home computer. Saved lessons and recordings are reused.</p>
    {status && <>
      <div className="grid grid-cols-3 gap-2 text-sm">
        {Object.entries(status.usage.categories).map(([name, value]) => <div key={name} className="rounded-xl bg-paper p-3">
          <p className="capitalize font-semibold">{name === 'books' ? 'Book preparation' : name}</p>
          <p>{money(value.used_usd)} this month</p>
          {value.uncertain_usd > 0 && <p className="text-xs text-attention">Includes {money(value.uncertain_usd)} reserved</p>}
        </div>)}
      </div>
      <p className="text-xs text-muted">Costs are tracked by month in São Paulo time. The app does not set spending limits; manage credits and limits with your providers. Provider bills may also include earlier usage, taxes, currency conversion, and other apps.</p>
      {Object.keys(status.provider_balances || {}).length > 0 && <div className="rounded-xl bg-paper p-3 flex flex-col gap-2 text-sm">
        <h3 className="font-semibold">Provider credit balances · last checked</h3>
        {Object.entries(status.provider_balances).map(([provider, check]) => <div key={provider}>
          <p>{provider === 'openai' ? 'OpenAI' : 'Google'}: {check.currency === 'BRL' ? 'R$' : 'US$'}{Number(check.balance).toFixed(2)} · automatic reload {check.auto_reload ? 'on' : 'off'}</p>
          <p className="text-xs text-muted">Checked {new Date(check.checked_at).toLocaleString('en-GB', { timeZone: 'America/Sao_Paulo' })} · São Paulo time</p>
          {check.note && <p className="text-xs text-muted">{check.note}</p>}
        </div>)}
        <p className="text-xs text-muted">Saved billing-page checks, updated when checked again. Balances may change with usage elsewhere and billing delays; these observations and recorded charges remain separate.</p>
      </div>}
      <p className="text-sm">OpenAI key: {status.keys.openai ? 'saved on the home server' : 'needed'} · Google key: {status.keys.google ? 'saved on the home server' : 'needed'} · ElevenLabs key: {status.keys.elevenlabs ? 'saved on the home server' : 'needed'}</p>
      <p className="text-sm">Inworld key: {status.keys.inworld ? 'saved on the home server' : 'not saved'}. Saving a key does not start generation or change the selected narration provider.</p>
      {status.preparation_model && <p className="text-xs text-muted">Lesson preparation: {status.preparation_model}{status.preparation_reasoning ? ` · ${status.preparation_reasoning} reasoning` : ''}. Live answer feedback: {status.model}.</p>}
      {isHost ? <>
        <form className="flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); run(async () => {
          await systemApi.aiSettings(draft);
          await Promise.all(['narrator-voices', 'lesson-narrator', 'reader', 'curriculum-preparation'].map(key => queryClient.invalidateQueries({ queryKey: [key] })));
        }); }}>
          <label className="text-sm font-semibold">Teaching provider
            <select value={draft.provider} onChange={(e) => setDraft({ ...draft, provider: e.target.value })} className="block mt-1 w-full rounded-lg border border-line bg-surface p-2">
              <option value="openai">OpenAI · Sol for preparation, Luna for feedback</option><option value="google">Google · Flash-Lite (manual alternative)</option>
            </select>
          </label>
          <label className="text-sm font-semibold">Narration provider
            <select value={draft.voice_provider} onChange={(e) => setDraft({ ...draft, voice_provider: e.target.value })} className="block mt-1 w-full rounded-lg border border-line bg-surface p-2">
              <option value="inworld">Inworld Flash · lower-cost lesson narration</option>
              <option value="elevenlabs">ElevenLabs · natural voice with synchronized text</option>
              <option value="kokoro-local">Home computer · Kokoro · no API charge</option>
              <option value="google-gemini">Google · Gemini expressive voice</option>
            </select>
          </label>
          {draft.voice_provider === 'inworld' && <div className="flex flex-col gap-4 rounded-xl bg-paper p-3">
            <p className="text-xs text-muted">Inworld TTS-2 Flash · billed by characters. On-Demand voice generation is estimated at US$15 per million characters. Saved recordings are reused; previews below are free.</p>
            <label className="flex gap-2 text-sm"><input type="checkbox" checked={Boolean(draft.inworld_enabled)} onChange={e=>setDraft({...draft,inworld_enabled:e.target.checked})}/>Enable Inworld Flash narration</label>
            <a href="#narrator-voices" className="text-sm text-action underline">Choose narrator voices and listen to samples</a>
          </div>}
          {draft.voice_provider === 'elevenlabs' && <div className="flex flex-col gap-3 rounded-xl bg-paper p-3">
            <p className="text-xs text-muted">Flash v2.5 · saved timestamps keep highlighting and activity pauses. Usage is counted at a published starting-rate equivalent for cost tracking; your subscription credits and actual bill may differ.</p>
            <label className="flex gap-2 text-sm"><input type="checkbox" checked={draft.elevenlabs_enabled} onChange={e => setDraft({ ...draft, elevenlabs_enabled: e.target.checked })}/>Enable ElevenLabs narration</label>
            {[['elevenlabs_voice_en', 'English narrator'], ['elevenlabs_voice_pt', 'Portuguese narrator']].map(([key, label]) => <label key={key} className="text-sm">{label}
              <select value={draft[key]} onChange={e => setDraft({ ...draft, [key]: e.target.value })} className="block mt-1 w-full rounded-lg border border-line bg-surface p-2">
                {(voiceCatalog?.voices || []).map(v=><option key={v.id} value={v.id}>{voiceLabel(v)}</option>)}
                {!voiceCatalog?.voices.some(v=>v.id===draft[key]) && <option value={draft[key]}>Saved narrator</option>}
              </select>
            </label>)}
            <VoiceSamples voices={voiceCatalog?.voices || []}/>
            {draft.elevenlabs_learner_voices.map((row, index) => <fieldset key={row.child_id} className="border border-line rounded-lg p-3 flex flex-col gap-2">
              <legend className="text-sm font-semibold">{status.voice.elevenlabs_learner_voices.find(r => r.child_id === row.child_id)?.name || 'Learner'}’s narrators</legend>
              {Object.entries(narrators).map(([field, fallback]) => { const choices=voiceCatalog?.voices.length?voiceCatalog.voices.map(v=>[v.id,voiceLabel(v)]):fallback;return ( <label key={field} className="text-sm">{field === 'english_voice' ? 'English narrator' : 'Portuguese narrator'}
                <select value={row[field]} onChange={e => setDraft({ ...draft, elevenlabs_learner_voices: draft.elevenlabs_learner_voices.map((r, i) => i === index ? { ...r, [field]: e.target.value } : r) })} className="block mt-1 w-full rounded-lg border border-line bg-surface p-2">
                  {choices.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
                  {!choices.some(([id]) => id === row[field]) && <option value={row[field]}>Saved custom narrator</option>}
                </select>
              </label>);})}
            </fieldset>)}
            <p className="text-xs text-muted">Narrators and samples come from your connected ElevenLabs account. <a className="underline" href="https://elevenlabs.io/app/settings/api-keys" target="_blank" rel="noreferrer">Manage API keys</a></p>
            <Button type="button" disabled={busy || !status.keys.elevenlabs} onClick={() => run(async () => { await systemApi.checkElevenLabs(); setConnection({ provider: 'elevenlabs', message: 'ElevenLabs key verified. No speech was generated.' }); })}>Check ElevenLabs connection</Button>
            {connection?.provider === 'elevenlabs' && <p role="status" className="text-xs">{connection.message}</p>}
          </div>}
          {draft.voice_provider === 'kokoro-local' && <>
            <p className="text-xs text-muted">{status.voice.local_available ? 'Local model installed.' : 'Install the local voice model on the home computer first.'} Creating a recording takes a few minutes and uses this computer. Saved recordings play on all connected devices. Electricity and storage still apply.</p>
            <div className="grid grid-cols-2 gap-2">{[['local_voice_en', 'English voice', [['am_michael', 'Michael'], ['af_heart', 'Heart']]], ['local_voice_pt', 'Portuguese voice', [['pf_dora', 'Dora'], ['pm_alex', 'Alex']]]].map(([key, label, choices]) => <label key={key} className="text-sm">{label}<select value={draft[key]} onChange={(e) => setDraft({ ...draft, [key]: e.target.value })} className="block mt-1 w-full rounded-lg border border-line bg-surface p-2">{choices.map(([value, name]) => <option key={value} value={value}>{name}</option>)}</select></label>)}</div>
          </>}
          {draft.voice_provider === 'google-gemini' && <><label className="flex gap-2 text-sm"><input type="checkbox" checked={draft.google_voice_enabled} onChange={(e) => setDraft({ ...draft, google_voice_enabled: e.target.checked })} />Google billing is restored; enable expressive voice</label>
          <label className="flex gap-2 text-sm"><input type="checkbox" checked={draft.aligned_voice_blocks} onChange={(e) => setDraft({ ...draft, aligned_voice_blocks: e.target.checked })} />Prepare longer recordings and synchronize on this computer</label>
          <p className="text-xs text-muted">Uses fewer Google requests with the same voice. This computer matches the saved audio to the lesson and preserves each activity's pause. {(status.voice.alignment_languages || []).length ? `Ready for ${(status.voice.alignment_languages || []).join(' and ')}.` : 'Install the local synchronization models before enabling this option.'} Existing recordings remain available.</p>
          <p className="text-xs text-muted">Check Google's prepaid balance and project spending cap first. Keep automatic reload off. <a className="text-action underline" href="https://aistudio.google.com/projects" target="_blank" rel="noreferrer">Open Google billing</a>. Paid Google generation is tracked here. Changing narrator never deletes saved recordings.</p></>}
          <Button type="submit" disabled={busy}>Save teaching and voice settings</Button>
        </form>
        <form className="flex flex-col gap-2 border-t border-line pt-3" onSubmit={(e) => { e.preventDefault(); run(async () => { await systemApi.aiKey(keyProvider, key); setKey(''); }); }}>
          <label className="text-sm">Save a key on this home server
            <select value={keyProvider} onChange={(e) => { setKeyProvider(e.target.value); setKey(''); setConnection(null); }} className="ml-2 rounded-lg border border-line p-1 bg-surface"><option value="openai">OpenAI</option><option value="google">Google</option><option value="elevenlabs">ElevenLabs</option><option value="inworld">Inworld</option></select>
          </label>
          {keyProvider === 'inworld' && <p className="text-xs text-muted">Create a Standard key in <a href="https://platform.inworld.ai" target="_blank" rel="noreferrer" className="underline">Inworld Portal</a> → Manage → API Keys. Paste the complete Basic (Base64) credential below, without the word “Basic”. It is encrypted on this Windows computer. Saving starts no speech requests; select Inworld Flash above to use it for lessons.</p>}
          <Field label="API key" type="password" autoComplete="off" value={key} onChange={(e) => setKey(e.target.value)} placeholder="Paste key here" />
          <Button type="submit" disabled={busy || key.trim().length < 15}>Save key securely</Button>
          {keyProvider === 'inworld' && <>
            <Button type="button" disabled={busy || !status.keys.inworld} onClick={() => run(async () => { await systemApi.checkInworld(); setConnection({ provider: 'inworld', message: 'Inworld key verified. No speech was generated.' }); })}>Check Inworld connection</Button>
            {connection?.provider === 'inworld' && <p role="status" className="text-xs">{connection.message}</p>}
          </>}
        </form>
      </> : <p className="text-sm text-muted">A parent can add keys and change voice settings on the home server computer.</p>}
      {(status.voice_jobs || []).length > 0 && <details className="border-t border-line pt-3 text-sm">
        <summary className="font-semibold cursor-pointer">Earlier voice preparation</summary>
        {status.voice_jobs.map((job) => <p key={job.id}>{job.completed_parts} / {job.parts} passages saved · {job.status}. {job.error} Resume from the lesson’s voice button.</p>)}
      </details>}
      {(status.uncertain_requests || []).length > 0 && <div className="border-t border-line pt-3 flex flex-col gap-2 text-sm">
        <h3 className="font-semibold">Charges awaiting confirmation</h3>
        <p className="text-xs text-muted">Keep these reserved unless the provider confirms the actual charge. Active requests cannot be reconciled here.</p>
        {status.uncertain_requests.map((request) => <div key={request.id} className="rounded-xl bg-paper p-3">
          <p>{request.category} · {request.model} · {money(request.charged_usd)} reserved · {request.created_at.slice(0, 10)}</p>
          {isHost && request.status === 'uncertain' && <form className="flex flex-wrap items-end gap-2 mt-2" onSubmit={(e) => {
            e.preventDefault(); const value = Number(new FormData(e.currentTarget).get('charge'));
            run(() => systemApi.aiReconcile(request.id, value));
          }}>
            <Field name="charge" label="Confirmed charge (US$)" type="number" min="0" max="100" step="0.000001" required />
            <label className="text-xs"><input type="checkbox" required /> I verified this request in the provider bill</label>
            <Button size="sm" type="submit" disabled={busy}>Reconcile charge</Button>
          </form>}
        </div>)}
      </div>}
      <Button size="sm" disabled={busy} onClick={() => run(async () => {})}>Refresh spending and jobs</Button>
    </>}
    {problem && <p role="alert" className="text-sm text-problem">{problem}</p>}
  </section>;
}

function VoiceSamples({voices}) {
  const [choice,setChoice]=useState('');
  const selected=voices.find(v=>v.id===choice);
  return <div className="flex flex-col gap-2"><label className="text-sm">Preview a narrator<select aria-label="Preview a narrator" value={choice} onChange={e=>setChoice(e.target.value)} className="block w-full mt-1 border border-line rounded-lg p-2 bg-surface"><option value="">Choose a sample</option>{voices.map(v=><option key={v.id} value={v.id}>{voiceLabel(v)}</option>)}</select></label>{selected&&<p className="text-xs text-muted">{voiceLabel(selected)}</p>}{selected?.preview_url&&<audio key={selected.id} controls preload="none" src={selected.preview_url} aria-label={`Preview ${selected.name}`} className="w-full"/>}</div>;
}
