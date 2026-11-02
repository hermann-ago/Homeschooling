/* @vitest-environment jsdom */
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
const api=vi.hoisted(()=>({estimate:vi.fn(),start:vi.fn()}));
vi.mock('../api/preparation',()=>({curriculumPrepApi:api}));
import {CurriculumPreparationCells,CurriculumPreparationDialog} from './CurriculumLessonPrep';
const topic={id:2,title:'Synthetic lesson'};
const ready={script_status:'ready',can_prepare:true,audio:{status:'missing'}};
it('distinguishes review in progress and a saved script needing source clarification',()=>{
  const prepare=vi.fn();
  const view=render(<CurriculumPreparationCells topic={topic} status={{...ready,job:{status:'running',phase:'review'}}} onPrepare={prepare}/>);
  expect(screen.getByText('Reviewing script…')).toBeTruthy();
  view.rerender(<CurriculumPreparationCells topic={topic} status={{...ready,review:{status:'needs_source_review',summary:'Script saved · source clarification needed'}}} onPrepare={prepare}/>);
  expect(screen.getByText('Script saved · source clarification needed')).toBeTruthy();
  expect(screen.queryByRole('button',{name:'Prepare advanced audio for Synthetic lesson'})).toBeNull();
  fireEvent.click(screen.getByRole('button',{name:'Prepare options for Synthetic lesson'}));
  expect(prepare).toHaveBeenCalledWith('both');
});
beforeEach(()=>{localStorage.clear();api.estimate.mockResolvedValue({script:{allowed:true,reused:false,estimated_cost_usd:.01},audio:{allowed:true,estimated_cost_usd:null},allowed:true});});
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.resetAllMocks();vi.unstubAllGlobals();});
function dialog(extra={}) {
  const close=vi.fn();
  render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><CurriculumPreparationDialog learner={1} topic={topic} status={ready} target="both" onClose={close} {...extra}/></QueryClientProvider>);
  return close;
}

it('lets preparation select Google audio for this lesson',async()=>{
  dialog();
  fireEvent.change(screen.getByLabelText('Audio provider'),{target:{value:'google-gemini'}});
  fireEvent.click(screen.getByRole('button',{name:'Check cost and prepare'}));
  await waitFor(()=>expect(api.estimate).toHaveBeenCalled());
  expect(api.estimate.mock.calls[0][0].audio_provider).toBe('google-gemini');
});

it('shows the actual script writer and reasoning setting before purchase',async()=>{
  api.estimate.mockResolvedValue({script:{allowed:true,reused:false,estimated_cost_usd:.2,model:'synthetic-preparation-model',reasoning_effort:'high'},allowed:true});
  dialog({target:'guide'});
  fireEvent.click(screen.getByRole('button',{name:'Check cost and prepare'}));
  expect(await screen.findByText('Script writer: synthetic-preparation-model · high reasoning')).toBeTruthy();
  expect(api.start).not.toHaveBeenCalled();
});

it('distinguishes a ready script from missing advanced audio and offers row actions',()=>{
  const prepare=vi.fn();
  render(<CurriculumPreparationCells topic={topic} status={ready} onPrepare={prepare}/>);
  expect(screen.getByText('Ready')).toBeTruthy();
  fireEvent.click(screen.getByRole('button',{name:'Prepare advanced audio for Synthetic lesson'}));
  expect(prepare).toHaveBeenCalledWith('audio');
});

it('labels partial Google recordings without offering a retry of a saved refusal',()=>{
  render(<CurriculumPreparationCells topic={topic} status={{...ready,audio:{status:'ready_with_fallback'}}} onPrepare={()=>{}}/>);
  expect(screen.getByText(/Google voice · some passages text-only/)).toBeTruthy();
  expect(screen.queryByRole('button',{name:'Prepare advanced audio for Synthetic lesson'})).toBeNull();
  expect(screen.getByRole('button',{name:'Prepare options for Synthetic lesson'})).toBeTruthy();
});

