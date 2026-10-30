/* @vitest-environment jsdom */
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({ state: vi.fn(), event: vi.fn(), access: vi.fn(), attachWork: vi.fn() }));
vi.mock('../../api/activities', () => ({ activitiesApi: api }));
vi.mock('../../api/tutor', () => ({ tutorApi: { attachWork: api.attachWork } }));
import ActivityLesson from './ActivityLesson';
import ActivityCard from './ActivityCards';
import { activityRegistry } from './registry';
import {storageKey} from './durable';

const makeActivity = (patch = {}) => ({ id: 'a1', kind: 'ask_question', status: 'pending', origin: 'required_book',
  content: { prompt: 'Why did the travelers stop?', response_modes: ['text', 'device_dictation', 'photo'] },
  interaction: { id: 'i1', status: 'awaiting_input', stage: 'initial' }, responses: [], messages: [], ...patch });
const makeState = (activity = makeActivity(), patch = {}) => ({ session_id: 's1', revision: 1, playback: {}, active_activity: activity,
  activities: [activity], events: [], event_cursor: 0, on_break: false, ...patch });
const show = (props = {}) => render(<ActivityLesson sessionId="s1" {...props} />);

beforeEach(() => { vi.resetAllMocks(); window.localStorage.clear(); api.state.mockResolvedValue(makeState()); });
afterEach(cleanup);

