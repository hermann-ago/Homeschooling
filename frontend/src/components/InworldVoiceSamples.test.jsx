/* @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import InworldVoiceSamples from './InworldVoiceSamples';

afterEach(cleanup);

it('offers language and gender groups with free preview controls and explicit choices', () => {
  const choose = vi.fn();
  const packet = { groups: [
    { language: 'en-US', gender: 'male', voices: [{ id: 'Brian', name: 'Brian', description: 'Clear American voice.', preview_url: '/api/ai/inworld/voices/Brian/preview' }] },
    { language: 'en-US', gender: 'female', voices: [{ id: 'Ashley', name: 'Ashley', preview_url: '/api/ai/inworld/voices/Ashley/preview' }] },
    { language: 'pt-BR', gender: 'male', voices: [{ id: 'Davi', name: 'Davi', preview_url: '/api/ai/inworld/voices/Davi/preview' }] },
    { language: 'pt-BR', gender: 'female', voices: [{ id: 'Bruna', name: 'Bruna', preview_url: '/api/ai/inworld/voices/Bruna/preview' }] },
  ] };
  render(<InworldVoiceSamples packet={packet} english="Brian" portuguese="Bruna" onChoose={choose} />);
  expect(screen.getByText(/Inworld does not publish popularity rankings/)).toBeTruthy();
  expect(screen.getByLabelText('Preview Brian').preload).toBe('none');
  fireEvent.click(screen.getByText('American English · Female · 1 voices'));
  fireEvent.click(screen.getByRole('button', { name: 'Use Ashley for English' }));
  expect(choose).toHaveBeenCalledWith('en-US', 'Ashley');
  fireEvent.click(screen.getByText('Brazilian Portuguese · Male · 1 voices'));
  fireEvent.click(screen.getByRole('button', { name: 'Use Davi for Portuguese' }));
  expect(choose).toHaveBeenCalledWith('pt-BR', 'Davi');
});
