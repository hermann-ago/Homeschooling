import { useEffect, useState } from 'react';
import { ChevronRight } from 'lucide-react';
import clsx from 'clsx';
import { canvasApi } from '../api/canvas';
import { Button, Dialog, Field } from '../ui';

/** Choose a chapter from any of the learner's books to read with a lesson. */
export default function InsertPicker({ childId, onSelect, onClose }) {
  const [subjects, setSubjects] = useState(null);
  const [expanded, setExpanded] = useState(null);
  const [search, setSearch] = useState('');

  useEffect(() => {
    canvasApi.getAvailableTopics(childId).then(setSubjects).catch(() => setSubjects([]));
  }, [childId]);

  const query = search.toLowerCase();
  const filtered = (subjects || []).map((s) => ({
    ...s,
    topics: s.topics.filter((t) => t.title.toLowerCase().includes(query) || s.subject_name.toLowerCase().includes(query)),
  })).filter((s) => s.topics.length > 0);

  return (
    <Dialog open onClose={onClose} title="Add pages from another book" width={560}
      description="Choose a chapter to read with this lesson."
      footer={<Button onClick={onClose}>Cancel</Button>}>
      <div className="flex flex-col gap-3">
        <Field label="Search" placeholder="Chapter or subject" value={search} onChange={(e) => setSearch(e.target.value)} autoFocus />
        <div className="max-h-[50vh] overflow-y-auto flex flex-col gap-1">
          {!subjects && <p className="text-sm text-muted">Loading…</p>}
          {subjects && filtered.length === 0 && <p className="text-sm text-muted">No chapters found.</p>}
          {filtered.map((subject) => {
            const open = expanded === subject.subject_id || Boolean(query);
            return (
              <div key={subject.subject_id}>
                <button type="button" aria-expanded={open}
                  onClick={() => setExpanded(expanded === subject.subject_id ? null : subject.subject_id)}
                  className="w-full flex items-center justify-between gap-2 p-3 rounded-xl hover:bg-paper text-left">
                  <span className="text-[15px] font-semibold">{subject.subject_name}</span>
                  <span className="flex items-center gap-2 text-[13px] text-muted">
                    {subject.topics.length} chapters
                    <ChevronRight aria-hidden="true" className={clsx('w-4 h-4 transition-transform', open && 'rotate-90')} />
                  </span>
                </button>
                {open && (
                  <ul className="ml-3 pl-3 border-l-2 border-line flex flex-col">
                    {subject.topics.map((topic) => (
                      <li key={topic.id}>
                        <button type="button" onClick={() => onSelect(topic)}
                          className="w-full text-left px-3 py-2 rounded-lg hover:bg-action-soft flex flex-col">
                          <span className="text-sm font-semibold">{topic.title}</span>
                          <span className="text-[13px] text-muted">
                            pp. {topic.page_start}–{topic.page_end}{topic.pdf_filename && ` · ${topic.pdf_filename.replace(/\.pdf$/i, '')}`}
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </Dialog>
  );
}
