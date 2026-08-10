/* @vitest-environment jsdom */
import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';


const panelMocks = vi.hoisted(() => ({ pageViewer: vi.fn() }));

vi.mock('./PageViewer', () => ({
  default: (props) => {
    panelMocks.pageViewer(props);
    return <div data-testid="page-viewer" />;
  },
}));

import ResponsivePageViewerPanel from './ResponsivePageViewerPanel';


describe('ResponsivePageViewerPanel', () => {
  afterEach(cleanup);

  beforeEach(() => {
    localStorage.clear();
    panelMocks.pageViewer.mockClear();
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1400 });
    globalThis.PointerEvent = MouseEvent;
    HTMLElement.prototype.setPointerCapture = vi.fn();
  });

  it('renders one viewer and persists keyboard resizing', () => {
    const slot = { document_id: 9 };
    render(<ResponsivePageViewerPanel slot={slot} childId={2} onClose={() => {}} />);

    expect(screen.getAllByTestId('page-viewer')).toHaveLength(1);
    const separator = screen.getByRole('separator', { name: 'Resize PDF workspace' });
    expect(separator.getAttribute('aria-valuenow')).toBe('644');

    fireEvent.keyDown(separator, { key: 'ArrowLeft' });
    expect(separator.getAttribute('aria-valuenow')).toBe('676');
    expect(localStorage.getItem('homeschool:pdf-panel-width:v1')).toBe('676');
  });

  it('supports pointer dragging from the panel edge', () => {
    render(<ResponsivePageViewerPanel slot={{ document_id: 9 }} childId={2} onClose={() => {}} />);
    const separator = screen.getByRole('separator', { name: 'Resize PDF workspace' });

    fireEvent.pointerDown(separator, { pointerId: 7, clientX: 700 });
    fireEvent.pointerMove(separator, { pointerId: 7, clientX: 600 });
    fireEvent.pointerUp(separator, { pointerId: 7, clientX: 600 });

    expect(separator.getAttribute('aria-valuenow')).toBe('744');
    expect(localStorage.getItem('homeschool:pdf-panel-width:v1')).toBe('744');
  });
});
