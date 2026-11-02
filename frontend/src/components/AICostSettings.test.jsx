import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
/* @vitest-environment jsdom */
import { render as rtlRender, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { afterEach, beforeEach, it, expect, vi } from 'vitest';
import { DeviceContext } from './deviceContext';
import AICostSettings from './AICostSettings';

const api = vi.hoisted(() => ({ aiStatus: vi.fn(), aiKey: vi.fn(), aiSettings: vi.fn(), checkElevenLabs: vi.fn(), checkInworld: vi.fn(), voices: vi.fn() }));
vi.mock('../api/system', () => ({ systemApi: api }));
vi.mock('../api/books',()=>({booksApi:{voices:api.voices}}));
const render=(ui,client=new QueryClient({defaultOptions:{queries:{retry:false}}}))=>rtlRender(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
const status = { provider: 'openai', keys: { openai: false, google: true }, voice: { enabled: false },
  pilot_passed: false, usage: { categories: { teaching: { used_usd: 0, limit_usd: 3 }, books: { used_usd: 0, limit_usd: 2 }, voice: { used_usd: 0, limit_usd: 2 } } }, book_jobs: [] };
beforeEach(() => { vi.clearAllMocks(); api.voices.mockResolvedValue({voices:[]}); api.aiStatus.mockResolvedValue(status); api.aiKey.mockResolvedValue({ configured: true }); });
afterEach(cleanup);

it('links to the visible narrator section and does not overwrite its choices when saving provider settings', async () => {
  const client = new QueryClient({defaultOptions:{queries:{retry:false}}});
  const invalidate = vi.spyOn(client, 'invalidateQueries');
  const voices = ['Brian','Dennis'].map(id=>({id,name:id,labels:{},language:'en-US',preview_url:`/api/ai/inworld/voices/${id}/preview`}));
  api.voices.mockResolvedValue({voices,groups:[{language:'en-US',gender:'male',voices}]});
  api.aiStatus.mockResolvedValue({...status,keys:{...status.keys,inworld:true},voice:{provider:'inworld',inworld_enabled:true,
    inworld_voice_en:'Brian',inworld_voice_pt:'Bruna',inworld_learner_voices:[{child_id:1,name:'Lucas',english_voice:null,portuguese_voice:null}]}});
  render(<DeviceContext.Provider value={{host:true}}><AICostSettings/></DeviceContext.Provider>,client);
  expect(await screen.findByRole('link',{name:'Choose narrator voices and listen to samples'})).toBeTruthy();
  fireEvent.click(screen.getByRole('button',{name:'Save teaching and voice settings'}));
  await waitFor(()=>expect(api.aiSettings).toHaveBeenCalledWith(expect.objectContaining({voice_provider:'inworld'})));
  expect(api.aiSettings.mock.calls[0][0]).not.toHaveProperty('inworld_model');
  expect(api.aiSettings.mock.calls[0][0]).not.toHaveProperty('inworld_voice_en');
  expect(api.aiSettings.mock.calls[0][0]).not.toHaveProperty('inworld_learner_voices');
  expect(invalidate).toHaveBeenCalledWith({queryKey:['narrator-voices']});
  expect(api.voices).not.toHaveBeenCalled();
});

it('shows and saves each learner’s narrator choices without sending display names', async () => {
  api.aiStatus.mockResolvedValue({ ...status, voice: { provider: 'elevenlabs', elevenlabs_enabled: true,
    elevenlabs_learner_voices: [{ child_id: 1, name: 'Lucas', english_voice: 'nuwpqeXdykQWOB3gY2BP', portuguese_voice: '3ULAAai0IVN00DTWA6vF' }] } });
  render(<DeviceContext.Provider value={{ host: true }}><AICostSettings /></DeviceContext.Provider>);
  expect(await screen.findByRole('group', { name: 'Lucas’s narrators' })).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Save teaching and voice settings' }));
  await waitFor(() => expect(api.aiSettings).toHaveBeenCalledWith(expect.objectContaining({
    elevenlabs_learner_voices: [{ child_id: 1, english_voice: 'nuwpqeXdykQWOB3gY2BP', portuguese_voice: '3ULAAai0IVN00DTWA6vF' }],
  })));
});

it('connects ElevenLabs independently of Google readiness and checks without generating speech', async () => {
  api.aiStatus.mockResolvedValue({ ...status, keys: { ...status.keys, elevenlabs: true },
    preparation_model: 'gpt-6.1-sol', preparation_reasoning: 'high', model: 'gpt-6-luna',
    voice: { provider: 'elevenlabs', google_enabled: false, elevenlabs_enabled: true } });
  api.checkElevenLabs.mockResolvedValue({ verified: true, speech_requested: false });
  render(<DeviceContext.Provider value={{ host: true }}><AICostSettings /></DeviceContext.Provider>);
  expect((await screen.findByRole('combobox', { name: 'Narration provider' })).value).toBe('elevenlabs');
  fireEvent.click(screen.getByRole('button', { name: 'Check ElevenLabs connection' }));
  expect(await screen.findByText('ElevenLabs key verified. No speech was generated.')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Save teaching and voice settings' }));
  await waitFor(() => expect(api.aiSettings).toHaveBeenCalledWith(expect.objectContaining({
    voice_provider: 'elevenlabs', elevenlabs_enabled: true, google_voice_enabled: false,
  })));
});

it('saves longer Google recordings without changing the selected voice provider or allowances', async () => {
  api.aiStatus.mockResolvedValue({ ...status, voice: { provider: 'google-gemini', enabled: true,
    aligned_blocks: true, alignment_languages: ['pt-BR', 'en-US'] } });
  render(<DeviceContext.Provider value={{ host: true }}><AICostSettings /></DeviceContext.Provider>);
  expect((await screen.findByRole('checkbox', { name: 'Prepare longer recordings and synchronize on this computer' })).checked).toBe(true);
  expect(screen.getByText(/Ready for pt-BR and en-US/)).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Save teaching and voice settings' }));
  await waitFor(() => expect(api.aiSettings).toHaveBeenCalledWith(expect.objectContaining({
    aligned_voice_blocks: true, voice_provider: 'google-gemini',
  })));
});

it('keeps Google billing readiness independent when choosing local narration', async () => {
  api.aiStatus.mockResolvedValue({ ...status, voice: { provider: 'kokoro-local', enabled: true,
    google_enabled: false, local_available: true, local_voice_en: 'am_michael', local_voice_pt: 'pf_dora' } });
  render(<DeviceContext.Provider value={{ host: true }}><AICostSettings /></DeviceContext.Provider>);
  const voice = await screen.findByRole('combobox', { name: 'Narration provider' });
  expect(voice.value).toBe('kokoro-local');
  fireEvent.click(screen.getByRole('button', { name: 'Save teaching and voice settings' }));
  await waitFor(() => expect(api.aiSettings).toHaveBeenCalledWith(expect.objectContaining({
    voice_provider: 'kokoro-local', google_voice_enabled: false,
  })));
});

it('shares family limits but hides key entry and spending changes in test mode', async () => {
  render(<DeviceContext.Provider value={{ host: true, test_mode: true }}><AICostSettings /></DeviceContext.Provider>);
  expect(screen.getByText(/Test mode tracks real provider costs too/)).toBeTruthy();
  await screen.findByText(/OpenAI key:/);
  expect(screen.queryByLabelText('API key')).toBeNull();
  expect(screen.queryByRole('button', { name: 'Save teaching and voice settings' })).toBeNull();
  expect(api.aiStatus).toHaveBeenCalled();
});

it('shows connections and allowances on another device without key entry or budget editing', async () => {
  render(<DeviceContext.Provider value={{ host: false }}><AICostSettings /></DeviceContext.Provider>);
  expect(await screen.findByText(/OpenAI key:/)).toBeTruthy();
  expect(screen.queryByLabelText('API key')).toBeNull();
  expect(screen.queryByRole('button', { name: 'Save teaching and voice settings' })).toBeNull();
});

it('stores a key through host settings and clears the password field', async () => {
  render(<DeviceContext.Provider value={{ host: true }}><AICostSettings /></DeviceContext.Provider>);
  const field = await screen.findByLabelText('API key');
  fireEvent.change(field, { target: { value: 'test-key-never-real' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save key securely' }));
  await waitFor(() => expect(api.aiKey).toHaveBeenCalledWith('openai', 'test-key-never-real'));
  await waitFor(() => expect(field.value).toBe(''));
});

it('accepts an Inworld credential without changing provider settings or generating speech', async () => {
  render(<DeviceContext.Provider value={{ host: true }}><AICostSettings /></DeviceContext.Provider>);
  const field = await screen.findByLabelText('API key');
  fireEvent.change(screen.getByRole('combobox', { name: 'Save a key on this home server' }), { target: { value: 'inworld' } });
  expect(screen.getByText(/select Inworld Flash above to use it for lessons/)).toBeTruthy();
  expect(field.type).toBe('password');
  fireEvent.change(field, { target: { value: 'synthetic-inworld-key-never-real' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save key securely' }));
  await waitFor(() => expect(api.aiKey).toHaveBeenCalledWith('inworld', 'synthetic-inworld-key-never-real'));
  await waitFor(() => expect(field.value).toBe(''));
  expect(api.aiSettings).not.toHaveBeenCalled();
});

it('checks an existing Inworld key without starting generation', async () => {
  api.aiStatus.mockResolvedValue({ ...status, keys: { ...status.keys, inworld: true }, voice: { provider: 'elevenlabs' } });
  api.checkInworld.mockResolvedValue({ verified: true, speech_requested: false });
  render(<DeviceContext.Provider value={{ host: true }}><AICostSettings /></DeviceContext.Provider>);
  await screen.findByLabelText('API key');
  fireEvent.change(screen.getByRole('combobox', { name: 'Save a key on this home server' }), { target: { value: 'inworld' } });
  fireEvent.click(screen.getByRole('button', { name: 'Check Inworld connection' }));
  expect(await screen.findByText('Inworld key verified. No speech was generated.')).toBeTruthy();
  expect(api.checkInworld).toHaveBeenCalledTimes(1);
  expect(api.aiSettings).not.toHaveBeenCalled();
});

it('shows original billing currencies as dated checks alongside the app allowances', async () => {
  api.aiStatus.mockResolvedValue({ ...status, provider_balances: {
    openai: { balance: 7.81, currency: 'USD', auto_reload: false, checked_at: '2026-10-07T20:00:00Z' },
    google: { balance: 25.85, currency: 'BRL', auto_reload: false, checked_at: '2026-10-07T20:00:00Z' },
  } });
  render(<DeviceContext.Provider value={{ host: false }}><AICostSettings /></DeviceContext.Provider>);
  expect(await screen.findByText('OpenAI: US$7.81 · automatic reload off')).toBeTruthy();
  expect(screen.getByText('Google: R$25.85 · automatic reload off')).toBeTruthy();
  expect(screen.getAllByText(/Checked 07\/10\/2026, 17:00:00/)).toHaveLength(2);
  expect(screen.getByText(/Saved billing-page checks/)).toBeTruthy();
});

it('shows tracked costs without app spending controls or permission toggles', async () => {
  render(<DeviceContext.Provider value={{ host: true }}><AICostSettings /></DeviceContext.Provider>);
  await screen.findByText(/Costs are tracked by month/);
  expect(screen.queryByRole('checkbox', { name: 'Enable generation within monthly allowances' })).toBeNull();
  expect(screen.queryByLabelText('Teaching (US$)')).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Save teaching and voice settings' }));
  await waitFor(() => expect(api.aiSettings).toHaveBeenCalled());
  for (const field of ['teaching_usd','books_usd','voice_usd','monthly_generation_enabled','pilot_passed']) {
    expect(api.aiSettings.mock.calls[0][0]).not.toHaveProperty(field);
  }
});
