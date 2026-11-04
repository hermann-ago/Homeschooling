/* @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import ResponseCapture from './ResponseCapture';

const activity = (content = {}) => ({ id: 'question', kind: 'ask_question', interaction: { id: 'first' }, content: { response_modes: ['text', 'device_dictation'], ...content } });
beforeEach(() => window.localStorage.clear());
afterEach(cleanup);

describe('Answer keyboard submission', () => {
  it('keeps a reading selection free of mode pickers and text inputs, including after refresh', () => {
    const submit = vi.fn().mockResolvedValue(null);
    const current = activity({ response_modes: ['choice'], answer_format: 'single_choice', choices: [{ id: 'yes', label: 'Yes' }, { id: 'no', label: 'No' }] });
    const view = render(<ResponseCapture compact sessionId="book-reading" activity={current} onSubmit={submit} />);
    expect(screen.queryByRole('combobox')).toBeNull();
    expect(screen.queryByRole('textbox')).toBeNull();
    expect(screen.queryByText('Add an explanation (optional)')).toBeNull();
    fireEvent.click(screen.getByRole('radio', { name: 'Yes' }));
    view.unmount();
    render(<ResponseCapture compact sessionId="book-reading" activity={current} onSubmit={submit} />);
    expect(screen.getByRole('radio', { name: 'Yes' }).checked).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: 'Check my answer' }));
    expect(submit.mock.calls[0][0]).toMatchObject({ method: 'choice', choice_ids: ['yes'], reasoning: '', assess_after_save: true });
  });

  it('opens true/false controls first, keeps an optional explanation and restores both after refresh', () => {
    const submit = vi.fn().mockResolvedValue(null);
    const current = activity({ response_modes: ['choice', 'text'], answer_format: 'true_false', choices: [{ id: 'true', label: 'Verdadeiro' }, { id: 'false', label: 'Falso' }] });
    const view = render(<ResponseCapture compact sessionId="practice" activity={current} onSubmit={submit} />);
    expect(screen.getByLabelText('How to answer').value).toBe('choice');
    expect(screen.getByRole('button', { name: 'Check my answer' }).disabled).toBe(true);
    fireEvent.click(screen.getByRole('radio', { name: 'Falso' }));
    fireEvent.change(screen.getByLabelText('Explain your thinking (optional)'), { target: { value: 'São os chineses.' } });
    expect(submit).not.toHaveBeenCalled();
    view.unmount();
    render(<ResponseCapture compact sessionId="practice" activity={current} onSubmit={submit} />);
    expect(screen.getByRole('radio', { name: 'Falso' }).checked).toBe(true);
    expect(screen.getByLabelText('Explain your thinking (optional)').value).toBe('São os chineses.');
    fireEvent.keyDown(screen.getByLabelText('Explain your thinking (optional)'), { key: 'Enter' });
    expect(submit.mock.calls[0][0]).toMatchObject({ method: 'choice', choice_ids: ['false'], reasoning: 'São os chineses.', assess_after_save: true });
  });

  it('allows one option or several only when explicitly requested, with a typed alternative', () => {
    const submit = vi.fn().mockResolvedValue(null);
    render(<ResponseCapture sessionId="practice" activity={activity({ response_modes: ['choice', 'text'], answer_format: 'multiple_select', choices: [{ id: 'a', label: '2' }, { id: 'b', label: '3' }, { id: 'c', label: '4' }] })} onSubmit={submit} />);
    fireEvent.click(screen.getByRole('checkbox', { name: '2' }));
    fireEvent.click(screen.getByRole('checkbox', { name: '4' }));
    fireEvent.click(screen.getByRole('checkbox', { name: '2' }));
    fireEvent.click(screen.getByRole('button', { name: 'Check my answer' }));
    expect(submit.mock.calls[0][0]).toMatchObject({ method: 'choice', choice_ids: ['c'] });
    fireEvent.change(screen.getByLabelText('How to answer'), { target: { value: 'typed' } });
    expect(screen.getByLabelText('Your answer')).toBeTruthy();
  });

  it('requires the explanation only when the source asks for it', () => {
    const submit = vi.fn().mockResolvedValue(null);
    render(<ResponseCapture sessionId="practice" activity={activity({ response_modes: ['choice', 'text'], require_reasoning: true, choices: [{ id: 'a', label: 'A' }, { id: 'b', label: 'B' }] })} onSubmit={submit} />);
    fireEvent.click(screen.getByRole('radio', { name: 'A' }));
    fireEvent.click(screen.getByRole('radio', { name: 'B' }));
    expect(screen.getByRole('radio', { name: 'A' }).checked).toBe(false);
    expect(screen.getByRole('button', { name: 'Check my answer' }).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText('Explain your thinking'), { target: { value: 'My reason.' } });
    fireEvent.keyDown(screen.getByRole('radio', { name: 'B' }), { key: 'Enter' });
    expect(submit.mock.calls[0][0]).toMatchObject({ method: 'choice', choice_ids: ['b'], reasoning: 'My reason.' });
  });

  it('accepts simple letter recognition without demanding a typed explanation', () => {
    const submit = vi.fn().mockResolvedValue(null);
    render(<ResponseCapture sessionId="practice" activity={activity({ response_modes: ['choice'], choices: [{ id: 'r', label: 'r' }, { id: 'p', label: 'p' }] })} onSubmit={submit} />);
    expect(screen.queryByLabelText('Explain your thinking')).toBeNull();
    fireEvent.click(screen.getByRole('radio', { name: 'r' }));
    fireEvent.click(screen.getByRole('button', { name: 'Check my answer' }));
    expect(submit.mock.calls[0][0]).toMatchObject({ method: 'choice', choice_ids: ['r'], reasoning: '', assess_after_save: true });
  });

  it('uses the same durable response identity for Enter and a retry after an uncertain reply', async () => {
    let finish;
    const submit = vi.fn().mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; })).mockResolvedValue(null);
    render(<ResponseCapture sessionId="practice" activity={activity()} onSubmit={submit} />);
    const answer = screen.getByLabelText('Your answer');
    fireEvent.change(answer, { target: { value: 'A saved answer' } });
    fireEvent.keyDown(answer, { key: 'Enter' });
    fireEvent.keyDown(answer, { key: 'Enter', repeat: true });
    fireEvent.click(screen.getByRole('button', { name: 'Check my answer' }));
    expect(submit).toHaveBeenCalledTimes(1);
    expect(submit.mock.calls[0][0]).toMatchObject({ text: 'A saved answer', assess_after_save: true });
    await finish(null);
    await waitFor(() => expect(answer.value).toBe('A saved answer'));
    fireEvent.keyDown(answer, { key: 'Enter' });
    expect(submit).toHaveBeenCalledTimes(2);
    expect(submit.mock.calls[1][0].response_id).toBe(submit.mock.calls[0][0].response_id);
  });

  it('leaves Shift+Enter and composition alone and does not send an empty or busy answer', () => {
    const submit = vi.fn();
    const current = activity();
    const { rerender } = render(<ResponseCapture sessionId="practice" activity={current} onSubmit={submit} />);
    const answer = screen.getByLabelText('Your answer');
    fireEvent.keyDown(answer, { key: 'Enter' });
    fireEvent.change(answer, { target: { value: 'First line' } });
    expect(fireEvent.keyDown(answer, { key: 'Enter', shiftKey: true })).toBe(true);
    fireEvent.keyDown(answer, { key: 'Enter', isComposing: true });
    fireEvent.keyDown(answer, { key: 'Enter', keyCode: 229 });
    rerender(<ResponseCapture sessionId="practice" activity={current} onSubmit={submit} busy />);
    fireEvent.keyDown(answer, { key: 'Enter' });
    expect(submit).not.toHaveBeenCalled();
  });

  it('requires reasoning before Enter can send and accepts Enter in the reasoning field', () => {
    const submit = vi.fn().mockResolvedValue(null);
    render(<ResponseCapture sessionId="practice" activity={activity({ require_reasoning: true })} onSubmit={submit} />);
    const answer = screen.getByLabelText('Your answer');
    fireEvent.change(answer, { target: { value: 'Four' } });
    fireEvent.keyDown(answer, { key: 'Enter' });
    expect(submit).not.toHaveBeenCalled();
    const reasoning = screen.getByLabelText('Explain your thinking');
    fireEvent.change(reasoning, { target: { value: 'Two pairs make four.' } });
    fireEvent.keyDown(reasoning, { key: 'Enter' });
    expect(submit.mock.calls[0][0]).toMatchObject({ text: 'Four', reasoning: 'Two pairs make four.' });
  });

  it('saves dictated input for confirmation without requesting assessment', () => {
    const submit = vi.fn().mockResolvedValue(null);
    render(<ResponseCapture sessionId="practice" activity={activity()} onSubmit={submit} />);
    fireEvent.change(screen.getByLabelText('How to answer'), { target: { value: 'dictation' } });
    const transcript = screen.getByLabelText('Your spoken transcript');
    fireEvent.change(transcript, { target: { value: 'Words to check' } });
    fireEvent.keyDown(transcript, { key: 'Enter' });
    expect(submit.mock.calls[0][0]).toMatchObject({ method: 'dictation', text: 'Words to check' });
    expect(submit.mock.calls[0][0].assess_after_save).toBeUndefined();
  });
});

describe('One answer box per problem', () => {
  const boxes = [{ id: 'blank-1', label: '58 - 27 =' }, { id: 'blank-2', label: '92 - 61 =' }];
  const work = (extra = {}) => ({ id: 'practice-1', kind: 'request_book_work', interaction: { id: 'first' },
    content: { prompt: '1. Use Number Line Hopping.', response_modes: ['text', 'photo'], blanks: boxes }, ...extra });

  it('moves through the boxes with Enter and checks once every box is filled', () => {
    const submit = vi.fn().mockResolvedValue(null);
    render(<ResponseCapture sessionId="math" activity={work()} onSubmit={submit} />);
    expect(screen.queryByLabelText('How to answer')).toBeNull();
    const first = screen.getByLabelText('Answer for 58 - 27 =');
    fireEvent.change(first, { target: { value: '31' } });
    fireEvent.keyDown(first, { key: 'Enter' });
    expect(document.activeElement).toBe(screen.getByLabelText('Answer for 92 - 61 ='));
    expect(submit).not.toHaveBeenCalled();
    fireEvent.change(document.activeElement, { target: { value: '31' } });
    fireEvent.keyDown(document.activeElement, { key: 'Enter' });
    expect(submit.mock.calls[0][0]).toMatchObject({ method: 'typed', blanks: { 'blank-1': '31', 'blank-2': '31' }, assess_after_save: true });
  });

  it('starts a retry from the last answers and marks which were right', () => {
    const last = { id: 'r1', original: { blanks: { 'blank-1': '31', 'blank-2': '30' } }, blank_results: { 'blank-1': true, 'blank-2': false } };
    render(<ResponseCapture sessionId="math" activity={work({ interaction: { id: 'retry' }, responses: [last] })} onSubmit={vi.fn()} />);
    expect(screen.getByLabelText('Answer for 58 - 27 =').value).toBe('31');
    expect(screen.getByLabelText('Right')).toBeTruthy();
    expect(screen.getByLabelText('Answer for 92 - 61 =').getAttribute('aria-invalid')).toBe('true');
    expect(screen.getByText('Look again')).toBeTruthy();
  });

  it('offers a photo of the book instead of typing', () => {
    render(<ResponseCapture sessionId="math" activity={work()} onSubmit={vi.fn()} onUpload={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: 'Send a photo of my book instead' }));
    expect(screen.queryByLabelText('Answer for 58 - 27 =')).toBeNull();
    expect(screen.getByRole('button', { name: 'Take photo of my work' })).toBeTruthy();
  });
});

describe('Photo answers', () => {
  it('sends a photo as soon as it is attached, without words typed before switching', async () => {
    const submit = vi.fn().mockResolvedValue(null);
    const upload = vi.fn().mockResolvedValue('E1');
    const current = activity({ response_modes: ['text', 'photo'], blanks: [{ id: 'blank-1', label: '__umor:' }, { id: 'blank-2', label: '__orta:' }] });
    render(<ResponseCapture compact sessionId="photo" activity={current} onSubmit={submit} onUpload={upload} />);
    fireEvent.change(screen.getByLabelText('Answer for __umor:'), { target: { value: 'hu' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send a photo of my book instead' }));
    expect(screen.queryByLabelText('What you wrote (optional transcript)')).toBeNull();
    fireEvent.change(screen.getByLabelText('Photo of your work'), { target: { files: [new File(['x'], 'work.jpg', { type: 'image/jpeg' })] } });
    await waitFor(() => expect(submit).toHaveBeenCalledTimes(1));
    expect(submit.mock.calls[0][0]).toMatchObject({ method: 'photo', evidence_ids: ['E1'], text: '', blanks: {} });
  });

  it('starts another go with a photo when the last answer was a photo', () => {
    const current = { ...activity({ response_modes: ['text', 'photo'] }), responses: [{ id: 'r1', method: 'photo', original: { text: '' } }] };
    render(<ResponseCapture compact sessionId="again" activity={current} onSubmit={vi.fn()} onUpload={vi.fn()} />);
    expect(screen.getByLabelText('How to answer').value).toBe('photo');
  });
});
