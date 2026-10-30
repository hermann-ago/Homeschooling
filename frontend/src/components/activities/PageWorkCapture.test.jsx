/* @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import PageWorkCapture from './PageWorkCapture';

const group = status => ({ id: 'shared-page', status, evidence_ids: [], items: [
  { activity_id: 'a1', page: 5, prompt: 'Book item A', text: 'F', uncertain: false },
  { activity_id: 'a2', page: 5, prompt: 'Book item B', text: 'leao', uncertain: true },
  { activity_id: 'a3', page: 5, prompt: 'Book item C', text: '', uncertain: false },
] });
beforeEach(() => window.localStorage.clear());
afterEach(cleanup);

const exercise = {scope:'exercise',status:'ready',can_type:true,instruction:'Complete the words:',items:'ABCDEF'.split('').map((label,index)=>({activity_id:`part-${index}`,label,prompt:`Word ${label} ___`}))};

it('defaults to six typed fields and checks filled parts with one action, including Enter', async () => {
  const event=vi.fn();
  render(<PageWorkCapture group={exercise} sessionId="synthetic" draftIdentity="exercise-1.initial" onEvent={event}/>);
  expect(screen.getAllByRole('textbox')).toHaveLength(6);
  expect(screen.getByRole('button',{name:'Check answers'}).disabled).toBe(true);
  fireEvent.change(screen.getByLabelText('Answer A'),{target:{value:'leão'}});
  fireEvent.change(screen.getByLabelText('Answer F'),{target:{value:'limões'}});
  fireEvent.keyDown(screen.getByLabelText('Answer F'),{key:'Enter',shiftKey:true});
  fireEvent.keyDown(screen.getByLabelText('Answer F'),{key:'Enter',isComposing:true,keyCode:229});
  expect(event).not.toHaveBeenCalled();
  fireEvent.keyDown(screen.getByLabelText('Answer F'),{key:'Enter'});
  await waitFor(()=>expect(event).toHaveBeenCalledWith('submit_exercise_answers',{items:[{item_id:'part-0',text:'leão'},{item_id:'part-5',text:'limões'}]}));
  expect(screen.queryByRole('button',{name:'I have finished these answers'})).toBeNull();
});

it('restores typed drafts after refresh and retains them when switching to a photo', () => {
  const props={group:exercise,sessionId:'synthetic',draftIdentity:'exercise-1.initial',onEvent:vi.fn()};
  const view=render(<PageWorkCapture {...props}/>);
  fireEvent.change(screen.getByLabelText('Answer C'),{target:{value:'corações'}});
  fireEvent.change(screen.getByLabelText('How to send these answers'),{target:{value:'photo'}});
  expect(screen.getByRole('button',{name:'I have finished these answers'})).toBeTruthy();
  view.unmount();render(<PageWorkCapture {...props}/>);
  expect(screen.getByLabelText('How to send these answers').value).toBe('photo');
  fireEvent.change(screen.getByLabelText('How to send these answers'),{target:{value:'typed'}});
  expect(screen.getByLabelText('Answer C').value).toBe('corações');
});

it('keeps drafts separate for a new attempt and prevents submitting without required reasoning', () => {
  const props={group:{...exercise,items:[{...exercise.items[0],require_reasoning:true},exercise.items[1]]},sessionId:'synthetic',onEvent:vi.fn()};
  const view=render(<PageWorkCapture {...props} draftIdentity="exercise-1.old"/>);
  fireEvent.change(screen.getByLabelText('Answer A'),{target:{value:'Old answer'}});
  view.rerender(<PageWorkCapture {...props} draftIdentity="exercise-1.new"/>);
  expect(screen.getByLabelText('Answer A').value).toBe('');
  fireEvent.change(screen.getByLabelText('Answer A'),{target:{value:'A new answer'}});
  expect(screen.getByRole('button',{name:'Check answers'}).disabled).toBe(true);
  fireEvent.change(screen.getByLabelText('Explain answer A'),{target:{value:'My actual reason'}});
  expect(screen.getByRole('button',{name:'Check answers'}).disabled).toBe(false);
});

it('uploads one page photo without creating an answer or asking for another photo per question', async () => {
  const upload = vi.fn().mockResolvedValue('one-photo'); const event = vi.fn();
  render(<PageWorkCapture group={group('capture')} sessionId="synthetic" onUpload={upload} onEvent={event} />);
  expect(screen.getAllByRole('listitem')).toHaveLength(3);
  const file = new File(['fake-page'], 'page.jpg', { type: 'image/jpeg' });
  fireEvent.change(screen.getByLabelText('Photo of these answers'), { target: { files: [file] } });
  await waitFor(() => expect(screen.getByText('1 photo attached')).toBeTruthy());
  expect(event).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Read all answers in these photos' }));
  expect(upload).toHaveBeenCalledTimes(1);
  expect(event).toHaveBeenCalledWith('submit_page_work', { page_work_id: 'shared-page', evidence_ids: ['one-photo'] });
});

it('requires review of uncertain answers and keeps amendments over refresh', () => {
  const event = vi.fn(); const props = { group: group('confirmation'), sessionId: 'synthetic', onEvent: event };
  const view = render(<PageWorkCapture {...props} />);
  expect(screen.getByRole('checkbox', { name: 'Include answer 1' }).checked).toBe(true);
  expect(screen.getByRole('checkbox', { name: 'Include answer 2' }).checked).toBe(false);
  expect(screen.getByRole('checkbox', { name: 'Include answer 3' }).checked).toBe(false);
  fireEvent.change(screen.getByLabelText('Captured answer 2'), { target: { value: 'leão' } });
  fireEvent.click(screen.getByRole('checkbox', { name: 'Include answer 2' }));
  view.unmount(); render(<PageWorkCapture {...props} />);
  expect(screen.getByLabelText('Captured answer 2').value).toBe('leão');
  fireEvent.click(screen.getByRole('button', { name: 'These match my work · Check 2 answers' }));
  expect(event).toHaveBeenCalledWith('confirm_page_work', { page_work_id: 'shared-page', items: [
    { item_id: 'a1', text: 'F' }, { item_id: 'a2', text: 'leão' },
  ] });
});

it('keeps blank or unselected work out of the assessment and disables duplicate confirmation while busy', () => {
  const event = vi.fn();
  render(<PageWorkCapture group={group('confirmation')} sessionId="synthetic" onEvent={event} busy />);
  expect(screen.getByRole('button', { name: 'These match my work · Check 1 answer' }).disabled).toBe(true);
  expect(screen.getByLabelText('Captured answer 1').disabled).toBe(true);
});

it('offers recovery of a saved failed page rather than uploading again', () => {
  const event = vi.fn();
  render(<PageWorkCapture group={{ ...group('assessment_failed'), error: 'Saved request needs recovery.' }} sessionId="synthetic" onEvent={event} />);
  fireEvent.click(screen.getByRole('button', { name: 'Recover saved page request' }));
  expect(event).toHaveBeenCalledWith('retry_page_work', { page_work_id: 'shared-page' });
  expect(screen.queryByRole('button', { name: 'Take a photo of these answers' })).toBeNull();
});
