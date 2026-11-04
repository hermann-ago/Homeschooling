/* @vitest-environment jsdom */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import VideoLesson from './VideoLesson';

const video = { provider: 'vimeo', title: 'Lesson 18', embed_url: 'https://player.vimeo.com/video/1?h=a&dnt=1', open_url: 'https://vimeo.com/1/a' };
afterEach(cleanup);

function player() {
  const frame = screen.getByTitle('Lesson 18');
  const sent = [];
  Object.defineProperty(frame, 'contentWindow', { value: { postMessage: (data) => sent.push(JSON.parse(data)) } });
  const say = (event) => act(() => { window.dispatchEvent(new MessageEvent('message', { origin: 'https://player.vimeo.com', source: frame.contentWindow, data: JSON.stringify({ event }) })); });
  return { sent, say };
}

it('plays from the publisher player, with Space to pause and resume, and reports the end', () => {
  const watched = vi.fn();
  render(<VideoLesson video={video} onWatched={watched} />);
  expect(screen.getByRole('link', { name: 'Open the video in a new tab' }).href).toBe('https://vimeo.com/1/a');
  const { sent, say } = player();
  say('ready');
  expect(sent.at(-1)).toEqual({ method: 'play' });
  say('play');
  fireEvent.keyDown(document.body, { key: ' ' });
  expect(sent.at(-1)).toEqual({ method: 'pause' });
  say('pause');
  fireEvent.keyDown(document.body, { key: ' ' });
  expect(sent.at(-1)).toEqual({ method: 'play' });
  say('finish');
  say('ended');
  expect(watched).toHaveBeenCalledTimes(1);
  expect(screen.getByText(/Video finished/)).toBeTruthy();
  const count = sent.length;
  fireEvent.keyDown(document.body, { key: ' ' });
  expect(sent.length).toBe(count); // Space now belongs to Continue
});

it('ignores messages from other pages', () => {
  const watched = vi.fn();
  render(<VideoLesson video={video} onWatched={watched} />);
  act(() => { window.dispatchEvent(new MessageEvent('message', { origin: 'https://example.com', data: JSON.stringify({ event: 'ended' }) })); });
  expect(watched).not.toHaveBeenCalled();
});

it('shows only a link in the saved lesson thread', () => {
  render(<VideoLesson video={video} readOnly />);
  expect(screen.queryByTitle('Lesson 18')).toBeNull();
  expect(screen.getByRole('link')).toBeTruthy();
});