describe('Shared activity lesson', () => {
  it.each([
    ['introduce', 'pending', false, 'Continue lesson'],
    ['read_source', 'answered', false, 'Continue lesson'],
    ['ask_question', 'answered', false, 'Continue lesson'],
    ['close_lesson', 'pending', false, 'Finish lesson'],
    ['introduce', 'pending', true, 'Return to lesson'],
  ])('focuses the main action for %s / %s / break %s', async (kind, status, on_break, label) => {
    api.state.mockResolvedValue(makeState(makeActivity({ kind, status,
      content: { text: 'A lesson step.', prompt: 'A question.' },
      interaction: { id: 'ready', status: 'ready_to_continue' } }), { on_break }));
    show();
    const button = await screen.findByRole('button', { name: label, exact: true });
    await waitFor(() => expect(document.activeElement).toBe(button));
    expect(button.tagName).toBe('BUTTON');
    expect(fireEvent.keyDown(button, { key: 'Enter', repeat: true })).toBe(false);
    expect(api.event).not.toHaveBeenCalled();
  });

  it('does not focus the reading-complete action while a reading is pending', async () => {
    api.state.mockResolvedValue(makeState(makeActivity({kind:'read_source',content:{text:'Read this passage.'},interaction:{id:'reading',status:'ready_to_continue'}})));
    show();
    const done = await screen.findByRole('button', { name: 'I have finished this reading' });
    expect(document.activeElement).not.toBe(done);
    expect(api.event).not.toHaveBeenCalled();
  });

  it('submits one typed exercise command and presents its saved per-part results', async () => {
    const exercise={scope:'exercise',can_type:true,instruction:'Complete:',items:[{activity_id:'a1',label:'A',prompt:'First blank'},{activity_id:'a2',label:'B',prompt:'Second blank'}]};
    api.state.mockResolvedValue(makeState(makeActivity({kind:'request_book_work',interaction:{id:'i1',status:'awaiting_work'}}),{page_work:{available_count:2,exercise}}));
    api.event.mockResolvedValue(makeState(makeActivity({status:'answered',interaction:{id:'i1',status:'completed'}}),{revision:2,page_work:{...exercise,id:'typed-job',capture_method:'typed',status:'completed',items:exercise.items.map(item=>({...item,confirmed_text:'leão',feedback:'Accent checked.'}))}}));
    show();
    fireEvent.change(await screen.findByLabelText('Answer A'),{target:{value:'leão'}});
    fireEvent.change(screen.getByLabelText('Answer B'),{target:{value:'irmã'}});
    fireEvent.click(screen.getByRole('button',{name:'Check answers'}));
    expect(await screen.findByRole('button',{name:'Continue lesson',exact:true})).toBeTruthy();
    expect(screen.getAllByText('Accent checked.')).toHaveLength(2);
    expect(api.event).toHaveBeenCalledTimes(1);
    expect(api.event.mock.calls[0][1]).toMatchObject({type:'submit_exercise_answers',activity_id:'a1',interaction_id:'i1',payload:{items:[{item_id:'a1',text:'leão'},{item_id:'a2',text:'irmã'}]}});
    expect(screen.queryByRole('button',{name:'I have finished writing in my book'})).toBeNull();
  });
  it('shows all parts of one exercise by default without individual writing controls', async () => {
    const exercise={scope:'exercise',instruction:'Fill in the blanks:',items:'ABCDEF'.split('').map((label,index)=>({activity_id:`a${index+1}`,label,prompt:`Sentence ${label} ___`}))};
    api.state.mockResolvedValue(makeState(makeActivity({kind:'request_book_work',interaction:{id:'i1',status:'awaiting_work'}}),{page_work:{available_count:8,exercise}}));
    api.event.mockResolvedValue(makeState(makeActivity(),{revision:2,page_work:{...exercise,id:'exercise-job',status:'capture'}}));
    show();
    expect(await screen.findByText('One exercise · All parts together')).toBeTruthy();
    expect(within(screen.getByRole('region',{name:'Page answers together'})).getAllByRole('listitem')).toHaveLength(6);
    expect(screen.getByText('Fill in the blanks:')).toBeTruthy();
    expect(screen.queryByRole('button',{name:'I have finished writing in my book'})).toBeNull();
    expect(screen.queryByRole('button',{name:'Send this page together'})).toBeNull();
    fireEvent.click(screen.getByRole('button',{name:'I have finished these answers'}));
    await screen.findByRole('button',{name:'Take a photo of these answers'});
    expect(api.event.mock.calls[0][1]).toMatchObject({type:'open_page_work',payload:{scope:'exercise'}});
    expect(screen.getByText(/you do not need the whole book page/)).toBeTruthy();
  });
  it('lets the child choose individual answers instead of the default exercise photo', async () => {
    api.state.mockResolvedValue(makeState(makeActivity(),{page_work:{available_count:2,exercise:{scope:'exercise',instruction:'Complete:',items:[{activity_id:'a1',label:'A',prompt:'First blank'},{activity_id:'a2',label:'B',prompt:'Next blank'}]}}}));
    show();fireEvent.click(await screen.findByRole('button',{name:'Answer one part at a time instead'}));
    expect(await screen.findByLabelText('Your answer')).toBeTruthy();
    expect(api.event).not.toHaveBeenCalled();
  });
  it('opens adjacent page work with a durable command and one expanded capture area',async()=>{
    api.state.mockResolvedValue(makeState(makeActivity(),{page_work:{available_count:3}}));
    api.event.mockResolvedValue(makeState(makeActivity(),{revision:2,page_work:{id:'page-job',status:'capture',items:[
      {activity_id:'a1',page:10,prompt:'Book item one'}, {activity_id:'a2',page:10,prompt:'Book item two'},
      {activity_id:'a3',page:10,prompt:'Book item three'}]}}));
    show();fireEvent.click(await screen.findByRole('button',{name:'Send this page together'}));
    expect(await screen.findByRole('region',{name:'Page answers together'})).toBeTruthy();
    expect(api.event.mock.calls[0][1]).toMatchObject({type:'open_page_work',activity_id:'a1',interaction_id:'i1'});
    expect(screen.getByRole('region',{name:'Current lesson action'}).dataset.expanded).toBe('true');
    expect(screen.getByText('Book page 10 · 3 answers together')).toBeTruthy();
    expect(screen.queryByLabelText('Your answer')).toBeNull();
  });
  it('shows Continue lesson after a shared photo without asking for an already checked item',async()=>{
    api.state.mockResolvedValue(makeState(makeActivity({status:'answered',interaction:{id:'i1',status:'completed'},
      practice_section:{id:'section',title:'True or false',item:1,total:3,completed:3}}),{page_work:{id:'page-job',status:'completed',items:[
        {activity_id:'a1',page:10,prompt:'Book item one',confirmed_text:'False',feedback:'That matches the source.'}]}}));
    show();expect(await screen.findByRole('button',{name:'Continue lesson',exact:true})).toBeTruthy();
    expect(screen.queryByRole('button',{name:'Next item'})).toBeNull();
  });
  it('restores saved words when an older capture method is no longer available',async()=>{
    localStorage.setItem(storageKey('s1','draft.a1.i1'),JSON.stringify({method:'choice',text:'They joined together.',
      choice_ids:['old-option'],reasoning:'',evidence_ids:[],response_id:'keep-original-submission'}));
    api.event.mockResolvedValue(makeState(makeActivity({status:'answered'}),{revision:2}));
    show();
    const answer=await screen.findByRole('textbox',{name:'Your answer',exact:true});
    expect(answer.value).toBe('They joined together.');
    expect(screen.getByText(/answer options changed/)).toBeTruthy();
    fireEvent.keyDown(answer,{key:'Enter'});
    await waitFor(()=>expect(api.event).toHaveBeenCalled());
    expect(api.event.mock.calls[0][1].payload).toMatchObject({method:'typed',text:'They joined together.',response_id:'keep-original-submission'});
  });
  it('captures labeled matches without making the child type all pairs', async () => {
    api.state.mockResolvedValue(makeState(makeActivity({content:{prompt:'Match each animal.',response_modes:['text'],
      matching:{items:[{id:'bird',label:'Bird'},{id:'fish',label:'Fish'}],options:[{id:'air',label:'Air'},{id:'water',label:'Water'}]}}})));
    api.event.mockResolvedValue(makeState(makeActivity({status:'answered'}),{revision:2}));
    show();
    fireEvent.change(await screen.findByLabelText('Bird'),{target:{value:'air'}});
    expect(screen.getByRole('button',{name:'Check my answer'}).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText('Fish'),{target:{value:'water'}});
    fireEvent.keyDown(screen.getByLabelText('Fish'),{key:'Enter'});
    await waitFor(()=>expect(api.event).toHaveBeenCalled());
    expect(api.event.mock.calls[0][1]).toMatchObject({type:'submit_response',payload:{matches:{bird:'air',fish:'water'},text:'Bird → Air\nFish → Water'}});
  });
  it('keeps practice progress and focuses Continue after an accepted item', async () => {
    const section={id:'practice-1',kind:'spelling',title:'Spelling practice',item:2,total:9,completed:1};
    api.state.mockResolvedValue(makeState(makeActivity({practice_section:section})));
    api.event.mockResolvedValue(makeState(makeActivity({practice_section:{...section,completed:2},status:'answered',interaction:{id:'i1',status:'completed'}}),{revision:2}));
    show();
    expect(await screen.findByText('Spelling practice · 2 of 9')).toBeTruthy();
    fireEvent.change(screen.getByLabelText('Your answer'),{target:{value:'A word'}});
    fireEvent.keyDown(screen.getByLabelText('Your answer'),{key:'Enter'});
    await waitFor(()=>expect(document.activeElement).toBe(screen.getByRole('button',{name:'Next word'})));
    expect(screen.getByRole('progressbar',{name:'2 of 9 items saved'})).toBeTruthy();
  });
  it('explains that the final confirmation saves curriculum completion and sends finish', async () => {
    api.state.mockResolvedValue(makeState(makeActivity({kind:'close_lesson',content:{text:'We have reached the recap.'},
      interaction:{id:'closing-1',status:'ready_to_continue'}}),{can_finish:false}));
    api.event.mockResolvedValue(makeState(null,{status:'completed',revision:2,activities:[]}));
    show();
    expect(await screen.findByText(/Choose Finish lesson to mark this chapter complete in Curriculum/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button',{name:'Finish lesson'}));
    await waitFor(()=>expect(api.event).toHaveBeenCalled());
    expect(api.event.mock.calls[0][1]).toMatchObject({type:'finish',activity_id:'a1',interaction_id:'closing-1'});
  });
  it('accepts a typed accented word immediately without requiring book completion or a photo', async () => {
    api.state.mockResolvedValue(makeState(makeActivity({kind:'request_book_work',content:{prompt:'Coloque o til: leao.',
      evidence_requirement:'spelling',response_modes:['text','photo']},interaction:{id:'i1',status:'awaiting_work',stage:'initial'}})));
    api.event.mockResolvedValue(makeState(makeActivity({status:'answered'}),{revision:2}));
    show();
    fireEvent.change(await screen.findByLabelText('Your answer'),{target:{value:'leão'}});
    expect(screen.queryByRole('button',{name:'I have finished writing in my book'})).toBeNull();
    expect(screen.getByText('Type the complete word, including its accents. A photo is optional.')).toBeTruthy();
    fireEvent.keyDown(screen.getByLabelText('Your answer'),{key:'Enter'});
    await waitFor(()=>expect(api.event).toHaveBeenCalled());
    expect(api.event.mock.calls[0][1]).toMatchObject({type:'submit_response',payload:{text:'leão',method:'typed',assess_after_save:true}});
  });
  it('recovers a confirmed answer from the former unnecessary photo gate', async () => {
    api.state.mockResolvedValue(makeState(makeActivity({ interaction: { id: 'i1', status: 'parent_review' },
      responses: [{ id: 'old-photo', interaction_id: 'i1', method: 'photo', confirmed_text: 'A word', status: 'parent_review', answer_only_recheck_available: true }] })));
    api.event.mockResolvedValue(makeState(makeActivity({status:'answered'}),{revision:2}));
    show();
    fireEvent.click(await screen.findByRole('button',{name:'Check my answer'}));
    await waitFor(()=>expect(api.event).toHaveBeenCalled());
    expect(api.event.mock.calls[0][1]).toMatchObject({type:'assess',payload:{response_id:'old-photo'}});
    expect(screen.queryByText('Parent assessment')).toBeNull();
  });
  it('requires an attached image when Photo of my work is selected', async () => {
    show();
    fireEvent.change(await screen.findByLabelText('How to answer'), { target: { value: 'photo' } });
    fireEvent.change(screen.getByLabelText('What you wrote (optional transcript)'), { target: { value: 'A typed word' } });
    expect(screen.getByRole('button', { name: 'Save answer for confirmation' }).disabled).toBe(true);
    expect(screen.getByText(/Attach a photo before sending/)).toBeTruthy();
    expect(api.event).not.toHaveBeenCalled();
  });
  it('allows Continue after sufficient generated discussion without inventing a follow-up answer', async () => {
    api.state.mockResolvedValue(makeState(makeActivity({ can_continue_discussion: true,
      interaction: { id: 'followup', status: 'awaiting_followup', prompt: 'Add a small detail.' } })));
    api.event.mockResolvedValue(makeState(null, { revision: 2, activities: [] }));
    show();
    fireEvent.click(await screen.findByRole('button', { name: 'Continue lesson' }));
    await waitFor(() => expect(api.event).toHaveBeenCalled());
    expect(api.event.mock.calls[0][1]).toMatchObject({ type: 'continue', interaction_id: 'followup', payload: {} });
  });
  it.each(['tell_it_back', 'explain_thinking'])('submits a %s explanation in one answer box without inventing separate reasoning', async (kind) => {
    api.state.mockResolvedValue(makeState(makeActivity({ kind, content: {
      prompt: 'Explain what happened and why.', response_modes: ['text'], evidence_requirement: 'reasoning', require_reasoning: true,
    } })));
    api.event.mockResolvedValue(makeState(makeActivity({ kind, status: 'answered' }), { revision: 2 }));
    show();
    fireEvent.change(await screen.findByLabelText('Your answer'), { target: { value: 'The little bird helped because it remembered the kindness.' } });
    expect(screen.queryByLabelText('Explain your thinking')).toBeNull();
    expect(screen.getByRole('button', { name: 'Check my answer' }).disabled).toBe(false);
    fireEvent.keyDown(screen.getByLabelText('Your answer'), { key: 'Enter' });
    await waitFor(() => expect(api.event).toHaveBeenCalled());
    expect(api.event.mock.calls[0][1].payload).toMatchObject({ text: 'The little bird helped because it remembered the kindness.', reasoning: '', assess_after_save: true });
  });
  it('shows original choice options once in the active composer and retains the complete historical prompt', async () => {
    const activity = makeActivity({content:{prompt:'Choose the animal. a. Cat b. Tree',response_modes:['choice','text'],
      answer_format:'single_choice',choices:[{id:'a',label:'a. Cat'},{id:'b',label:'b. Tree'}]}});
    api.state.mockResolvedValue(makeState(activity));
    const view=show();
    await screen.findByRole('radio',{name:'a. Cat'});
    expect(screen.getByText('Choose the animal.')).toBeTruthy();
    expect(screen.getAllByText('a. Cat')).toHaveLength(1);
    view.unmount();
    render(<ActivityCard activity={activity} readOnly />);
    expect(screen.getByText('Choose the animal. a. Cat b. Tree')).toBeTruthy();
  });
  it('clears a recovered connection error even when the lesson revision did not change', async () => {
    let poll;
    const interval = window.setInterval;
    const timer = vi.spyOn(window, 'setInterval').mockImplementation((callback, delay) => {
      if (delay === 4000) poll = callback;
      return interval(callback, delay);
    });
    const state = makeState();
    api.state.mockResolvedValueOnce(state).mockRejectedValueOnce(new Error('Temporary connection loss')).mockResolvedValue(state);
    try {
      show();
      await screen.findByLabelText('Your answer');
      await act(async () => { await poll(); });
      expect(screen.getByText('Temporary connection loss')).toBeTruthy();
      await act(async () => { await poll(); });
      expect(screen.queryByText('Temporary connection loss')).toBeNull();
      expect(screen.getByLabelText('Your answer')).toBeTruthy();
    } finally { timer.mockRestore(); }
  });

  it('offers repeated back and start-over commands in lesson options, including from a break', async () => {
    api.state.mockResolvedValue(makeState(makeActivity(), { can_go_back: true, on_break: true }));
    api.event.mockResolvedValue(makeState(makeActivity({ id: 'previous' }), { revision: 2, can_go_back: true }));
    const onContinue = vi.fn();
    show({ onContinue });
    fireEvent.click(await screen.findByLabelText('Lesson options'));
    fireEvent.click(screen.getByRole('button', { name: 'Go back one step' }));
    await waitFor(() => expect(api.event).toHaveBeenCalledTimes(1));
    expect(api.event.mock.calls[0][1]).toMatchObject({ type: 'go_back', activity_id: 'a1', expected_revision: 1 });
    await waitFor(() => expect(onContinue).toHaveBeenCalled());
    fireEvent.click(screen.getByLabelText('Lesson options'));
    fireEvent.click(screen.getByRole('button', { name: 'Start lesson over' }));
    await waitFor(() => expect(api.event).toHaveBeenCalledTimes(2));
    expect(api.event.mock.calls[1][1]).toMatchObject({ type: 'restart_lesson', activity_id: 'previous', expected_revision: 2 });
  });

  it('keeps old answers and feedback in history while a replay shows an empty response space', async () => {
    api.state.mockResolvedValue(makeState(makeActivity({ interaction: { id: 'fresh', replay_of: 'old', sequence: 2, dialogue_start_sequence: 2, status: 'awaiting_input' },
      responses: [{ id: 'old-response', interaction_id: 'old', status: 'assessed', original: { text: 'Earlier answer' } }],
      messages: [{ id: 'old-reply', role: 'teacher', text: 'Earlier feedback', sequence: 2 }] })));
    show();
    expect((await screen.findByLabelText('Your answer')).value).toBe('');
    expect(screen.getByText('Earlier answer')).toBeTruthy();
    expect(screen.getByText('Earlier feedback')).toBeTruthy();
    expect(within(screen.getByLabelText('Current tutor activity')).queryByText('Earlier feedback')).toBeNull();
    expect(api.event).not.toHaveBeenCalled();
  });

  it('disables back at the first step', async () => {
    show();
    fireEvent.click(await screen.findByLabelText('Lesson options'));
    expect(screen.getByRole('button', { name: 'Go back one step' }).disabled).toBe(true);
  });
  it('rechecks the already saved answer against its book key without asking for another answer', async () => {
    const response = { id: 'misgraded', interaction_id: 'earlier-interaction', status: 'assessed', original: { text: 'False.' }, key_recheck_available: true };
    api.state.mockResolvedValue(makeState(makeActivity({ responses: [response] })));
    api.event.mockResolvedValue(makeState(makeActivity({ status: 'answered' }), { revision: 2 }));
    show();
    fireEvent.click(await screen.findByRole('button', { name: 'Recheck this answer against the book key' }));
    await waitFor(() => expect(api.event).toHaveBeenCalled());
    expect(api.event.mock.calls[0][1]).toMatchObject({ type: 'recheck_key', interaction_id: 'i1', payload: { response_id: 'misgraded' } });
  });
  it('requests replacement feedback for the same saved response only after an explicit click', async () => {
    const response = { id: 'saved-answer', interaction_id: 'i1', status: 'assessment_failed', original: { text: 'My words' }, feedback_failure: 'invalid_reply' };
    api.state.mockResolvedValue(makeState(makeActivity({ interaction: { id: 'i1', status: 'assessment_failed' }, responses: [response] })));
    api.event.mockResolvedValue(makeState(makeActivity({ status: 'answered' }), { revision: 2 }));
    show();
    await screen.findByRole('button', { name: 'Generate replacement feedback' });
    expect(api.event).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Generate replacement feedback' }));
    await waitFor(() => expect(api.event).toHaveBeenCalled());
    expect(api.event.mock.calls[0][1]).toMatchObject({ type: 'assess', payload: { response_id: 'saved-answer', replace_invalid_reply: true } });
  });
  it('does not offer another purchase after an invalid replacement and keeps unfinished work available', async () => {
    const response = { id: 'saved-answer', interaction_id: 'i1', status: 'assessment_failed', original: { text: 'My words' }, feedback_failure: 'invalid_reply', feedback_replacement_used: true };
    api.state.mockResolvedValue(makeState(makeActivity({ interaction: { id: 'i1', status: 'assessment_failed' }, responses: [response] })));
    show();
    expect((await screen.findByRole('button', { name: 'Replacement needs review' })).disabled).toBe(true);
    expect(screen.getByRole('button', { name: 'Leave this to revisit' }).disabled).toBe(false);
    expect(screen.getByText('My words')).toBeTruthy();
    expect(api.event).not.toHaveBeenCalled();
  });
  it('keeps failed help recoverable and reuses its identity after deferring it', async () => {
    api.event.mockImplementationOnce(async (session, command) => {
      const next = makeState(makeActivity(), { error: 'Help is pending', events: [{ operation_id: command.operation_id }], pending_support_commands: [command] });
      api.state.mockResolvedValue(next); return next;
    }).mockResolvedValueOnce(makeState());
    show();
    fireEvent.click(await screen.findByRole('button', { name: 'Show an example' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Leave this help request for later' }));
    expect(screen.getByLabelText('Your answer')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Show an example' }));
    await waitFor(() => expect(api.event).toHaveBeenCalledTimes(2));
    expect(api.event.mock.calls[1][1]).toEqual(api.event.mock.calls[0][1]);
  });
  it('sends distinct explanation, example and hint requests from the current question', async () => {
    api.event.mockResolvedValue(makeState());
    show();
    for (const [kind, label] of [['explain', 'Explain that differently'], ['example', 'Show an example'], ['hint', 'Give me a hint']]) {
      fireEvent.click(await screen.findByRole('button', { name: label }));
      await waitFor(() => expect(api.event.mock.calls.at(-1)?.[1]).toMatchObject({ type: 'request_hint', payload: { kind } }));
      await waitFor(() => expect(screen.getByRole('button', { name: label }).disabled).toBe(false));
    }
    expect(api.event).toHaveBeenCalledTimes(3);
  });
  it('registers all twenty-three semantic activities and keeps internal actions without cards', () => {
    expect(Object.keys(activityRegistry)).toHaveLength(23);
    expect(Object.entries(activityRegistry).filter(([, value]) => value.internal).map(([kind]) => kind)).toEqual(['review_progress', 'prepare_lesson', 'record_learning_evidence']);
  });

  it('keeps the current question and input together below the historical conversation', async () => {
    const active = makeActivity();
    const completed = makeActivity({ id: 'done', status: 'answered', content: { prompt: 'Earlier question' }, responses: [{ id: 'r0', original: { text: 'Earlier answer' }, status: 'assessed' }] });
    api.state.mockResolvedValue(makeState(active, { activities: [completed, active, makeActivity({ id: 'future', content: { prompt: 'SECRET upcoming question' } })] }));
    const { container } = show();
    expect(await screen.findByText('Why did the travelers stop?')).toBeTruthy();
    expect(screen.queryByText('SECRET upcoming question')).toBeNull();
    expect(screen.getAllByRole('article', { name: 'Current tutor activity' })).toHaveLength(1);
    expect(container.querySelector('details').open).toBe(false);
    expect(screen.getByText('Earlier answer')).toBeTruthy();
    const conversation = screen.getByRole('generic', { name: 'Lesson conversation' });
    const composer = screen.getByRole('region', { name: 'Current lesson action' });
    expect(within(composer).getByLabelText('Your answer')).toBeTruthy();
    expect(within(composer).getByText('Why did the travelers stop?')).toBeTruthy();
    expect(within(conversation).queryByText('Why did the travelers stop?')).toBeNull();
    expect(within(conversation).getByText('Earlier answer')).toBeTruthy();
    expect(conversation.contains(composer)).toBe(false);
    expect(screen.getByText('Earlier answer').compareDocumentPosition(screen.getByText('Why did the travelers stop?')) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('keeps typed drafts scoped to the interaction after remount', async () => {
    const first = show();
    fireEvent.change(await screen.findByLabelText('Your answer'), { target: { value: 'My original unfinished answer' } });
    first.unmount(); show();
    expect((await screen.findByLabelText('Your answer')).value).toBe('My original unfinished answer');
    expect(api.event).not.toHaveBeenCalled();
  });

  it('keeps session controls in the top bar when the current activity is minimized', async () => {
    show({ renderSessionControls: () => <div role="group" aria-label="Session narration settings"><button>Session voice</button></div> });
    const controls = await screen.findByRole('group', { name: 'Session narration settings' });
    expect(controls.closest('header')).toBeTruthy();
    expect(screen.getByRole('region', { name: 'Current lesson action' }).contains(controls)).toBe(false);
    fireEvent.click(screen.getByRole('button', { name: 'Minimize activity' }));
    expect(screen.getByRole('button', { name: 'Session voice' })).toBeTruthy();
    expect(api.event).not.toHaveBeenCalled();
  });
  it('keeps reading and its controls in an expandable current activity box', async () => {
    api.state.mockResolvedValue(makeState(makeActivity({ kind: 'read_source', content: { text: 'A short assigned passage.' }, interaction: { id: 'reading', status: 'ready_to_continue' } })));
    show({ renderReading: () => <p>The current reading goes here.</p> });
    const box = await screen.findByRole('region', { name: 'Current lesson action' });
    expect(within(box).getByText('The current reading goes here.')).toBeTruthy();
    expect(within(box).getByRole('button', { name: 'I have finished this reading' })).toBeTruthy();
    expect(within(box).getByRole('button', { name: 'I have finished this reading' }).closest('.tutor-workbox-content')).toBeNull();
    expect(within(box).getByRole('button', { name: 'I have finished this reading' }).closest('[aria-label="Lesson step controls"]')).toBeTruthy();
    expect(within(screen.getByLabelText('Lesson conversation')).queryByText('The current reading goes here.')).toBeNull();
    const toggle = within(box).getByRole('button', { name: 'Minimize activity' });
    expect(toggle.getAttribute('aria-expanded')).toBe('true');
    const reading = within(box).getByText('The current reading goes here.');
    fireEvent.click(toggle);
    expect(within(box).getByRole('button', { name: 'Show activity' }).getAttribute('aria-expanded')).toBe('false');
    expect(reading.closest('[hidden]')).toBeTruthy();
    fireEvent.click(within(box).getByRole('button', { name: 'Show activity' }));
    expect(within(box).getByText('The current reading goes here.')).toBe(reading);
    expect(reading.closest('[hidden]')).toBeNull();
    expect(api.event).not.toHaveBeenCalled();
  });

  it('minimizes to a bottom bar without losing the draft or advancing work', async () => {
    const pause = vi.fn();
    show({ onPauseNarration: pause });
    const answer = await screen.findByLabelText('Your answer');
    fireEvent.change(answer, { target: { value: 'An unfinished answer' } });
    const before = pause.mock.calls.length;
    fireEvent.click(screen.getByRole('button', { name: 'Minimize activity' }));
    const box = screen.getByRole('region', { name: 'Current lesson action' });
    expect(box.dataset.minimized).toBe('true');
    expect(screen.queryByRole('textbox', { name: 'Your answer' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Check my answer' })).toBeNull();
    expect(pause.mock.calls.length).toBe(before + 1);
    expect(api.event).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Show activity' }));
    expect(screen.getByLabelText('Your answer')).toBe(answer);
    expect(answer.value).toBe('An unfinished answer');
  });

  it('archives the processed exchange while keeping the new follow-up and feedback in the box', async () => {
    const base = makeActivity();
    const first = { id: 'r1', interaction_id: 'i1', status: 'assessed', original: { text: 'They stopped for water.' } };
    api.event.mockResolvedValue(makeState({ ...base, responses: [first], interaction: { id: 'i2', status: 'awaiting_followup', prompt: 'Why was water important?' },
      interactions: [{ id: 'i1', sequence: 1, prompt: base.content.prompt }, { id: 'i2', sequence: 2, prompt: 'Why was water important?' }], messages: [{ id: 'teacher', role: 'teacher', text: 'Think about their long journey.' }] }, { revision: 2 }));
    show();
    fireEvent.change(await screen.findByLabelText('Your answer'), { target: { value: 'They stopped for water.' } });
    fireEvent.keyDown(screen.getByLabelText('Your answer'), { key: 'Enter' });
    await screen.findByText('Why was water important?');
    const history = screen.getByLabelText('Lesson conversation');
    const box = screen.getByRole('region', { name: 'Current lesson action' });
    expect(within(history).getByText('Teacher: Why did the travelers stop?')).toBeTruthy();
    expect(within(history).getByText('They stopped for water.')).toBeTruthy();
    expect(within(history).queryByText('Why was water important?')).toBeNull();
    expect(within(box).getByText('Why was water important?')).toBeTruthy();
    expect(within(box).getByText('Think about their long journey.')).toBeTruthy();
    expect(within(box).getByLabelText('Your answer').value).toBe('');
  });
  it('keeps the earlier scroll position when a teacher reply arrives and offers a return to latest', async () => {
    show();
    await screen.findByLabelText('Your answer');
    const conversation = screen.getByLabelText('Lesson conversation');
    Object.defineProperties(conversation, { scrollHeight: { configurable: true, value: 1200 }, clientHeight: { configurable: true, value: 300 } });
    conversation.scrollTop = 0;
    fireEvent.scroll(conversation);
    api.event.mockResolvedValue(makeState(makeActivity({ messages: [{ id: 'hint', role: 'teacher', text: 'Notice the river.' }] }), { revision: 2 }));
    fireEvent.click(screen.getByRole('button', { name: 'Give me a hint' }));
    await screen.findByText('Notice the river.');
    expect(conversation.scrollTop).toBe(0);
    fireEvent.click(screen.getByRole('button', { name: /Back to latest/ }));
    expect(conversation.scrollTop).toBe(1200);
  });

  it('edits a labeled mistake example and saves correction separately from reasoning', async () => {
    api.state.mockResolvedValue(makeState(makeActivity({ kind: 'find_and_fix_mistake', content: {
      prompt: 'Correct the sum.', example: '2 + 2 = 5', response_modes: ['text'], require_reasoning: true,
    } })));
    api.event.mockResolvedValue(makeState(makeActivity({ status: 'answered' }), { revision: 2 }));
    show();
    fireEvent.click(await screen.findByRole('button', { name: 'Edit the example' }));
    expect(screen.getByText('This example deliberately contains a mistake. Find it and explain your correction.')).toBeTruthy();
    const correction = screen.getByLabelText('Your corrected example');
    expect(correction.value).toBe('2 + 2 = 5');
    fireEvent.change(correction, { target: { value: '2 + 2 = 4' } });
    expect(screen.getByRole('button', { name: 'Check my answer' }).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText('Explain your thinking'), { target: { value: 'Two pairs make four.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Check my answer' }));
    await waitFor(() => expect(api.event).toHaveBeenCalled());
    expect(api.event.mock.calls[0][1].payload).toMatchObject({ text: '2 + 2 = 4', reasoning: 'Two pairs make four.' });
  });

  it('keeps completed support in the reference history of its originating activity', async () => {
    const active = makeActivity();
    const support = makeActivity({ id: 'support', parent_activity_id: active.id, kind: 'explain_or_observe', status: 'answered', content: { text: 'Look at how the groups joined.' } });
    api.state.mockResolvedValue(makeState(active, { activities: [active, support] }));
    show();
    const current = await screen.findByLabelText('Earlier exchanges in this activity');
    expect(within(current).getByText('Look at how the groups joined.')).toBeTruthy();
    expect(screen.getByLabelText('Lesson conversation').contains(current)).toBe(true);
    expect(screen.getAllByText('Look at how the groups joined.')).toHaveLength(1);
  });

  it('draws fractional number lines at the specified scale and tick interval', () => {
    const { container } = render(<ActivityCard activity={makeActivity({ kind: 'visual_demonstration', content: { visual: {
      type: 'number_line', minimum: 0, maximum: 0.5, step: 0.1, caption: 'Fractions', points: [{ value: 0.5, label: 'One half' }],
    } } })} readOnly />);
    expect(container.querySelector('circle').getAttribute('cx')).toBe('565');
    expect(screen.getByText('0.1', { selector: 'text' })).toBeTruthy();
    expect(screen.getByRole('img').getAttribute('aria-label')).toContain('One half: 0.5');
    expect(container.querySelectorAll('svg g line')).toHaveLength(6);
  });

  it('saves and checks a typed answer in one durable command, then waits for Continue', async () => {
    const base = makeActivity();
    const response = { id: 'r1', interaction_id: 'i1', method: 'typed', original: { text: 'They needed water.' }, status: 'assessed' };
    api.event.mockResolvedValueOnce(makeState({ ...base, status: 'answered', responses: [response], interaction: { ...base.interaction, status: 'completed' }, messages: [{ id: 'm1', role: 'teacher', text: 'That matches the source.' }] }, { revision: 3 }))
      .mockResolvedValueOnce(makeState(null, { revision: 4, activities: [] }));
    const continued = vi.fn(); show({ onContinue: continued });
    fireEvent.change(await screen.findByLabelText('Your answer'), { target: { value: 'They needed water.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Check my answer' }));
    expect(await screen.findByText('That matches the source.')).toBeTruthy();
    expect(continued).not.toHaveBeenCalled();
    expect(api.event.mock.calls[0][1]).toMatchObject({ type: 'submit_response', activity_id: 'a1', interaction_id: 'i1', expected_revision: 1, payload: { method: 'typed', text: 'They needed water.', assess_after_save: true } });
    fireEvent.click(screen.getByRole('button', { name: 'Continue lesson' }));
    await waitFor(() => expect(continued).toHaveBeenCalledTimes(1));
  });

  it('requires dictation confirmation before an assessment action is available', async () => {
    const base = makeActivity();
    api.state.mockResolvedValue(makeState({ ...base, interaction: { ...base.interaction, status: 'awaiting_confirmation' }, responses: [{ id: 'spoken', interaction_id: 'i1', method: 'dictation', original: { text: 'The trees united.' }, status: 'awaiting_confirmation' }] }));
    api.event.mockResolvedValue(makeState({ ...base, interaction: { ...base.interaction, status: 'ready_to_assess' }, responses: [{ id: 'spoken', interaction_id: 'i1', method: 'dictation', confirmed_text: 'The tribes united.', status: 'confirmed' }] }, { revision: 2 }));
    show();
    fireEvent.change(await screen.findByLabelText('Confirmed answer'), { target: { value: 'The tribes united.' } });
    expect(screen.queryByRole('button', { name: 'Check my answer' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Confirm and check my answer' }));
    expect(await screen.findByRole('button', { name: 'Check my answer' })).toBeTruthy();
    expect(api.event.mock.calls[0][1]).toMatchObject({ type: 'confirm_response', payload: { response_id: 'spoken', text: 'The tribes united.', assess_after_confirm: true } });
  });

  it('waits for physical-book completion before capturing the answer', async () => {
    const book = makeActivity({ kind: 'request_book_work', content: { prompt: 'Write the sum in your book.', book_name: 'Arithmetic', printed_page: '14', exercise_reference: '3', response_modes: ['text'] }, interaction: { id: 'i1', status: 'awaiting_work', stage: 'initial' } });
    api.state.mockResolvedValue(makeState(book));
    api.event.mockResolvedValue(makeState({ ...book, interaction: { id: 'i1', status: 'awaiting_input', stage: 'capture' } }, { revision: 2 }));
    show();
    expect(await screen.findByText('Arithmetic')).toBeTruthy();
    expect(screen.queryByLabelText('Your answer')).toBeNull();
    const done = screen.getByRole('button', { name: 'I have finished writing in my book' });
    await waitFor(() => expect(document.activeElement).toBe(done));
    expect(fireEvent.keyDown(done, { key: 'Enter', repeat: true })).toBe(false);
    expect(api.event).not.toHaveBeenCalled();
    fireEvent.click(done);
    const answer = await screen.findByLabelText('Your answer');
    await waitFor(() => expect(document.activeElement).toBe(answer));
    expect(api.event.mock.calls[0][1].type).toBe('physical_complete');
    expect(api.event).toHaveBeenCalledTimes(1);
  });

  it('restores an unfinished transcript correction without confirming or assessing it', async () => {
    const response = { id: 'spoken-draft', interaction_id: 'i1', method: 'dictation', original: { text: 'The trees united.' }, status: 'awaiting_confirmation' };
    api.state.mockResolvedValue(makeState(makeActivity({ interaction: { id: 'i1', status: 'awaiting_confirmation' }, responses: [response] })));
    const first = show();
    fireEvent.change(await screen.findByLabelText('Confirmed answer'), { target: { value: 'The tribes united.' } });
    first.unmount(); show();
    expect((await screen.findByLabelText('Confirmed answer')).value).toBe('The tribes united.');
    expect(api.event).not.toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: 'Check my answer' })).toBeNull();
    expect(screen.getByText('The trees united.')).toBeTruthy();
  });

  it('retains operation identity after an ambiguous transport failure and retries the exact command', async () => {
    api.event.mockRejectedValueOnce(new Error('Network unavailable')).mockResolvedValueOnce(makeState(makeActivity({ status: 'answered' }), { revision: 2 }));
    show();
    fireEvent.change(await screen.findByLabelText('Your answer'), { target: { value: 'My preserved answer' } });
    fireEvent.click(screen.getByRole('button', { name: 'Check my answer' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Recover saved action' }));
    await waitFor(() => expect(api.event).toHaveBeenCalledTimes(2));
    expect(api.event.mock.calls[1][1]).toEqual(api.event.mock.calls[0][1]);
    expect(api.event.mock.calls[0][1].payload.response_id).toBeTruthy();
  });

  it('checks operation receipts on reload instead of duplicating an accepted answer', async () => {
    api.event.mockImplementationOnce(async (session, command) => {
      api.state.mockResolvedValue(makeState(makeActivity({ status: 'answered' }), { revision: 2, events: [{ operation_id: command.operation_id }] }));
      throw new Error('The response was lost');
    });
    show();
    fireEvent.change(await screen.findByLabelText('Your answer'), { target: { value: 'Already committed' } });
    fireEvent.click(screen.getByRole('button', { name: 'Check my answer' }));
    await screen.findByRole('button', { name: 'Continue lesson' });
    expect(screen.queryByRole('button', { name: 'Recover saved action' })).toBeNull();
    expect(api.event).toHaveBeenCalledTimes(1);
  });

  it('keeps a prediction hidden until the independent prediction and reason are saved', async () => {
    const prediction = makeActivity({ kind: 'predict_then_check', content: { prompt: 'What happens next?', reflection_prompt: 'What changed?', reveal: { text: 'The bridge falls.' }, response_modes: ['text'] } });
    api.state.mockResolvedValue(makeState(prediction));
    api.event.mockResolvedValueOnce(makeState({ ...prediction, interaction: { id: 'i1', status: 'awaiting_reveal', stage: 'initial' }, responses: [{ id: 'r1', interaction_id: 'i1', status: 'confirmed', original: { text: 'They cross.', reasoning: 'The road reaches the bridge.' } }] }, { revision: 2 }))
      .mockResolvedValueOnce(makeState({ ...prediction, interaction: { id: 'i2', status: 'awaiting_input', stage: 'reflection', prompt: 'What changed?' }, stage: 'reflection' }, { revision: 3 }));
    show();
    expect(await screen.findByText('What happens next?')).toBeTruthy();
    expect(screen.queryByText('The bridge falls.')).toBeNull();
    fireEvent.change(screen.getByLabelText('Your answer'), { target: { value: 'They cross.' } });
    expect(screen.getByRole('button', { name: 'Save answer' }).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText('Explain your thinking'), { target: { value: 'The road reaches the bridge.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save answer' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Check my prediction' }));
    expect(await screen.findByText('The bridge falls.')).toBeTruthy();
    expect(screen.getByText('What changed?')).toBeTruthy();
    expect(screen.getByLabelText('Your answer')).toBeTruthy();
  });

  it('reveals modeled example steps in order before offering practice', async () => {
    const example = makeActivity({ kind: 'worked_example', content: { text: 'Add two groups.', steps: [{ text: 'First make two groups.' }, { text: 'Then count all objects.' }], practice_prompt: 'Now try three groups.', response_modes: ['text'], evidence_requirement: 'reasoning' }, interaction: { id: 'i1', status: 'ready_to_continue', stage: 'example:0' } });
    api.state.mockResolvedValue(makeState(example));
    api.event.mockResolvedValueOnce(makeState({ ...example, interaction: { id: 'i2', status: 'ready_to_continue', stage: 'example:1' } }, { revision: 2 }))
      .mockResolvedValueOnce(makeState({ ...example, interaction: { id: 'i3', status: 'awaiting_input', stage: 'practice' } }, { revision: 3 }));
    show();
    expect(await screen.findByText('First make two groups.')).toBeTruthy();
    expect(screen.queryByText('Then count all objects.')).toBeNull();
    expect(screen.queryByLabelText('Your answer')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Show next example step' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Try it yourself' }));
    expect(await screen.findByText('Now try three groups.')).toBeTruthy();
    expect(screen.getByLabelText('Your answer')).toBeTruthy();
  });

  it('saves a break, restores its pending interaction and displays a return orientation', async () => {
    api.event.mockResolvedValueOnce(makeState(makeActivity(), { revision: 2, on_break: true }))
      .mockResolvedValueOnce(makeState(makeActivity(), { revision: 3, orientation: 'Return to the travelers question.' }));
    const paused = vi.fn(); const continued = vi.fn(); show({ onPauseNarration: paused, onContinue: continued });
    fireEvent.click(await screen.findByRole('button', { name: 'Take a break' }));
    expect(await screen.findByRole('region', { name: 'Lesson break' })).toBeTruthy();
    expect(screen.queryByLabelText('Your answer')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Return to lesson' }));
    expect(await screen.findByText('Return to the travelers question.')).toBeTruthy();
    expect(screen.getByLabelText('Your answer')).toBeTruthy();
    expect(paused).toHaveBeenCalled(); expect(continued).not.toHaveBeenCalled();
  });

  it('routes uncertain written work to parent review without a wrong mark', async () => {
    const response = { id: 'photo', interaction_id: 'i1', method: 'photo', original: { text: 'Unclear writing' }, status: 'parent_review', evidence_ids: ['e1'] };
    api.state.mockResolvedValue(makeState(makeActivity({ interaction: { id: 'i1', status: 'parent_review' }, responses: [response] })));
    api.event.mockResolvedValue(makeState(makeActivity({ status: 'answered' }), { revision: 2 }));
    show();
    expect(await screen.findByText(/It is not marked wrong/)).toBeTruthy();
    fireEvent.click(screen.getByText('Inspect the original work together'));
    fireEvent.change(screen.getByLabelText('What you checked'), { target: { value: 'Checked the original workbook page.' } });
    fireEvent.change(screen.getByLabelText('Parent assessment'), { target: { value: 'Correct' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save parent review' }));
    await waitFor(() => expect(api.event).toHaveBeenCalled());
    expect(api.event.mock.calls[0][1]).toMatchObject({ type: 'parent_review', payload: { response_id: 'photo', result: 'Correct', note: 'Checked the original workbook page.' } });
  });

  it('lets a source disagreement continue directly, with review optional and no grade requested', async () => {
    const response = { id: 'source-answer', interaction_id: 'i1', method: 'choice',
      original: { text: 'Book wording' }, status: 'parent_review', source_disputed: true };
    api.state.mockResolvedValue(makeState(makeActivity({ interaction: { id: 'i1', status: 'parent_review' }, responses: [response] })));
    api.event.mockResolvedValue(makeState(makeActivity({ id: 'next', interaction: { id: 'i2', status: 'awaiting_input' } }), { revision: 2 }));
    const continued = vi.fn(); show({ onContinue: continued });
    const button = await screen.findByRole('button', { name: 'Continue lesson', exact: true });
    expect(button.disabled).toBe(false);
    expect(screen.getByText('Review this answer together (optional)')).toBeTruthy();
    expect(screen.queryByText(/This work needs a parent/)).toBeNull();
    fireEvent.click(button);
    await waitFor(() => expect(api.event).toHaveBeenCalledTimes(1));
    expect(api.event.mock.calls[0][1]).toMatchObject({ type: 'acknowledge_source_issue',
      activity_id: 'a1', interaction_id: 'i1', payload: { response_id: 'source-answer' } });
    await waitFor(() => expect(continued).toHaveBeenCalledTimes(1));
    expect(api.event.mock.calls[0][1].payload.result).toBeUndefined();
  });

  it('saves acknowledgement of the return orientation before dismissing it', async () => {
    api.state.mockResolvedValue(makeState(makeActivity(), { orientation: 'Return to your saved question.' }));
    api.event.mockResolvedValue(makeState(makeActivity(), { revision: 2 }));
    show();
    fireEvent.click(await screen.findByRole('button', { name: 'Continue with this activity' }));
    await waitFor(() => expect(api.event).toHaveBeenCalled());
    expect(api.event.mock.calls[0][1].type).toBe('acknowledge_return');
    await waitFor(() => expect(screen.queryByText('Return to your saved question.')).toBeNull());
  });

  it('does not grant desktop tutor access until a parent explicitly enables it', async () => {
    api.access.mockResolvedValue({ enabled: true }); show();
    await screen.findByText('Why did the travelers stop?');
    fireEvent.click(screen.getByText('Lesson options'));
    const toggle = await screen.findByRole('checkbox', { name: /Allow desktop tutor/ });
    expect(toggle.checked).toBe(false); expect(api.access).not.toHaveBeenCalled();
    fireEvent.click(toggle); await waitFor(() => expect(api.access).toHaveBeenCalledWith('s1', true));
  });
  it('closes the top options with Escape and returns focus without granting tutor access', async () => {
    show();
    await screen.findByText('Why did the travelers stop?');
    const trigger = screen.getByLabelText('Lesson options');
    fireEvent.click(trigger);
    expect(trigger.closest('details').open).toBe(true);
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(trigger.closest('details').open).toBe(false);
    expect(document.activeElement).toBe(trigger);
    expect(api.access).not.toHaveBeenCalled();
  });
});

describe('Allowlisted visual and rich cards', () => {
  it('opens the full saved thread including initial prompts, follow-ups and legacy learner messages', async () => {
    const completed = makeActivity({ status: 'answered', content: { prompt: 'Original prompt' },
      interaction: { id: 'i2', prompt: 'Follow-up prompt' }, interactions: [{ id: 'i1', sequence: 1, prompt: 'Original prompt' }, { id: 'i2', sequence: 2, prompt: 'Follow-up prompt' }],
      responses: [{ id: 'r1', message_id: 'linked', interaction_id: 'i1', original: { text: 'First words' }, status: 'assessed', support_snapshot: { dialogue_sequence: 0 } }, { id: 'r2', interaction_id: 'i2', original: { text: 'Later words' }, status: 'assessed', support_snapshot: { dialogue_sequence: 3 } }],
      messages: [{ id: 'linked', role: 'student', sequence: 1, text: 'First words' }, { id: 'reply', role: 'teacher', sequence: 2, text: 'Here is a hint.' }, { id: 'legacy', role: 'student', sequence: 3, text: 'My earlier question' }] });
    api.state.mockResolvedValue(makeState(null, { status: 'completed', activities: [completed] }));
    show();
    fireEvent.click(await screen.findByRole('button', { name: 'Collapse lesson thread' }));
    fireEvent.click(screen.getByRole('button', { name: 'Show full lesson thread' }));
    expect(screen.getByText('Original prompt')).toBeTruthy();
    expect(screen.getByText('Teacher: Follow-up prompt')).toBeTruthy();
    expect(screen.getByText('My earlier question')).toBeTruthy();
    expect(screen.getAllByText('First words')).toHaveLength(1);
    expect(screen.getAllByText('Answer checked')).toHaveLength(2);
  });

  it('shows device-only draft storage when the home server has not accepted it', async () => {
    api.event.mockResolvedValue(null);
    show();
    fireEvent.change(await screen.findByLabelText('Your answer'), { target: { value: 'Preserved locally' } });
    expect(screen.getByText('Draft saved on this device')).toBeTruthy();
    await new Promise((resolve) => setTimeout(resolve, 750));
    expect(screen.queryByText('Draft saved to your home server')).toBeNull();
  });

  it('keeps the latest feedback visible and focuses the follow-up answer', async () => {
    api.state.mockResolvedValue(makeState(makeActivity({ interaction: { id: 'follow-up', status: 'awaiting_followup', prompt: 'What changed?' },
      responses: [{ id: 'first', status: 'assessed', original: { text: 'First answer' } }], messages: [{ id: 'hint', role: 'teacher', text: 'Think about joining groups.' }] })));
    show();
    const answer = await screen.findByLabelText('Your answer');
    expect(document.activeElement).toBe(answer);
    expect(within(screen.getByRole('article', { name: 'Latest teacher reply' })).getByText('Think about joining groups.')).toBeTruthy();
    expect(screen.getAllByText('Think about joining groups.')).toHaveLength(1);
  });

  it('only labels a draft as server-saved after receiving its draft revision', async () => {
    api.event.mockResolvedValue(makeState(makeActivity({ draft_revision: 1 })));
    show();
    fireEvent.change(await screen.findByLabelText('Your answer'), { target: { value: 'Server draft' } });
    expect(await screen.findByText('Draft saved to your home server')).toBeTruthy();
    api.event.mockResolvedValue(null);
    fireEvent.change(screen.getByLabelText('Your answer'), { target: { value: 'Newer local draft' } });
    expect(screen.getByText('Draft saved on this device')).toBeTruthy();
    expect(screen.queryByText('Draft saved to your home server')).toBeNull();
  });

  it('uses the configured introduction class and renders text without executing markup', () => {
    const { container } = render(<ActivityCard activity={makeActivity({ kind: 'introduce', content: { text: '<script>neverRun()</script>' } })} />);
    expect(container.querySelector('.activity-introduction')).toBeTruthy(); expect(container.querySelector('script')).toBeNull();
  });
  it('renders number lines, timelines and diagrams with accessible alternatives', () => {
    const { rerender } = render(<ActivityCard activity={makeActivity({ kind: 'visual_demonstration', content: { visual: { type: 'number_line', minimum: 0, maximum: 5, points: [{ value: 2, label: 'Two' }], caption: 'Counting to five' } } })} />);
    expect(screen.getByRole('img', { name: /Counting to five.*Number line from 0 to 5/ })).toBeTruthy();
    rerender(<ActivityCard activity={makeActivity({ kind: 'visual_demonstration', content: { visual: { type: 'timeline', events: [{ date: '1200', label: 'A journey' }], caption: 'Travel timeline' } } })} />);
    expect(within(screen.getByRole('list', { name: 'Travel timeline' })).getByText('A journey')).toBeTruthy();
    rerender(<ActivityCard activity={makeActivity({ kind: 'visual_demonstration', content: { visual: { type: 'diagram', nodes: [{ id: 'a', label: 'River' }, { id: 'b', label: 'Town' }], edges: [{ from_id: 'a', to_id: 'b', label: 'supplies' }], caption: 'A river supplies a town' } } })} />);
    expect(screen.getByRole('img', { name: 'A river supplies a town' })).toBeTruthy();
  });
  it('shows comparison items and clearly labels deliberate mistake puzzles', () => {
    const { rerender } = render(<ActivityCard activity={makeActivity({ kind: 'compare_and_connect', content: { prompt: 'Compare these.', items: [{ id: 'a', title: 'River town', text: 'Ships arrive.' }, { id: 'b', title: 'Hill town', text: 'Carts arrive.' }] } })} />);
    expect(screen.getByText('River town')).toBeTruthy(); expect(screen.getByText('Hill town')).toBeTruthy();
    rerender(<ActivityCard activity={makeActivity({ kind: 'find_and_fix_mistake', content: { prompt: 'Fix it.', puzzle_label: 'Find the mistake puzzle', example: '2 + 3 = 6' } })} />);
    expect(screen.getByText('Find the mistake puzzle')).toBeTruthy(); expect(screen.getByText(/deliberately contains a mistake/)).toBeTruthy();
  });
});
