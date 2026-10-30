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
