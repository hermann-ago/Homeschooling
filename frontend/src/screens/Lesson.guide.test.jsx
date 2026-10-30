/* @vitest-environment jsdom */
import React from 'react';
import {render,screen,fireEvent,waitFor,cleanup} from '@testing-library/react';
import {it,expect,vi,afterEach} from 'vitest';
import {FeedbackProvider} from '../ui';
import {MemoryRouter} from 'react-router';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
const api=vi.hoisted(()=>({estimateGuide:vi.fn(),writeGuide:vi.fn()}));
const preparation=vi.hoisted(()=>({lesson:vi.fn(),estimate:vi.fn(),start:vi.fn()}));
vi.mock('../api/tutor',()=>({tutorApi:api}));
vi.mock('../api/preparation',()=>({curriculumPrepApi:preparation}));
vi.mock('../components/NarratorPicker',()=>({default:()=> <p>Narrator selection</p>}));
vi.mock('pdfjs-dist',()=>({getDocument:vi.fn()}));
vi.mock('../components/PageViewer',()=>({default:()=>null}));
vi.mock('../components/OriginalSourcePage',()=>({default:()=>null}));
import {GuidePanel,LessonReadMode} from './Lesson';
afterEach(()=>{cleanup();vi.resetAllMocks();});

it('exposes guided teaching and the exact saved session from the book-only view',()=>{
  const change=vi.fn();
  render(<MemoryRouter><LessonReadMode mode="book" onChange={change} resumePath="/lesson?learner=1&topic=2&session=saved-session"/></MemoryRouter>);
  expect(screen.getByRole('link',{name:'Resume this tutoring lesson'}).getAttribute('href')).toContain('session=saved-session');
  fireEvent.click(screen.getByRole('button',{name:'Guided lesson'}));
  expect(change).toHaveBeenCalledWith('guide');
});

it('offers guide and voice together outside settings and waits for explicit generation',async()=>{
  preparation.lesson.mockResolvedValue({title:'Chapter 2',script_status:'missing',audio:{status:'missing'}});
  preparation.estimate.mockResolvedValue({allowed:true,script:{allowed:true,reused:false,cached_invalid_reply:true,estimated_cost_usd:.02},audio:{allowed:true,estimated_cost_usd:null}});
  preparation.start.mockResolvedValue({id:'prepared'});const changed=vi.fn();
  render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><FeedbackProvider><GuidePanel guide={null} learner={1} topic={2} onChanged={changed}/></FeedbackProvider></QueryClientProvider>);
  fireEvent.click(screen.getByRole('button',{name:'Prepare lesson & voice'}));
  expect(screen.getByLabelText('What to prepare').value).toBe('both');
  expect(screen.queryByText(/Maximum for/)).toBeNull();
  fireEvent.click(screen.getByRole('button',{name:'Check cost and prepare'}));
  await screen.findByLabelText('Preparation estimate');
  expect(preparation.start).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button',{name:'Prepare in background'}));
  await waitFor(()=>expect(preparation.start).toHaveBeenCalledWith(expect.objectContaining({learner:1,topic:2,target:'both',replace_invalid:true})));
  await waitFor(()=>expect(changed).toHaveBeenCalled());
});
