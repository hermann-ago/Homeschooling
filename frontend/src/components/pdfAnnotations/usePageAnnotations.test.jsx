/* @vitest-environment jsdom */
import React from 'react';
import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';


const annotationMocks = vi.hoisted(() => ({
  getPageAnnotations: vi.fn(),
  savePageAnnotations: vi.fn(),
}));

vi.mock('../../api/annotations', () => {
  class AnnotationConflictError extends Error {
    constructor(message, current) {
      super(message);
      this.current = current;
    }
  }
  return {
    AnnotationConflictError,
    getPageAnnotations: annotationMocks.getPageAnnotations,
    savePageAnnotations: annotationMocks.savePageAnnotations,
  };
});

import { AnnotationConflictError } from '../../api/annotations';
import { usePageAnnotations } from './usePageAnnotations';


const emptyPage = {
  child_id: 1,
  document_id: 2,
  page_number: 3,
  strokes: [],
  revision: 0,
  updated_at: null,
};

const stroke = {
  id: '123e4567-e89b-12d3-a456-426614174000',
  color: '#111827',
  width: 0.005,
  points: [[0.1, 0.2], [0.3, 0.4]],
};


describe('usePageAnnotations', () => {
  beforeEach(() => {
    localStorage.clear();
    annotationMocks.getPageAnnotations.mockReset().mockResolvedValue(emptyPage);
    annotationMocks.savePageAnnotations.mockReset();
  });

  it('autosaves committed strokes and clears the local draft', async () => {
    annotationMocks.savePageAnnotations.mockResolvedValue({ ...emptyPage, strokes: [stroke], revision: 1 });
    const { result } = renderHook(() => usePageAnnotations({
      childId: 1, documentId: 2, pageNumber: 3, enabled: true,
    }));
    await waitFor(() => expect(result.current.saveStatus).toBe('saved'));

    act(() => result.current.addStroke(stroke));
    expect(result.current.saveStatus).toBe('unsaved');
    await act(async () => result.current.flush());

    expect(annotationMocks.savePageAnnotations).toHaveBeenCalledWith(1, 2, 3, 0, [stroke]);
    expect(result.current.saveStatus).toBe('saved');
    expect(localStorage.length).toBe(0);
  });

  it('keeps a draft after a failed save and succeeds on retry', async () => {
    annotationMocks.savePageAnnotations.mockRejectedValueOnce(new Error('Network unavailable'));
    const { result } = renderHook(() => usePageAnnotations({
      childId: 1, documentId: 2, pageNumber: 3, enabled: true,
    }));
    await waitFor(() => expect(result.current.saveStatus).toBe('saved'));
    act(() => result.current.addStroke(stroke));
    await act(async () => result.current.flush());
    expect(result.current.saveStatus).toBe('error');
    expect(localStorage.length).toBe(1);

    annotationMocks.savePageAnnotations.mockResolvedValueOnce({ ...emptyPage, strokes: [stroke], revision: 1 });
    await act(async () => result.current.retry());
    expect(result.current.saveStatus).toBe('saved');
    expect(localStorage.length).toBe(0);
  });

  it('preserves local work when the server reports a revision conflict', async () => {
    const current = { ...emptyPage, revision: 4, strokes: [] };
    annotationMocks.savePageAnnotations.mockRejectedValueOnce(
      new AnnotationConflictError('Changed elsewhere', current),
    );
    const { result } = renderHook(() => usePageAnnotations({
      childId: 1, documentId: 2, pageNumber: 3, enabled: true,
    }));
    await waitFor(() => expect(result.current.saveStatus).toBe('saved'));
    act(() => result.current.addStroke(stroke));
    await act(async () => result.current.flush());

    expect(result.current.saveStatus).toBe('conflict');
    expect(result.current.conflict.revision).toBe(4);
    expect(result.current.strokes).toEqual([stroke]);
    expect(localStorage.length).toBe(1);
  });
});
