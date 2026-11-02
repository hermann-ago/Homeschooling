/* @vitest-environment jsdom */
import React from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';


const viewerMocks = vi.hoisted(() => ({
  getDocument: vi.fn(),
  getDocumentData: vi.fn(),
  pageRender: vi.fn(),
  resize: null,
  print: vi.fn(),
}));

vi.mock('../utils/printLessonPages', () => ({ printLessonPages: viewerMocks.print }));

vi.mock('react-pdf', () => ({
  Document: ({ children }) => <div data-testid="pdf-document">{children}</div>,
  Page: (props) => {
    viewerMocks.pageRender(props);
    return <div data-testid="pdf-page" style={{ width: props.width, height: 600 }} />;
  },
  pdfjs: { GlobalWorkerOptions: {} },
}));

vi.mock('../api/documents', () => ({
  getDocument: viewerMocks.getDocument,
  getDocumentData: viewerMocks.getDocumentData,
}));

vi.mock('./pdfAnnotations/usePageAnnotations', () => ({
  usePageAnnotations: () => ({
    strokes: [],
    loading: false,
    saveStatus: 'saved',
    error: '',
    conflict: null,
    canUndo: false,
    canRedo: false,
    addStroke: vi.fn(),
    eraseStrokes: vi.fn(),
    clear: vi.fn(),
    undo: vi.fn(),
    redo: vi.fn(),
    retry: vi.fn(),
    flush: vi.fn().mockResolvedValue(true),
    reloadConflict: vi.fn(),
    keepMine: vi.fn(),
  }),
}));

vi.mock('./pdfAnnotations/AnnotationLayer', () => ({ default: () => null }));
vi.mock('./pdfAnnotations/AnnotationToolbar', () => ({ default: () => null }));

import PageViewer from './PageViewer';
import { FeedbackProvider } from '../ui/feedback';


