/* @vitest-environment jsdom */
import React, { useState } from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { Button, CheckButton, LearnerSwitcher, LessonRow, useConfirm, useToast } from './index';
import { FeedbackProvider } from './feedback';

afterEach(cleanup);

describe('CheckButton', () => {
  it('names the lesson and reports the new state', () => {
    const onToggle = vi.fn();
    const { rerender } = render(<CheckButton label="History" onToggle={onToggle} />);
    fireEvent.click(screen.getByRole('button', { name: 'Mark History done' }));
    expect(onToggle).toHaveBeenCalledWith(true);

    rerender(<CheckButton label="History" done onToggle={onToggle} />);
    const button = screen.getByRole('button', { name: /History: done/ });
    expect(button.getAttribute('aria-pressed')).toBe('true');
    fireEvent.click(button);
    expect(onToggle).toHaveBeenLastCalledWith(false);
  });
});

describe('LearnerSwitcher', () => {
  it('offers Everyone plus each learner and marks the choice', () => {
    function Harness() {
      const [value, setValue] = useState('all');
      return <LearnerSwitcher learners={[{ id: 1, name: 'Lucas', color: '#4A90D9' }]} value={value} onChange={setValue} />;
    }
    render(<Harness />);
    expect(screen.getByRole('button', { name: 'Everyone' }).getAttribute('aria-pressed')).toBe('true');
    fireEvent.click(screen.getByRole('button', { name: 'Lucas' }));
    expect(screen.getByRole('button', { name: 'Lucas' }).getAttribute('aria-pressed')).toBe('true');
  });
});

describe('LessonRow', () => {
  const lesson = { id: 7, subject_name: 'Portuguese', topic_title: 'Dígrafo RR', time_start: '10:00', time_end: '11:00', page_from: 277, page_to: 277 };

  it('shows time and a single page, and hides Open once done', () => {
    const { rerender } = render(<LessonRow lesson={lesson} learnerColor="#4A90D9" onOpen={() => {}} />);
    expect(screen.getByText('10:00–11:00 · p. 277')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Open' })).toBeTruthy();
    rerender(<LessonRow lesson={{ ...lesson, is_completed: true }} learnerColor="#4A90D9" onOpen={() => {}} />);
    expect(screen.queryByRole('button', { name: 'Open' })).toBeNull();
  });
});

describe('feedback', () => {
  function Harness({ onAnswer }) {
    const confirm = useConfirm();
    const toast = useToast();
    return (
      <>
        <Button onClick={async () => onAnswer(await confirm({ title: 'Delete History?', confirmLabel: 'Delete' }))}>Ask</Button>
        <Button onClick={() => toast('Book linked.')}>Tell</Button>
      </>
    );
  }

  it('resolves confirm with the button the parent pressed', async () => {
    const onAnswer = vi.fn();
    render(<FeedbackProvider><Harness onAnswer={onAnswer} /></FeedbackProvider>);
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }));
    expect(await screen.findByText('Delete History?')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));
    await waitFor(() => expect(onAnswer).toHaveBeenCalledWith(true));

    fireEvent.click(screen.getByRole('button', { name: 'Ask' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Cancel' }));
    await waitFor(() => expect(onAnswer).toHaveBeenLastCalledWith(false));
  });

  it('shows a toast message', async () => {
    render(<FeedbackProvider><Harness onAnswer={() => {}} /></FeedbackProvider>);
    fireEvent.click(screen.getByRole('button', { name: 'Tell' }));
    expect(await screen.findByText('Book linked.')).toBeTruthy();
  });
});