it('identifies an imported Inworld recording as ready',()=>{
  render(<CurriculumPreparationCells topic={topic} status={{...ready,audio:{status:'ready',provider:'inworld',voice:'Clive'}}} onPrepare={()=>{}}/>);
  expect(screen.getByText('Ready · Inworld TTS-2')).toBeTruthy();
  expect(screen.queryByRole('button',{name:'Prepare advanced audio for Synthetic lesson'})).toBeNull();
});

it('distinguishes fully declined audio from a partial recording',()=>{
  render(<CurriculumPreparationCells topic={topic} status={{...ready,audio:{status:'ready_with_fallback',recorded_parts:0,parts:2}}} onPrepare={()=>{}}/>);
  expect(screen.getByText('Google voice declined · no audio saved')).toBeTruthy();
  expect(screen.queryByText(/some passages text-only/)).toBeNull();
});

it('keeps stale recordings visibly tied to the saved script and shows a running job',()=>{
  const result=render(<CurriculumPreparationCells topic={topic} status={{...ready,script_status:'outdated',audio:{status:'ready'}}} onPrepare={()=>{}}/>);
  expect(screen.getByText('Saved · update available')).toBeTruthy();
  expect(screen.getByText('For the saved script')).toBeTruthy();
  result.rerender(<CurriculumPreparationCells topic={topic} status={{...ready,job:{status:'running',phase:'audio'},audio:{status:'aligning',parts:4,completed_parts:2}}} onPrepare={()=>{}}/>);
  expect(screen.getByText('2/4 synchronized')).toBeTruthy();
  expect(screen.getByRole('button',{name:'Prepare options for Synthetic lesson'}).disabled).toBe(true);
});

it('estimates before generation and retries an ambiguous submission with the same durable identity',async()=>{
  const close=dialog();
  fireEvent.click(screen.getByRole('button',{name:'Check cost and prepare'}));
  await screen.findByLabelText('Preparation estimate');
  expect(api.start).not.toHaveBeenCalled();
  api.start.mockRejectedValueOnce(new Error('Connection lost')).mockResolvedValueOnce({id:'job',status:'queued'});
  fireEvent.click(screen.getByRole('button',{name:'Prepare in background'}));
  await screen.findByRole('alert');
  const command=api.start.mock.calls[0][0];
  expect(command.target).toBe('both');
  expect(command.operation_id).toBeTruthy();
  fireEvent.click(screen.getByRole('button',{name:'Prepare in background'}));
  await waitFor(()=>expect(close).toHaveBeenCalled());
  expect(api.start.mock.calls[1][0]).toEqual(command);
});

it('prevents generation when the cost check is blocked',async()=>{
  api.estimate.mockResolvedValue({script:{estimated_cost_usd:.2,allowed:false},allowed:false});
  dialog();fireEvent.click(screen.getByRole('button',{name:'Check cost and prepare'}));
  await screen.findByRole('alert');
  expect(screen.getByRole('button',{name:'Prepare in background'}).disabled).toBe(true);
  expect(api.start).not.toHaveBeenCalled();
});

it('queues on an HTTP phone without randomUUID and survives unavailable browser storage',async()=>{
  vi.stubGlobal('crypto',{});
  vi.spyOn(Storage.prototype,'setItem').mockImplementation(()=>{throw new Error('Storage unavailable');});
  api.start.mockRejectedValueOnce(new Error('Connection lost')).mockResolvedValueOnce({id:'phone-job',status:'queued'});
  const close=dialog();
  fireEvent.click(screen.getByRole('button',{name:'Check cost and prepare'}));
  await screen.findByLabelText('Preparation estimate');
  fireEvent.click(screen.getByRole('button',{name:'Prepare in background'}));
  expect(await screen.findByRole('alert')).toHaveProperty('textContent','Connection lost');
  expect(screen.getByRole('button',{name:'Prepare in background'}).disabled).toBe(false);
  fireEvent.click(screen.getByRole('button',{name:'Prepare in background'}));
  await waitFor(()=>expect(close).toHaveBeenCalled());
  expect(api.start.mock.calls[0][0].operation_id).toMatch(/^[A-Za-z0-9_-]{8,100}$/);
  expect(api.start.mock.calls[1][0]).toEqual(api.start.mock.calls[0][0]);
});

