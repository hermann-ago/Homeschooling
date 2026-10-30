/* @vitest-environment jsdom */
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {afterEach,expect,it,vi} from 'vitest';
const api=vi.hoisted(()=>({sourceNotes:vi.fn(),saveSourceNote:vi.fn()}));
vi.mock('../api/books',()=>({booksApi:api}));
import SourceNotes from './SourceNotes';
afterEach(()=>{cleanup();vi.resetAllMocks();});
it('binds edits to the saved edition, page range and version',async()=>{
  const note={id:'n1',key:'source',document_sha256:'b'.repeat(64),version:2,first_page:5,last_page:6,title:'A checked claim',teaching_note:'Clarify this claim.',assessment_note:'A private exception.',references:['https://example.org/source'],active:true};
  api.sourceNotes.mockResolvedValue({documents:[{id:9,sha256:'b'.repeat(64),original_filename:'Synthetic book.pdf'}],notes:[note],history:[note]});
  api.saveSourceNote.mockResolvedValue({});
  render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><SourceNotes subject={{id:3}}/></QueryClientProvider>);
  fireEvent.click(await screen.findByRole('button',{name:'Edit source note'}));
  expect(screen.getByLabelText('Book edition').disabled).toBe(true);
  fireEvent.change(screen.getByLabelText('Teaching clarification'),{target:{value:'A corrected explanation.'}});
  fireEvent.click(screen.getByRole('button',{name:'Save new version'}));
  await waitFor(()=>expect(api.saveSourceNote).toHaveBeenCalledWith(3,expect.objectContaining({document_id:9,expected_sha256:'b'.repeat(64),expected_version:2,first_page:5,last_page:6,teaching_note:'A corrected explanation.'})));
});
