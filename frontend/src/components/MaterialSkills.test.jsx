/* @vitest-environment jsdom */
import React from 'react';
import {render,screen,fireEvent,waitFor,cleanup} from '@testing-library/react';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {afterEach,it,expect,vi} from 'vitest';
import {FeedbackProvider} from '../ui';
const api=vi.hoisted(()=>({materialSkills:vi.fn(),saveMaterialSkill:vi.fn()}));
vi.mock('../api/books',()=>({booksApi:api}));
import MaterialSkills from './MaterialSkills';
afterEach(()=>{cleanup();vi.clearAllMocks();});
it('shows editable material skills and keeps earlier instructions as a restorable draft',async()=>{
  api.materialSkills.mockResolvedValue({skills:[{key:'book-json',title:'Livro em JSON',description:'Source structure',version:1,content:'Current instructions',history:[{id:1,version:0,content:'Earlier instructions'}]}]});
  api.saveMaterialSkill.mockResolvedValue({version:2});
  render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><FeedbackProvider><MaterialSkills/></FeedbackProvider></QueryClientProvider>);
  fireEvent.click(screen.getByText('Skills dos materiais'));
  fireEvent.click(await screen.findByRole('button',{name:'Livro em JSON · v1'}));
  expect(screen.getByLabelText('Instruções da skill de materiais').value).toBe('Current instructions');
  fireEvent.change(screen.getByLabelText('Histórico da skill de materiais'),{target:{value:'0'}});
  expect(screen.getByText('Earlier instructions')).toBeTruthy();
  fireEvent.click(screen.getByRole('button',{name:'Usar como rascunho'}));
  expect(api.saveMaterialSkill).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button',{name:'Salvar nova versão'}));
  await waitFor(()=>expect(api.saveMaterialSkill).toHaveBeenCalledWith('book-json','Earlier instructions',1));
});
