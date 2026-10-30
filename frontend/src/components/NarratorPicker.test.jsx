/* @vitest-environment jsdom */
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, it, expect, vi } from 'vitest';
import NarratorPicker from './NarratorPicker';
import LessonSourcePages from './LessonSourcePages';
const api=vi.hoisted(()=>({voices:vi.fn(),narrator:vi.fn(),saveNarrator:vi.fn(),sourcePages:vi.fn(),saveSourcePages:vi.fn()}));
vi.mock('../api/books',()=>({booksApi:api}));
afterEach(cleanup);
beforeEach(()=>{
  vi.clearAllMocks();
  api.voices.mockResolvedValue({voices:[{id:'first-narrator',name:'First',labels:{accent:'British',gender:'female'},preview_url:'https://example.com/first.mp3'},
    {id:'second-narrator',name:'Second',labels:{accent:'American',gender:'male'},preview_url:'https://example.com/second.mp3'}]});
  api.narrator.mockResolvedValue({voice:'first-narrator'});api.saveNarrator.mockResolvedValue({voice:'second-narrator'});
});
function show(component){return render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}>{component}</QueryClientProvider>);}
it('previews existing samples and selects a lesson voice without generating speech',async()=>{
  show(<NarratorPicker topic={5}/>);
  await screen.findByRole('option',{name:/Second.*American.*male/i},{timeout:5000});
  fireEvent.change(screen.getByLabelText('Lesson narrator'),{target:{value:'second-narrator'}});
  expect(screen.getByLabelText('Preview Second').getAttribute('src')).toBe('https://example.com/second.mp3');
  expect(api.saveNarrator).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button',{name:'Use narrator for this lesson'}));
  await waitFor(()=>expect(api.saveNarrator).toHaveBeenCalledWith(5,'second-narrator'));
  expect(await screen.findByText(/Narrator selected/)).toBeTruthy();
});
it('saves selected source ranges with their revision and keeps key roles visible',async()=>{
  api.sourcePages.mockResolvedValue({revision:3,sources:[{document_id:9,page_start:2,page_end:3}],books:[{document_id:9,name:'Key',role:'answer_key',page_count:10,chapters:[]}]});
  api.saveSourcePages.mockResolvedValue({revision:4});
  show(<LessonSourcePages topic={7}/>);
  await screen.findByRole('option',{name:'Key · private answer key'});
  fireEvent.change(screen.getByLabelText('Source 1 last page'),{target:{value:'4'}});
  fireEvent.click(screen.getByRole('button',{name:'Save selected pages'}));
  await waitFor(()=>expect(api.saveSourcePages).toHaveBeenCalledWith(7,[{document_id:9,page_start:2,page_end:4}],3));
});