describe('PageViewer sizing', () => {
  afterEach(cleanup);
  beforeEach(() => {
    viewerMocks.pageRender.mockClear();
    viewerMocks.getDocument.mockReset().mockResolvedValue({
      id: 9,
      
      size_bytes: 100,
      page_count: 300,
    });
    viewerMocks.getDocumentData.mockReset().mockResolvedValue(new Uint8Array([1, 2, 3]));
    viewerMocks.resize = null;
    viewerMocks.print.mockReset().mockResolvedValue(undefined);
    HTMLElement.prototype.scrollTo = vi.fn();

    Object.defineProperty(HTMLElement.prototype, 'clientWidth', {
      configurable: true,
      get: () => 524,
    });
    globalThis.requestAnimationFrame = (callback) => {
      callback();
      return 1;
    };
    globalThis.cancelAnimationFrame = vi.fn();
    globalThis.ResizeObserver = class ResizeObserver {
      constructor(callback) {
        viewerMocks.resize = callback;
      }

      observe() {}

      disconnect() {}
    };
  });

  it('keeps a stable page width when resize notifications repeat', async () => {
    render(<FeedbackProvider><PageViewer
      childId={2}
      slot={{
        document_id: 9,
        page_from: 257,
        page_to: 259,
        pdf_page_offset: 21,
        subject_name: 'Language Arts',
        topic_title: 'Spelling Practice',
      }}
    /></FeedbackProvider>);

    await waitFor(() => expect(screen.getByTestId('pdf-page')).toBeTruthy());
    expect(screen.getByTestId('pdf-page').style.width).toBe('500px');
    expect(screen.getByTestId('pdf-page-viewport').style.scrollbarGutter).toBe('stable');

    viewerMocks.pageRender.mockClear();
    act(() => {
      viewerMocks.resize();
      viewerMocks.resize();
      viewerMocks.resize();
    });

    expect(viewerMocks.pageRender).not.toHaveBeenCalled();
  });

  it('fits a portrait page to available height without changing its proportions, and allows width fitting', async () => {
    Object.defineProperty(HTMLElement.prototype, 'clientHeight', { configurable: true, get: () => 800 });
    render(<FeedbackProvider><PageViewer slot={{ document_id: 9, page_from: 1, page_to: 2 }} /></FeedbackProvider>);
    await screen.findByTestId('pdf-page');
    act(() => viewerMocks.pageRender.mock.calls.at(-1)[0].onLoadSuccess({ getViewport: () => ({ width: 600, height: 1000 }) }));
    expect(screen.getByTestId('pdf-page').style.width).toBe('466px');
    fireEvent.click(screen.getByRole('button', { name: 'Fit width' }));
    expect(screen.getByTestId('pdf-page').style.width).toBe('500px');
    expect(screen.getByRole('button', { name: 'Fit width' }).getAttribute('aria-pressed')).toBe('true');
  });

  it('prints the assigned range with its PDF offset, regardless of the currently viewed page', async () => {
    render(<FeedbackProvider><PageViewer slot={{ document_id: 9, page_from: 10, page_to: 12, pdf_page_offset: 4, topic_title: 'Letter practice' }} /></FeedbackProvider>);
    await screen.findByTestId('pdf-page');
    fireEvent.click(screen.getByRole('button', { name: 'Next assigned page' }));
    await screen.findByText('Book page 11');
    fireEvent.click(screen.getByRole('button', { name: 'Print lesson pages' }));
    expect(await screen.findByRole('dialog', { name: 'Print lesson pages' })).toBeTruthy();
    expect(viewerMocks.print).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('Book pages'), { target: { value: '10,12' } });
    fireEvent.change(screen.getByLabelText('Pages per sheet'), { target: { value: '2' } });
    fireEvent.click(screen.getByRole('button', { name: 'Open print dialog' }));
    await waitFor(() => expect(viewerMocks.print).toHaveBeenCalledTimes(1));
    expect(viewerMocks.print.mock.calls[0][0]).toMatchObject({ first: 14, last: 16, offset: 4, selection: '10,12', pagesPerSheet: 2, title: 'Letter practice · book pages 10–12' });
  });

  it('keeps printing unavailable when the book could not be loaded', async () => {
    viewerMocks.getDocumentData.mockRejectedValue(new Error('The PDF is unavailable'));
    render(<FeedbackProvider><PageViewer slot={{ document_id: 9, page_from: 1, page_to: 2 }} /></FeedbackProvider>);
    await screen.findByText('The PDF is unavailable');
    expect(screen.getByRole('button', { name: 'Print lesson pages' }).disabled).toBe(true);
    expect(viewerMocks.print).not.toHaveBeenCalled();
  });

  it('retains the selected range and multi-page layout when reopening for the back pass', async () => {
    viewerMocks.print.mockImplementation(async ({ onReady }) => onReady());
    const slot = { document_id: 9, page_from: 10, page_to: 15, pdf_page_offset: 4 };
    const view = render(<FeedbackProvider><PageViewer slot={slot} /></FeedbackProvider>);
    await screen.findByTestId('pdf-page');
    fireEvent.click(screen.getByRole('button', { name: 'Print lesson pages' }));
    fireEvent.change(screen.getByLabelText('Book pages'), { target: { value: '10–14' } });
    fireEvent.change(screen.getByLabelText('Pages per sheet'), { target: { value: '2' } });
    fireEvent.change(screen.getByLabelText('Sides to print'), { target: { value: 'odd' } });
    fireEvent.click(screen.getByRole('button', { name: 'Open print dialog' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    fireEvent.click(screen.getByRole('button', { name: 'Print lesson pages' }));
    expect(screen.getByLabelText('Book pages').value).toBe('10–14');
    expect(screen.getByLabelText('Pages per sheet').value).toBe('2');
    fireEvent.change(screen.getByLabelText('Sides to print'), { target: { value: 'even' } });
    expect(screen.getByText('Back of sheet 1: 12, 13')).toBeTruthy();
    expect(screen.getByText('Back of sheet 2: blank, blank')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Open print dialog' }));
    await waitFor(() => expect(viewerMocks.print).toHaveBeenCalledTimes(2));
    expect(viewerMocks.print.mock.calls[1][0]).toMatchObject({ selection: '10–14', pagesPerSheet: 2, parity: 'even' });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    view.rerender(<FeedbackProvider><PageViewer slot={{ ...slot, page_from: 20, page_to: 21 }} /></FeedbackProvider>);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Print lesson pages' }).disabled).toBe(false));
    fireEvent.click(screen.getByRole('button', { name: 'Print lesson pages' }));
    expect(screen.getByLabelText('Book pages').value).toBe('20–21');
    expect(screen.getByLabelText('Sides to print').value).toBe('all');
  });
});
