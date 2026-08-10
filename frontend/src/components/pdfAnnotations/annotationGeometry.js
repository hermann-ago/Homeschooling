export function clamp(value, minimum = 0, maximum = 1) {
  return Math.min(maximum, Math.max(minimum, value));
}


export function toPhysicalPage(bookPage, offset = 0) {
  return bookPage + offset;
}


export function normalizePointer(rect, clientX, clientY) {
  if (!rect.width || !rect.height) return [0, 0];
  return [
    clamp((clientX - rect.left) / rect.width),
    clamp((clientY - rect.top) / rect.height),
  ];
}


function squaredDistance(a, b) {
  const dx = a[0] - b[0];
  const dy = a[1] - b[1];
  return dx * dx + dy * dy;
}


export function simplifyPoints(points, minimumDistance = 0.0015) {
  if (points.length <= 2) return points;
  const threshold = minimumDistance * minimumDistance;
  const simplified = [points[0]];
  for (let index = 1; index < points.length - 1; index += 1) {
    if (squaredDistance(points[index], simplified[simplified.length - 1]) >= threshold) {
      simplified.push(points[index]);
    }
  }
  const last = points[points.length - 1];
  if (squaredDistance(last, simplified[simplified.length - 1]) > 0) {
    simplified.push(last);
  }
  return simplified;
}


export function pointToSegmentDistance(point, start, end) {
  const dx = end[0] - start[0];
  const dy = end[1] - start[1];
  if (dx === 0 && dy === 0) return Math.sqrt(squaredDistance(point, start));
  const projection = clamp(
    ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / (dx * dx + dy * dy),
  );
  return Math.hypot(
    point[0] - (start[0] + projection * dx),
    point[1] - (start[1] + projection * dy),
  );
}


export function findHitStrokeIds(strokes, point, eraserRadius = 0.018) {
  return strokes.filter((stroke) => {
    const hitRadius = eraserRadius + stroke.width / 2;
    if (stroke.points.length === 1) {
      return Math.sqrt(squaredDistance(point, stroke.points[0])) <= hitRadius;
    }
    for (let index = 1; index < stroke.points.length; index += 1) {
      if (pointToSegmentDistance(point, stroke.points[index - 1], stroke.points[index]) <= hitRadius) {
        return true;
      }
    }
    return false;
  }).map((stroke) => stroke.id);
}


function drawStroke(context, stroke, width, height) {
  const points = stroke.points;
  if (!points.length) return;
  const lineWidth = Math.max(1, stroke.width * width);
  context.strokeStyle = stroke.color;
  context.fillStyle = stroke.color;
  context.lineWidth = lineWidth;
  context.lineCap = 'round';
  context.lineJoin = 'round';

  if (points.length === 1) {
    context.beginPath();
    context.arc(points[0][0] * width, points[0][1] * height, lineWidth / 2, 0, Math.PI * 2);
    context.fill();
    return;
  }

  context.beginPath();
  context.moveTo(points[0][0] * width, points[0][1] * height);
  for (let index = 1; index < points.length - 1; index += 1) {
    const current = points[index];
    const next = points[index + 1];
    context.quadraticCurveTo(
      current[0] * width,
      current[1] * height,
      ((current[0] + next[0]) / 2) * width,
      ((current[1] + next[1]) / 2) * height,
    );
  }
  const last = points[points.length - 1];
  context.lineTo(last[0] * width, last[1] * height);
  context.stroke();
}


export function drawAnnotationCanvas(canvas, strokes, width, height) {
  const pixelRatio = window.devicePixelRatio || 1;
  const nextWidth = Math.max(1, Math.round(width * pixelRatio));
  const nextHeight = Math.max(1, Math.round(height * pixelRatio));
  if (canvas.width !== nextWidth || canvas.height !== nextHeight) {
    canvas.width = nextWidth;
    canvas.height = nextHeight;
  }
  canvas.style.width = `${width}px`;
  canvas.style.height = `${height}px`;
  const context = canvas.getContext('2d');
  context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
  context.clearRect(0, 0, width, height);
  strokes.forEach((stroke) => drawStroke(context, stroke, width, height));
}


export function createAnnotationHistory(strokes = []) {
  return { past: [], present: strokes, future: [] };
}


export function annotationHistoryReducer(state, action) {
  switch (action.type) {
    case 'load':
      return createAnnotationHistory(action.strokes);
    case 'commit':
      return {
        past: [...state.past, state.present],
        present: action.strokes,
        future: [],
      };
    case 'undo':
      if (!state.past.length) return state;
      return {
        past: state.past.slice(0, -1),
        present: state.past[state.past.length - 1],
        future: [state.present, ...state.future],
      };
    case 'redo':
      if (!state.future.length) return state;
      return {
        past: [...state.past, state.present],
        present: state.future[0],
        future: state.future.slice(1),
      };
    default:
      return state;
  }
}
