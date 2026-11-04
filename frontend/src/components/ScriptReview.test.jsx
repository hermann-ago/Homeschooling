/* @vitest-environment jsdom */
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
const api=vi.hoisted(()=>({scriptReview:vi.fn(),retryScriptReview:vi.fn()}));
vi.mock('../api/tutor',()=>({tutorApi:api}));
import ScriptReview from './ScriptReview';
const failed={input_sha256:'a'.repeat(64),status:{status:'failed',summary:'Script saved · review could not finish'},review:{data:{error:'Synthetic connection failed',findings:[]}}};
beforeEach(()=>api.scriptReview.mockResolvedValue(failed));
afterEach(()=>{cleanup();vi.resetAllMocks();});
function show(){render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><ScriptReview guideId="guide-synthetic"/></QueryClientProvider>);}

it('shows saved review failure and sends a bounded explicit retry against exact inputs',async()=>{
  show();await screen.findByText('Synthetic connection failed');
  expect(api.retryScriptReview).not.toHaveBeenCalled();
  api.retryScriptReview.mockResolvedValue({});
  api.scriptReview.mockResolvedValue({...failed,status:{status:'approved',summary:'Script reviewed'},review:{data:{findings:[]}}});
  expect(screen.queryByLabelText('Maximum for script review (US$)')).toBeNull();
  fireEvent.click(screen.getByRole('button',{name:'Review saved script'}));
  await screen.findByText('Script reviewed');
  expect(api.retryScriptReview).toHaveBeenCalledWith('guide-synthetic',{expected_input_sha256:'a'.repeat(64),maximum_usd:.30});
});

it('shows a blocking finding without an automatic rewrite or review retry',async()=>{
  api.scriptReview.mockResolvedValue({...failed,status:{status:'needs_source_review',summary:'Source clarification needed'},review:{data:{findings:[{severity:'blocking',category:'source_conflict',detail:'This assertion conflicts with the checked source note.',suggestion:'Add an explicit source clarification.'}]}}});
  show();await screen.findByText('Add an explicit source clarification.');
  expect(screen.getByText(/Generate a new tutor script/)).toBeTruthy();
  await waitFor(()=>expect(api.retryScriptReview).not.toHaveBeenCalled());
  expect(screen.queryByRole('button',{name:'Review saved script'})).toBeNull();
});

it('lists the teacher answer key recorded with the script',async()=>{
  api.scriptReview.mockResolvedValue({...failed,status:{status:'approved',summary:'Script reviewed'},review:{data:{findings:[]}},
    answer_key:[{prompt:'3. ____ the Conqueror captured Constantinople.',answer:'Mehmed',answer_page:174},{prompt:'Draw a map.',answer:null,answer_page:null}]});
  show();await screen.findByText('Answer key (teacher only)');
  expect(screen.getByText('Mehmed')).toBeTruthy();
  expect(screen.getByText(/key page 174/)).toBeTruthy();
  expect(screen.getByText('No answer in the key')).toBeTruthy();
});

it('lets a grown-up approve the expected answers for boxes the key does not cover',async()=>{
  api.approveAnswers=vi.fn().mockResolvedValue({});
  api.scriptReview.mockResolvedValue({...failed,status:{status:'approved',summary:'Script reviewed'},review:{data:{findings:[]}},
    answer_key:[{index:0,prompt:'Complete com h.',answer:null,blanks:['__umor:','__orta:'],proposed_answers:['humor','orta'],approved_answers:null},
      {index:1,prompt:'Coloque em ordem.',answer:null,blanks:['1º'],proposed_answers:['Dromedário'],approved_answers:null}]});
  show();await screen.findByText('Answers to approve (no answer key)');
  const second=screen.getByLabelText('Expected answer for __orta:');
  expect(second.value).toBe('orta');
  fireEvent.change(second,{target:{value:'horta'}});
  fireEvent.click(screen.getByRole('button',{name:'Approve all 2'}));
  await waitFor(()=>expect(api.approveAnswers).toHaveBeenCalledTimes(2));
  expect(api.approveAnswers).toHaveBeenCalledWith('guide-synthetic',0,['humor','horta']);
  expect(api.approveAnswers).toHaveBeenCalledWith('guide-synthetic',1,['Dromedário']);
});
