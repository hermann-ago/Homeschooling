import { useState } from 'react';
import { SegmentedControl } from '../ui';

/** Small screens show one useful panel at a time; both stay mounted. */
export default function LessonWorkspace({ book, children, hasBook = true, hasTutor = true }) {
  const [selected, setSelected] = useState('tutor');
  const pane = hasTutor ? selected : 'book';
  return <div className="lesson-workspace-layout flex-1 min-h-0 flex flex-col" data-has-book={hasBook}>
    {hasBook && hasTutor && <div className="lesson-workspace-switch lg:hidden shrink-0 px-3 py-2 bg-surface border-b border-line">
      <SegmentedControl label="Lesson workspace" value={pane} onChange={setSelected} className="w-full [&>button]:flex-1 [&>button]:justify-center"
        options={[{ value: 'tutor', label: 'Tutor & activities' }, { value: 'book', label: 'Book pages' }]} />
    </div>}
    <div className="lesson-panels flex-1 min-h-0 flex flex-col lg:flex-row" data-mobile-pane={pane}>
      <section aria-label="Original book pages" className="lesson-book-panel flex-1 min-h-0 min-w-0 bg-surface">{book}</section>
      {children}
    </div>
  </div>;
}
