import React, { useEffect, useRef, useState } from 'react';
import {
  drawAnnotationCanvas,
  findHitStrokeIds,
  normalizePointer,
  simplifyPoints,
} from './annotationGeometry';


function newStroke(color, width, point) {
  const randomId = globalThis.crypto?.randomUUID?.()
    || `stroke-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return { id: randomId, color, width, points: [point] };
}


const AnnotationLayer = ({
  surfaceRef,
  strokes,
  tool,
  color,
  strokeWidth,
  disabled,
  onAddStroke,
  onEraseStrokes,
}) => {
  const canvasRef = useRef(null);
  const activePointerRef = useRef(null);
  const draftStrokeRef = useRef(null);
  const erasedIdsRef = useRef(new Set());
  const [draftStroke, setDraftStroke] = useState(null);
  const [erasedIds, setErasedIds] = useState(new Set());
  const [surfaceSize, setSurfaceSize] = useState({ width: 0, height: 0 });

  useEffect(() => {
    const surface = surfaceRef.current;
    if (!surface) return undefined;
    const measure = () => {
      const rect = surface.getBoundingClientRect();
      setSurfaceSize({ width: rect.width, height: rect.height });
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(surface);
    return () => observer.disconnect();
  }, [surfaceRef]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !surfaceSize.width || !surfaceSize.height) return;
    const visibleStrokes = strokes.filter((stroke) => !erasedIds.has(stroke.id));
    if (draftStroke) visibleStrokes.push(draftStroke);
    drawAnnotationCanvas(canvas, visibleStrokes, surfaceSize.width, surfaceSize.height);
  }, [draftStroke, erasedIds, strokes, surfaceSize]);

  useEffect(() => {
    activePointerRef.current = null;
    draftStrokeRef.current = null;
    erasedIdsRef.current = new Set();
    setDraftStroke(null);
    setErasedIds(new Set());
  }, [tool]);

  const pointFromEvent = (event) => normalizePointer(
    event.currentTarget.getBoundingClientRect(),
    event.clientX,
    event.clientY,
  );

  const eraseAt = (point) => {
    const hits = findHitStrokeIds(strokes, point);
    if (!hits.length) return;
    const next = new Set(erasedIdsRef.current);
    hits.forEach((id) => next.add(id));
    erasedIdsRef.current = next;
    setErasedIds(next);
  };

  const handlePointerDown = (event) => {
    if (disabled || tool === 'hand' || !event.isPrimary) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    activePointerRef.current = event.pointerId;
    const point = pointFromEvent(event);
    if (tool === 'pen') {
      const stroke = newStroke(color, strokeWidth, point);
      draftStrokeRef.current = stroke;
      setDraftStroke(stroke);
    } else if (tool === 'eraser') {
      erasedIdsRef.current = new Set();
      setErasedIds(new Set());
      eraseAt(point);
    }
  };

  const handlePointerMove = (event) => {
    if (activePointerRef.current !== event.pointerId) return;
    event.preventDefault();
    const point = pointFromEvent(event);
    if (tool === 'pen' && draftStrokeRef.current) {
      const previous = draftStrokeRef.current.points.at(-1);
      if (Math.hypot(point[0] - previous[0], point[1] - previous[1]) < 0.0008) return;
      const stroke = {
        ...draftStrokeRef.current,
        points: [...draftStrokeRef.current.points, point],
      };
      draftStrokeRef.current = stroke;
      setDraftStroke(stroke);
    } else if (tool === 'eraser') {
      eraseAt(point);
    }
  };

  const finishPointer = (event) => {
    if (activePointerRef.current !== event.pointerId) return;
    event.preventDefault();
    if (tool === 'pen' && draftStrokeRef.current) {
      onAddStroke({
        ...draftStrokeRef.current,
        points: simplifyPoints(draftStrokeRef.current.points),
      });
    } else if (tool === 'eraser' && erasedIdsRef.current.size) {
      onEraseStrokes([...erasedIdsRef.current]);
    }
    activePointerRef.current = null;
    draftStrokeRef.current = null;
    erasedIdsRef.current = new Set();
    setDraftStroke(null);
    setErasedIds(new Set());
  };

  return (
    <canvas
      ref={canvasRef}
      aria-label="PDF annotation drawing surface"
      className="absolute inset-0 z-20"
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={finishPointer}
      onPointerCancel={finishPointer}
      style={{
        cursor: tool === 'pen' ? 'crosshair' : tool === 'eraser' ? 'cell' : 'default',
        pointerEvents: tool === 'hand' || disabled ? 'none' : 'auto',
        touchAction: tool === 'hand' ? 'auto' : 'none',
      }}
    />
  );
};


export default AnnotationLayer;