it('shows active audio progress without offering another purchase',()=>{
  dialog({status:{...ready,job:{status:'running',phase:'audio'},audio:{status:'running',parts:10,completed_parts:4}}});
  expect(screen.getByText('4 of 10 voice sections synchronized.')).toBeTruthy();
  expect(screen.getByText(/home computer continues preparing/)).toBeTruthy();
  expect(screen.queryByRole('button',{name:'Check cost and prepare'})).toBeNull();
  expect(screen.getAllByRole('button',{name:'Close'}).every(button=>!button.disabled)).toBe(true);
});

it('makes a known script replacement explicit and sends its durable recovery flag',async()=>{
  const close=dialog({status:{...ready,job:{recovery:'replace_script',error:'The provider returned no lesson content.'}}});
  expect(screen.getByText(/one replacement script; its cost is tracked/)).toBeTruthy();
  fireEvent.click(screen.getByRole('button',{name:'Check cost and prepare'}));
  await screen.findByLabelText('Preparation estimate');
  api.start.mockResolvedValue({id:'recovery-job'});
  fireEvent.click(screen.getByRole('button',{name:'Prepare in background'}));
  await waitFor(()=>expect(close).toHaveBeenCalled());
  expect(api.start.mock.calls[0][0].replace_invalid).toBe(true);
});

it('keeps audio synchronization free by default and requires an explicit replacement choice',()=>{
  dialog({target:'audio',status:{...ready,audio:{status:'alignment_review'},job:{recovery:'repair_audio'}}});
  const choice=screen.getByRole('checkbox',{name:/Request one replacement for the failed audio block/});
  expect(choice.checked).toBe(false);
  fireEvent.click(choice);expect(choice.checked).toBe(true);
});

it('allows an explicit Google script after a refusal without an app spending cap',async()=>{
  const close=dialog({status:{...ready,script_status:'missing',job:{error_code:'provider_refusal',error:'The provider declined this request.'}}});
  fireEvent.change(screen.getByRole('combobox',{name:'Script provider'}),{target:{value:'google'}});
  expect(screen.queryByLabelText('Maximum for the tutor script (US$)')).toBeNull();
  fireEvent.click(screen.getByRole('button',{name:'Check cost and prepare'}));
  await screen.findByLabelText('Preparation estimate');
  expect(api.estimate.mock.calls[0][0]).toMatchObject({teaching_provider:'google',replace_invalid:false});
  api.start.mockResolvedValue({id:'google-job'});
  fireEvent.click(screen.getByRole('button',{name:'Prepare in background'}));
  await waitFor(()=>expect(close).toHaveBeenCalled());
  expect(api.start.mock.calls[0][0]).toMatchObject({teaching_provider:'google'});
});

it('restores the previous provider and allows intentional script regeneration',async()=>{
  dialog({status:{...ready,job:{teaching_provider:'google',maximum_guide_usd:.15,maximum_audio_usd:.6}}});
  expect(screen.getByRole('combobox',{name:'Script provider'}).value).toBe('google');
  expect(screen.queryByLabelText('Maximum for advanced audio (US$)')).toBeNull();
  fireEvent.click(screen.getByRole('checkbox',{name:/Generate a new tutor script/}));
  fireEvent.click(screen.getByRole('button',{name:'Check cost and prepare'}));
  await screen.findByLabelText('Preparation estimate');
  expect(api.estimate.mock.calls[0][0]).toMatchObject({rewrite:true,teaching_provider:'google',maximum_guide_usd:2});
});
