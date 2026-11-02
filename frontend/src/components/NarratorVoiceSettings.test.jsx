/* @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { DeviceContext } from './deviceContext';
import NarratorVoiceSettings from './NarratorVoiceSettings';

const api=vi.hoisted(()=>({narratorSettings:vi.fn(),saveNarratorSettings:vi.fn(),voices:vi.fn()}));
vi.mock('../api/system',()=>({systemApi:api}));
vi.mock('../api/books',()=>({booksApi:{voices:api.voices}}));
const settings={connected:true,provider:'inworld',model:'inworld-tts-2-flash',english_voice:'Brian',portuguese_voice:'Bruna',
  learners:[{child_id:1,name:'Lucas',english_voice:null,portuguese_voice:null}]};
const voices=['Brian','Oliver','Bruna'].map(id=>({id,name:id,gender:id==='Bruna'?'female':'male',language:id==='Bruna'?'pt-BR':'en-US',preview_url:`/api/ai/inworld/voices/${id}/preview`}));
beforeEach(()=>{
  vi.clearAllMocks(); api.narratorSettings.mockResolvedValue(settings);
  api.saveNarratorSettings.mockImplementation(async choices=>({...settings,...choices}));
  api.voices.mockResolvedValue({voices,groups:[{language:'en-US',gender:'male',voices:voices.slice(0,2)},
    {language:'pt-BR',gender:'female',voices:[voices[2]]}]});
});
afterEach(cleanup);
function show(device={host:false}) {
  const client=new QueryClient({defaultOptions:{queries:{retry:false}}});
  render(<QueryClientProvider client={client}><DeviceContext.Provider value={device}><NarratorVoiceSettings/></DeviceContext.Provider></QueryClientProvider>);
  return client;
}

it('lets a phone audition Oliver and save family choices while children inherit', async()=>{
  const client=show(); const invalidate=vi.spyOn(client,'invalidateQueries');
  fireEvent.click(await screen.findByRole('button',{name:'Use Oliver for English'}));
  expect(screen.getByLabelText('Preview Oliver').getAttribute('src')).toContain('/Oliver/preview');
  expect(api.saveNarratorSettings).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button',{name:'Save narrator choices'}));
  await waitFor(()=>expect(api.saveNarratorSettings).toHaveBeenCalledWith({english_voice:'Oliver',portuguese_voice:'Bruna',
    learners:[{child_id:1,english_voice:null,portuguese_voice:null}]}));
  expect(await screen.findByText(/Narrator choices saved/)).toBeTruthy();
  expect(invalidate).toHaveBeenCalledWith({queryKey:['lesson-narrator']});
  expect(screen.queryByLabelText('API key')).toBeNull();
});

it('saves a separate child voice without changing the family narrator', async()=>{
  show(); await screen.findByRole('button',{name:'Use Oliver for English'});
  fireEvent.click(screen.getByText('Separate voices for each child'));
  fireEvent.change(within(screen.getByRole('group',{name:'Lucas'})).getByLabelText('English narrator'),{target:{value:'Oliver'}});
  fireEvent.click(screen.getByRole('button',{name:'Save narrator choices'}));
  await waitFor(()=>expect(api.saveNarratorSettings).toHaveBeenCalledWith({english_voice:'Brian',portuguese_voice:'Bruna',
    learners:[{child_id:1,english_voice:'Oliver',portuguese_voice:null}]}));
});

it('keeps samples available but blocks family preference changes in test mode',async()=>{
  show({host:false,test_mode:true}); await screen.findByLabelText('Preview Oliver');
  expect(screen.getByRole('button',{name:'Save narrator choices'}).disabled).toBe(true);
  expect(screen.getByRole('button',{name:'Use Oliver for English'}).disabled).toBe(true);
  expect(api.saveNarratorSettings).not.toHaveBeenCalled();
});
