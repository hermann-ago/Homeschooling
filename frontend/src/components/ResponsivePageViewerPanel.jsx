import React, { useEffect, useRef, useState } from 'react';
import clsx from 'clsx';
import PageViewer from './PageViewer';


const PANEL_WIDTH_KEY = 'homeschool:pdf-panel-width:v1';
const MIN_PANEL_WIDTH = 380;
const MIN_CONTENT_WIDTH = 360;
const MAX_PANEL_WIDTH = 1200;


function clampPanelWidth(width) {
  const viewportMaximum = Math.max(MIN_PANEL_WIDTH, window.innerWidth - MIN_CONTENT_WIDTH);
  return Math.round(Math.min(MAX_PANEL_WIDTH, viewportMaximum, Math.max(MIN_PANEL_WIDTH, width)));
}


function defaultPanelWidth() {
  return clampPanelWidth(Math.min(720, window.innerWidth * 0.46));
}


function readPanelWidth() {
  try {
    const savedWidth = Number.parseInt(localStorage.getItem(PANEL_WIDTH_KEY), 10);
    if (Number.isFinite(savedWidth)) return clampPanelWidth(savedWidth);
  } catch {
    // Fall back to the responsive default when storage is unavailable.
  }
  return defaultPanelWidth();
}


function savePanelWidth(width) {
  try {
    localStorage.setItem(PANEL_WIDTH_KEY, String(width));
  } catch {
    // Resizing still works for the current session when storage is unavailable.
  }
}


const ResponsivePageViewerPanel = ({ slot, childId, onClose }) => {
  const [panelWidth, setPanelWidth] = useState(readPanelWidth);
  const dragRef = useRef(null);

  useEffect(() => {
    const handleResize = () => setPanelWidth((width) => clampPanelWidth(width));
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const resizeTo = (width) => {
    const nextWidth = clampPanelWidth(width);
    setPanelWidth(nextWidth);
    return nextWidth;
  };

  const handlePointerDown = (event) => {
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    dragRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startWidth: panelWidth,
    };
  };

  const handlePointerMove = (event) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    drag.currentWidth = resizeTo(drag.startWidth + drag.startX - event.clientX);
  };

  const finishResize = (event) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    dragRef.current = null;
    savePanelWidth(drag.currentWidth ?? panelWidth);
  };

  const handleKeyDown = (event) => {
    if (!['ArrowLeft', 'ArrowRight', 'Home'].includes(event.key)) return;
    event.preventDefault();
    const nextWidth = event.key === 'Home'
      ? defaultPanelWidth()
      : resizeTo(panelWidth + (event.key === 'ArrowLeft' ? 32 : -32));
    if (event.key === 'Home') setPanelWidth(nextWidth);
    savePanelWidth(nextWidth);
  };

  const maximumWidth = Math.min(MAX_PANEL_WIDTH, Math.max(MIN_PANEL_WIDTH, window.innerWidth - MIN_CONTENT_WIDTH));

  return (
    <aside
      aria-label="PDF lesson workspace"
      data-testid="pdf-viewer-panel"
      className="fixed inset-0 z-50 w-full bg-surface h-full min-w-0 lg:relative lg:inset-auto lg:z-40 lg:w-[var(--pdf-panel-width)] lg:min-w-[380px] lg:border-l lg:border-border lg:shadow-[-4px_0_15px_-3px_rgba(0,0,0,0.05)] lg:flex-shrink-0"
      style={{ '--pdf-panel-width': `${panelWidth}px` }}
    >
      <div
        role="separator"
        aria-label="Resize PDF workspace"
        aria-orientation="vertical"
        aria-valuemin={MIN_PANEL_WIDTH}
        aria-valuemax={maximumWidth}
        aria-valuenow={panelWidth}
        tabIndex={0}
        title="Drag to resize PDF workspace"
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={finishResize}
        onPointerCancel={finishResize}
        onKeyDown={handleKeyDown}
        onDoubleClick={() => {
          const nextWidth = defaultPanelWidth();
          setPanelWidth(nextWidth);
          savePanelWidth(nextWidth);
        }}
        className={clsx(
          'group absolute inset-y-0 left-0 z-50 hidden w-3 -translate-x-1/2 cursor-col-resize touch-none items-center justify-center outline-none lg:flex',
          'focus-visible:bg-accent/10',
        )}
      >
        <span className="h-16 w-1 rounded-full bg-border shadow-sm transition group-hover:bg-accent group-focus-visible:bg-accent" />
      </div>
      <PageViewer slot={slot} childId={childId} onClose={onClose} />
    </aside>
  );
};


export default ResponsivePageViewerPanel;
