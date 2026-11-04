import { useEffect, useId, useRef, useState } from 'react';
import { beginNarration, registerNarrator } from '../../utils/narration';
import { focusLessonControl } from '../../utils/lessonFocus';
import { nextStepButton, useSpaceBar } from '../../utils/spaceBar';

const VIMEO = 'https://player.vimeo.com';

/**
 * The book's video lesson on the publisher's own player. Nothing is copied:
 * the video streams from where the publisher keeps it. On a Vimeo player
 * Space plays and pauses it, and when it ends Continue takes over.
 */
export default function VideoLesson({ video, readOnly = false, onWatched }) {
  const frame = useRef(null);
  const narrator = useId();
  const [status, setStatus] = useState('loading'); // loading · ready · playing · paused · ended
  const current = useRef('loading');
  const watched = useRef(onWatched);
  useEffect(() => { watched.current = onWatched; }, [onWatched]);
  const vimeo = video.provider === 'vimeo';
  const live = vimeo && !readOnly;
  const send = (method, value) => frame.current?.contentWindow?.postMessage(JSON.stringify(value === undefined ? { method } : { method, value }), VIMEO);
  const show = (next) => { current.current = next; setStatus(next); };

  useEffect(() => {
    if (!live) return undefined;
    const message = (event) => {
      if (event.origin !== VIMEO || event.source !== frame.current?.contentWindow) return;
      let data;
      try { data = typeof event.data === 'string' ? JSON.parse(event.data) : event.data; } catch { return; }
      if (data?.event === 'ready') {
        // The player's own messages call the end "finish".
        ['play', 'pause', 'finish', 'ended'].forEach((name) => send('addEventListener', name));
        show('ready');
        send('play'); // starts by itself when the browser allows sound
      } else if (data?.event === 'play') { beginNarration(narrator); show('playing'); }
      else if (data?.event === 'pause' && current.current !== 'ended') show('paused');
      else if ((data?.event === 'finish' || data?.event === 'ended') && current.current !== 'ended') {
        show('ended');
        watched.current?.();
        focusLessonControl(nextStepButton());
      }
    };
    window.addEventListener('message', message);
    return () => window.removeEventListener('message', message);
  }, [live]);
  // The tutor's voice and the video never talk over each other.
  useEffect(() => registerNarrator(narrator, () => { if (current.current === 'playing') send('pause'); }), [narrator]);
  useSpaceBar(() => {
    if (!live || ['loading', 'ended'].includes(current.current)) return false;
    send(current.current === 'playing' ? 'pause' : 'play');
    return true;
  });

  const link = <a className="text-action underline" href={video.open_url} target="_blank" rel="noreferrer">Open the video in a new tab</a>;
  if (readOnly) return <p className="text-sm">{video.title || 'Video lesson'} · {link}</p>;
  return <div className="flex flex-col gap-2" aria-label="Video lesson">
    <div className="relative w-full overflow-hidden rounded-xl bg-black" style={{ aspectRatio: '16 / 9' }}>
      <iframe ref={frame} src={video.embed_url} title={video.title || 'Video lesson'} className="absolute inset-0 h-full w-full border-0"
        allow="autoplay; fullscreen; picture-in-picture" allowFullScreen />
    </div>
    <p className="text-xs text-muted">
      {live && status === 'ended' ? 'Video finished. Press Space to continue. ' : live ? 'Space plays and pauses the video. ' : ''}{link}
    </p>
  </div>;
}
