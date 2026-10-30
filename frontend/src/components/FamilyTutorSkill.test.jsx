/* @vitest-environment jsdom */
import React from 'react';
import {render,screen,fireEvent,cleanup,waitFor} from '@testing-library/react';
import {afterEach,it,expect,vi} from 'vitest';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
const api=vi.hoisted(()=>({teachingStyle:vi.fn(),saveTeachingStyle:vi.fn()}));
vi.mock('../api/tutor',()=>({tutorApi:api}));
import FamilyTutorSkill from './FamilyTutorSkill';

afterEach(()=>{cleanup();vi.resetAllMocks();});
function show(){
  const client=new QueryClient({defaultOptions:{queries:{retry:false}}});
  api.teachingStyle.mockResolvedValue({skill:{version:1,content:'Current friendly style.',profiles:{'1':{age:9,as_of:null}}},
    learners:[{id:1,name:'Synthetic learner'}],history:[{id:1,version:0,content:'Earlier style.',profiles:{}}]});
  render(<QueryClientProvider client={client}><FamilyTutorSkill/></QueryClientProvider>);
}

it('edits a shared skill and confirmed age without starting paid generation',async()=>{
  show();
  fireEvent.click(await screen.findByRole('button',{name:/View and edit tutoring skill · v1/}));
  expect(screen.getByLabelText('Synthetic learner age').value).toBe('9');
  fireEvent.click(screen.getByRole('button',{name:'Edit instructions'}));
  fireEvent.change(screen.getByLabelText('Teaching instructions'),{target:{value:'A warmer shared style.'}});
  fireEvent.change(screen.getByLabelText('Synthetic learner age'),{target:{value:'10'}});
  api.saveTeachingStyle.mockResolvedValue({version:2});
  fireEvent.click(screen.getByRole('button',{name:'Save new version'}));
  await waitFor(()=>expect(api.saveTeachingStyle).toHaveBeenCalledWith('A warmer shared style.',
    {'1':{age:10,as_of:expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/)}},1));
  expect(await screen.findByRole('status')).toBeTruthy();
});

it('keeps the draft on a version conflict and can inspect earlier instructions',async()=>{
  show();
  fireEvent.click(await screen.findByRole('button',{name:/View and edit tutoring skill · v1/}));
  fireEvent.change(screen.getByLabelText('Shared tutoring skill versions'),{target:{value:'0'}});
  expect(screen.getByText('Earlier style.')).toBeTruthy();
  expect(screen.getByRole('button',{name:'Save new version'}).disabled).toBe(true);
  fireEvent.click(screen.getByRole('button',{name:'Use as draft'}));
  api.saveTeachingStyle.mockRejectedValue(new Error('Another device changed the skill.'));
  fireEvent.click(screen.getByRole('button',{name:'Save new version'}));
  expect(await screen.findByRole('alert')).toHaveProperty('textContent',expect.stringContaining('Your draft is kept here.'));
  expect(screen.getByLabelText('Teaching instructions').value).toBe('Earlier style.');
});

it('saves a birth year without turning it into a guessed fixed age',async()=>{
  show();
  fireEvent.click(await screen.findByRole('button',{name:/View and edit tutoring skill · v1/}));
  const year=new Date().getFullYear()-9;
  fireEvent.change(screen.getByLabelText('Synthetic learner birth year'),{target:{value:String(year)}});
  expect(screen.getByLabelText('Synthetic learner age').value).toBe('');
  expect(screen.getByText(new RegExp(`Born ${year} · age 8–9`))).toBeTruthy();
  api.saveTeachingStyle.mockResolvedValue({version:2});
  fireEvent.click(screen.getByRole('button',{name:'Save new version'}));
  await waitFor(()=>expect(api.saveTeachingStyle).toHaveBeenCalledWith('Current friendly style.',
    {'1':{birth_year:year,as_of:expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/)}},1));
});

it('stores an exact birthday as a date and removes the old fixed age',async()=>{
  show();
  fireEvent.click(await screen.findByRole('button',{name:/View and edit tutoring skill · v1/}));
  fireEvent.change(screen.getByLabelText('Synthetic learner date of birth'),{target:{value:'2017-05-19'}});
  expect(screen.getByLabelText('Synthetic learner age').value).toBe('');
  api.saveTeachingStyle.mockResolvedValue({version:2});
  fireEvent.click(screen.getByRole('button',{name:'Save new version'}));
  await waitFor(()=>expect(api.saveTeachingStyle).toHaveBeenCalledWith('Current friendly style.',
    {'1':{birth_date:'2017-05-19',as_of:expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/)}},1));
});
