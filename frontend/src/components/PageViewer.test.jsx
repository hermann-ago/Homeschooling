/* @vitest-environment jsdom */
import React from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';


const viewerMocks = vi.hoisted(() => ({
  getDocument: vi.fn(),
  getDocumentData: vi.fn(),
  pageRender: vi.fn(),
  resize: null,
}));

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


describe('PageViewer sizing', () => {
  beforeEach(() => {
    viewerMocks.pageRender.mockClear();
    viewerMocks.getDocument.mockReset().mockResolvedValue({
      id: 9,
      blob_path: 'private/book.pdf',
      size_bytes: 100,
      page_count: 300,
    });
    viewerMocks.getDocumentData.mockReset().mockResolvedValue(new Uint8Array([1, 2, 3]));
    viewerMocks.resize = null;

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
    render(<PageViewer
      childId={2}
      slot={{
        document_id: 9,
        page_from: 257,
        page_to: 259,
        pdf_page_offset: 21,
        subject_name: 'Language Arts',
        topic_title: 'Spelling Practice',
      }}
      onClose={() => {}}
    />);

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
});
