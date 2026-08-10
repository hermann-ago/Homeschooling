import { describe, expect, it } from 'vitest';
import {
  annotationHistoryReducer,
  createAnnotationHistory,
  findHitStrokeIds,
  normalizePointer,
  simplifyPoints,
  toPhysicalPage,
} from './annotationGeometry';


describe('PDF annotation geometry', () => {
  it('normalizes mouse and touch coordinates independently of rendered size', () => {
    const small = normalizePointer({ left: 10, top: 20, width: 200, height: 400 }, 110, 220);
    const large = normalizePointer({ left: 10, top: 20, width: 800, height: 1600 }, 410, 820);
    expect(small).toEqual([0.5, 0.5]);
    expect(large).toEqual([0.5, 0.5]);
  });

  it('clamps pointer positions to the page', () => {
    expect(normalizePointer({ left: 0, top: 0, width: 100, height: 100 }, -20, 130)).toEqual([0, 1]);
  });

  it('simplifies dense pointer samples while preserving endpoints', () => {
    const points = [[0, 0], [0.0001, 0.0001], [0.2, 0.2], [0.2001, 0.2001], [1, 1]];
    expect(simplifyPoints(points)).toEqual([[0, 0], [0.2, 0.2], [1, 1]]);
  });

  it('finds the complete stroke touched by the eraser', () => {
    const strokes = [
      { id: 'blue', color: '#0000FF', width: 0.005, points: [[0.1, 0.1], [0.9, 0.9]] },
      { id: 'red', color: '#FF0000', width: 0.005, points: [[0.1, 0.9], [0.3, 0.9]] },
    ];
    expect(findHitStrokeIds(strokes, [0.5, 0.5])).toEqual(['blue']);
  });

  it('supports undo and redo without changing persisted stroke shapes', () => {
    const first = [{ id: 'one', points: [[0, 0]], color: '#111111', width: 0.005 }];
    const second = [...first, { id: 'two', points: [[1, 1]], color: '#111111', width: 0.005 }];
    let history = annotationHistoryReducer(createAnnotationHistory(first), { type: 'commit', strokes: second });
    history = annotationHistoryReducer(history, { type: 'undo' });
    expect(history.present).toEqual(first);
    history = annotationHistoryReducer(history, { type: 'redo' });
    expect(history.present).toEqual(second);
  });

  it('maps assigned book pages to physical PDF pages using the configured offset', () => {
    expect(toPhysicalPage(42, 7)).toBe(49);
    expect(toPhysicalPage(42, 0)).toBe(42);
  });
});
