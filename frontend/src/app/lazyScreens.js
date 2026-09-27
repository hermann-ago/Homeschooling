import { lazy } from 'react';

// The lesson (PDF pages, handwriting, read-along) and the style guide load only when opened, so Today
// and the other screens start quickly on tablets.
export const Lesson = lazy(() => import('../screens/Lesson.jsx'));
export const StyleGuide = lazy(() => import('../screens/StyleGuide.jsx'));
