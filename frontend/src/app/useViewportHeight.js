import { useEffect } from 'react';

/** Follow browser chrome and the on-screen keyboard, while leaving pinch zoom alone. */
export default function useViewportHeight() {
  useEffect(() => {
    const viewport = window.visualViewport;
    if (!viewport) return undefined;
    let width = viewport.width;
    let fullHeight = Math.max(viewport.height, window.innerHeight);
    const update = () => {
      if (viewport.scale !== 1) return;
      if (viewport.width !== width) { width = viewport.width; fullHeight = viewport.height; }
      fullHeight = Math.max(fullHeight, viewport.height);
      const root = document.documentElement;
      root.style.setProperty('--app-height', `${Math.round(viewport.height)}px`);
      const editing = document.activeElement?.matches('textarea, input:not([type="radio"]):not([type="checkbox"]), [contenteditable="true"]');
      root.dataset.keyboardOpen = String(Boolean(editing && viewport.height < fullHeight * .78));
    };
    update();
    viewport.addEventListener('resize', update);
    document.addEventListener('focusin', update);
    document.addEventListener('focusout', update);
    return () => {
      viewport.removeEventListener('resize', update);
      document.removeEventListener('focusin', update);
      document.removeEventListener('focusout', update);
      document.documentElement.style.removeProperty('--app-height');
      delete document.documentElement.dataset.keyboardOpen;
    };
  }, []);
}
