import { useRef, useState } from 'react';
import { useNavigate } from 'react-router';
import { useQueryClient } from '@tanstack/react-query';
import { addDays, format, isToday, parseISO } from 'date-fns';
import { BookOpen, CheckCheck, ChevronDown, ChevronRight, FolderOpen, Plus, Printer, Star, Trash2, Upload } from 'lucide-react';
import clsx from 'clsx';
import ScreenHeader from '../app/ScreenHeader';
import { useLearner } from '../app/learnerContext';
import useReplanAction from '../app/useReplanAction';
import { subjectsApi } from '../api/subjects';
import { keys, refreshPlan, useChildProgress, useSlots, useSubjects, useTopics } from '../api/queries';
import DriveBookPicker from '../components/DriveBookPicker';
import {
  Badge, Button, CheckButton, Dialog, Field, IconButton, ProgressBar, SegmentedControl, useConfirm, useToast,
} from '../ui';
import { learnerTones } from '../utils/colors';
import { isoDay, lessonPath } from '../utils/lessons';

const PRINTED = 'Printed book';
// The planner numbers the study days: A subjects get the 1st, 3rd, 5th…, B the 2nd, 4th, 6th…
const DAYS = {
  A: { label: 'Every other day · 1st', short: '1st days', hint: 'Planned on the 1st, 3rd, 5th… study day, taking turns with “2nd” subjects.' },
  B: { label: 'Every other day · 2nd', short: '2nd days', hint: 'Planned on the 2nd, 4th, 6th… study day, taking turns with “1st” subjects.' },
  C: { label: 'Every study day', short: 'Every day', hint: 'Planned on every day with study time.' },
};
const PACES = [
  { value: 0.5, label: 'Slower' }, { value: 1, label: 'Normal' }, { value: 1.5, label: 'Faster' }, { value: 2, label: 'Twice as fast' },
];
const paceLabel = (weight) => PACES.find((p) => p.value === weight)?.label.concat(' pace') ?? `${weight}× pace`;
const clean = (error) => (error?.message || String(error)).replace(/^\/[^:]+: /, '');
const bookOf = (topic) => topic.pdf_filename || PRINTED;
const bookTitle = (name) => name.replace(/\.pdf$/i, '');

/** Shared "do it, refresh, tell the parent" wrapper for curriculum changes. */
function useChange(subjectId, childId) {
  const client = useQueryClient();
  const toast = useToast();
  return async (action, success) => {
    try {
      const result = await action();
      await Promise.all([
        client.invalidateQueries({ queryKey: keys.topics(subjectId) }),
        client.invalidateQueries({ queryKey: keys.subjects(childId) }),
        refreshPlan(client),
      ]);
      if (success) toast(success);
      return result ?? true;
    } catch (error) {
      toast({ tone: 'problem', message: clean(error) });
      return null;
    }
  };
}

/* ── Dialogs ───────────────────────────────────────────────────────────── */

function AddSubjectDialog({ child, onClose, onAdded }) {
  const [name, setName] = useState('');
  const [saving, setSaving] = useState(false);
  const client = useQueryClient();
  const toast = useToast();
  const save = async () => {
    setSaving(true);
    try {
      const subject = await subjectsApi.create({ name: name.trim(), weight: 1, child_id: child.id });
      await client.invalidateQueries({ queryKey: keys.subjects(child.id) });
      await client.invalidateQueries({ queryKey: ['progress'] });
      onAdded(subject);
    } catch (error) {
      toast({ tone: 'problem', message: `Could not add the subject: ${clean(error)}` });
      setSaving(false);
    }
  };
  return (
    <Dialog open onClose={onClose} title={`Add a subject for ${child.name}`}
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" disabled={!name.trim() || saving} onClick={save}>Add subject</Button></>}>
      <Field label="Name" autoFocus placeholder="e.g. Math, Science, Português" value={name}
        onChange={(e) => setName(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && name.trim() && save()} />
    </Dialog>
  );
}

function EditSubjectDialog({ subject, child, onClose, onDeleted }) {
  const [form, setForm] = useState({
    name: subject.name, weight: subject.weight ?? 1, slot_type: subject.slot_type || 'A', end_date: subject.end_date || '',
  });
  const change = useChange(subject.id, child.id);
  const confirm = useConfirm();
  const replan = useReplanAction();
  const set = (changes) => setForm((current) => ({ ...current, ...changes }));
  const scheduleChanged = form.weight !== subject.weight || form.slot_type !== subject.slot_type
    || (form.end_date || null) !== (subject.end_date || null);

  const save = async () => {
    const ok = await change(() => subjectsApi.update(subject.id, { ...form, name: form.name.trim(), end_date: form.end_date || null }), 'Subject saved.');
    if (!ok) return;
    onClose();
    if (scheduleChanged) replan.run([child]);
  };
  const remove = async () => {
    const ok = await confirm({
      title: `Delete ${subject.name}?`,
      description: 'Its books, chapters and planned lessons are removed. Tutoring records that refer to it stop the delete.',
      confirmLabel: 'Delete subject', danger: true,
    });
    if (ok && await change(() => subjectsApi.deleteSubject(subject.id), `${subject.name} deleted.`)) onDeleted();
  };

  return (
    <Dialog open onClose={onClose} title="Edit subject" width={520}
      footer={<>
        <Button variant="danger" icon={Trash2} onClick={remove} className="mr-auto">Delete subject</Button>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="primary" disabled={!form.name.trim()} onClick={save}>Save</Button>
      </>}>
      <div className="flex flex-col gap-5">
        <Field label="Name" value={form.name} onChange={(e) => set({ name: e.target.value })} />
        <div className="flex flex-col gap-1.5">
          <span className="text-[13px] font-semibold text-muted">Days</span>
          <SegmentedControl label="Days" size="sm" value={form.slot_type} onChange={(slot_type) => set({ slot_type })}
            options={Object.entries(DAYS).map(([value, d]) => ({ value, label: d.short }))} />
          <span className="text-[13px] text-subtle">{DAYS[form.slot_type].hint}</span>
        </div>
        <div className="flex flex-col gap-1.5">
          <span className="text-[13px] font-semibold text-muted">Pace</span>
          <SegmentedControl label="Pace" size="sm" value={form.weight} onChange={(weight) => set({ weight })}
            options={(PACES.some((p) => p.value === form.weight) ? PACES : [...PACES, { value: form.weight, label: `${form.weight}×` }])
              .map((p) => ({ value: p.value, label: p.label }))} />
          <span className="text-[13px] text-subtle">A faster pace gives this subject more pages in each lesson.</span>
        </div>
        <Field label="Finish by (optional)" type="date" value={form.end_date} onChange={(e) => set({ end_date: e.target.value })}
          hint="Leave empty to finish with the school year." />
        {scheduleChanged && <p className="text-[13px] text-attention">Saving asks to re-plan {child.name}, so the lessons follow these settings.</p>}
      </div>
    </Dialog>
  );
}

function AddBookDialog({ subject, child, onClose, onAdded }) {
  const [mode, setMode] = useState(null);
  const [chapters, setChapters] = useState(10);
  const [busy, setBusy] = useState('');
  const input = useRef(null);
  const change = useChange(subject.id, child.id);

  const run = async (label, action, success) => {
    setBusy(label);
    const ok = await change(action, success);
    setBusy('');
    if (ok) { onAdded(); onClose(); }
  };
  const upload = (file) => file && run('Reading the book to find its chapters… this can take a minute.',
    () => subjectsApi.uploadPdf(subject.id, file), `${file.name} added and its chapters found.`);
  const link = (book) => { setMode(null); run('Reading the book to find its chapters… this can take a minute.',
    () => subjectsApi.linkDriveBook(subject.id, book.path), `${book.name} linked and its chapters found.`); };
  const printed = () => run('Adding chapters…', () => subjectsApi.generateChapters(subject.id, chapters), `${chapters} chapters added.`);

  const Option = ({ icon: Icon, title, text, onClick }) => (
    <button type="button" onClick={onClick} disabled={Boolean(busy)}
      className="flex items-start gap-3.5 p-4 rounded-xl border border-line text-left hover:border-action hover:bg-action-soft/40 disabled:opacity-50">
      <Icon aria-hidden="true" className="w-5 h-5 mt-0.5 text-action shrink-0" />
      <span className="flex flex-col gap-0.5"><span className="text-[15px] font-semibold">{title}</span><span className="text-[13px] text-muted">{text}</span></span>
    </button>
  );

  return (
    <>
      <Dialog open={mode !== 'drive'} onClose={busy ? undefined : onClose} title={`Add a book to ${subject.name}`}
        footer={mode === 'printed'
          ? <><Button onClick={() => setMode(null)} disabled={Boolean(busy)}>Back</Button><Button variant="primary" disabled={Boolean(busy) || chapters < 1} onClick={printed}>Add chapters</Button></>
          : <Button onClick={onClose} disabled={Boolean(busy)}>Cancel</Button>}>
        {busy ? (
          <p className="py-4 text-[15px]" role="status">{busy}</p>
        ) : mode === 'printed' ? (
          <Field label="How many chapters?" type="number" min={1} max={100} value={chapters}
            onChange={(e) => setChapters(Math.max(1, Math.min(100, Number(e.target.value) || 1)))}
            hint="Numbered chapters are added so a printed book can be planned and ticked off." />
        ) : (
          <div className="flex flex-col gap-2.5">
            <Option icon={FolderOpen} title="From the Drive folder" text="A PDF already in the Homeschooling folder." onClick={() => setMode('drive')} />
            <Option icon={Upload} title="Upload a PDF" text="Copied into this subject's Books folder." onClick={() => input.current?.click()} />
            <Option icon={Printer} title="A printed book" text="No PDF: plan it by chapter numbers." onClick={() => setMode('printed')} />
            <input ref={input} type="file" accept=".pdf,application/pdf" className="hidden"
              onChange={(e) => { upload(e.target.files[0]); e.target.value = ''; }} />
          </div>
        )}
      </Dialog>
      {mode === 'drive' && <DriveBookPicker onClose={() => setMode(null)} onPick={link} />}
    </>
  );
}

function OffsetDialog({ subject, child, book, offset, onClose }) {
  const [value, setValue] = useState(offset);
  const change = useChange(subject.id, child.id);
  const save = async () => {
    if (await change(() => subjectsApi.setBookOffset(subject.id, book, value), 'Page offset saved.')) onClose();
  };
  return (
    <Dialog open onClose={onClose} title="Page offset" description={bookTitle(book)}
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" onClick={save}>Save</Button></>}>
      <Field label="Pages before page 1" type="number" value={value} onChange={(e) => setValue(Number(e.target.value) || 0)}
        hint="If the book's page 1 is the PDF's page 5, the offset is 4. Lessons then open on the right pages." />
    </Dialog>
  );
}

/* ── Subject detail ────────────────────────────────────────────────────── */

function whenLabel(topic, planned) {
  if (topic.completed) {
    return topic.completed_at
      ? { text: `Done ${format(new Date(topic.completed_at), 'd MMM')}`, tone: 'done' }
      : { text: 'Done', tone: 'done' };
  }
  const info = planned.get(topic.id);
  if (!info) return { text: 'Not planned', tone: 'none' };
  if (info.missed) return { text: `Unfinished · ${format(parseISO(info.missed), 'd MMM')}`, tone: 'late' };
  const day = parseISO(info.next);
  return { text: isToday(day) ? 'Today' : format(day, 'EEE d MMM'), tone: isToday(day) ? 'today' : 'next' };
}

function ChapterRow({ topic, when, tones, onToggle, onOpen, onEarlier, onDelete }) {
  return (
    <div className="flex flex-wrap md:flex-nowrap items-center gap-x-4 gap-y-1 px-5 py-3 border-b border-line-soft last:border-b-0">
      <CheckButton size={32} done={topic.completed} current={when.tone === 'today'} color={tones.strong}
        label={topic.title} onToggle={onToggle} />
      <span className={clsx('flex-1 min-w-[12rem] text-[15px] font-semibold', topic.completed && 'text-subtle line-through')}>{topic.title}</span>
      <span className="w-24 text-sm text-muted">
        {topic.page_start === topic.page_end ? `p. ${topic.page_start}` : `${topic.page_start}–${topic.page_end}`}
      </span>
      <span className="w-40">
        {when.tone === 'late' ? <Badge tone="attention">{when.text}</Badge>
          : when.tone === 'today' ? <Badge color={tones.strong} background={tones.soft}>{when.text}</Badge>
            : when.tone === 'done' ? <span className="text-sm text-action font-semibold">{when.text}</span>
              : <span className="text-sm text-muted">{when.text}</span>}
      </span>
      <span className="flex gap-1 ml-auto">
        {onOpen && <IconButton icon={BookOpen} size="sm" label={`Open ${topic.title}`} onClick={onOpen} />}
        {!topic.completed && <IconButton icon={CheckCheck} size="sm" variant="quiet" label={`Mark ${topic.title} and every chapter before it done`} onClick={onEarlier} />}
        <IconButton icon={Trash2} size="sm" variant="quiet" label={`Delete ${topic.title}`} onClick={onDelete} className="text-muted" />
      </span>
    </div>
  );
}

function SubjectDetail({ subject, child, onDeleted }) {
  const { data: topics = [], isLoading } = useTopics(subject.id);
  const { data: missed = [] } = useSlots(child.id, 'missed');
  const { data: upcoming = [] } = useSlots(child.id, { start: isoDay(new Date()), end: isoDay(addDays(new Date(), 400)) });
  const [chosenBook, setChosenBook] = useState(null);
  const [dialog, setDialog] = useState(null);
  const [showDone, setShowDone] = useState(false);
  const change = useChange(subject.id, child.id);
  const confirm = useConfirm();
  const navigate = useNavigate();
  const tones = learnerTones(child.color);

  const books = [...topics.reduce((map, t) => {
    const name = bookOf(t);
    const book = map.get(name) || { name, core: false, count: 0, offset: t.pdf_page_offset || 0, document: t.document_id };
    book.core = book.core || Boolean(t.is_core);
    book.count += 1;
    return map.set(name, book);
  }, new Map()).values()].sort((a, b) => Number(b.core) - Number(a.core));
  const book = books.find((b) => b.name === chosenBook) || books[0];
  const chapters = topics.filter((t) => book && bookOf(t) === book.name)
    .sort((a, b) => (a.chapter_order ?? 0) - (b.chapter_order ?? 0) || a.page_start - b.page_start);
  const finished = chapters.filter((t) => t.completed);
  const open = chapters.filter((t) => !t.completed);

  const planned = new Map();
  for (const slot of missed) if (!slot.is_completed && slot.topic_id) {
    const entry = planned.get(slot.topic_id) || {};
    if (!entry.missed || slot.date < entry.missed) entry.missed = slot.date;
    planned.set(slot.topic_id, entry);
  }
  for (const slot of upcoming) if (!slot.is_completed && slot.topic_id) {
    const entry = planned.get(slot.topic_id) || {};
    if (!entry.next || slot.date < entry.next) entry.next = slot.date;
    planned.set(slot.topic_id, entry);
  }

  const row = (topic) => (
    <ChapterRow key={topic.id} topic={topic} when={whenLabel(topic, planned)} tones={tones}
      onToggle={() => change(() => subjectsApi.toggleTopicComplete(subject.id, topic.id))}
      onOpen={topic.document_id ? () => navigate(lessonPath({ topic_id: topic.id }, child.id)) : null}
      onEarlier={async () => {
        if (await confirm({ title: `Mark "${topic.title}" and every chapter before it done?`, description: 'The time is recorded as now.', confirmLabel: 'Mark done' })) {
          change(() => subjectsApi.completePrevious(subject.id, topic.id), 'Chapters marked done.');
        }
      }}
      onDelete={async () => {
        if (await confirm({ title: `Delete "${topic.title}"?`, description: 'Its planned lessons are removed too.', confirmLabel: 'Delete chapter', danger: true })) {
          change(() => subjectsApi.deleteTopic(subject.id, topic.id), 'Chapter deleted.');
        }
      }} />
  );

  return (
    <section className="flex-1 min-w-0 flex flex-col gap-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex flex-col gap-2.5">
          <h1 className="font-display text-3xl md:text-4xl font-medium">{subject.name}</h1>
          <div className="flex flex-wrap gap-2">
            <Badge>{DAYS[subject.slot_type || 'A'].label}</Badge>
            <Badge>{paceLabel(subject.weight ?? 1)}</Badge>
            <Badge>{subject.end_date ? `Finish by ${format(parseISO(subject.end_date), 'd MMM yyyy')}` : 'Ends with the school year'}</Badge>
          </div>
        </div>
        <Button onClick={() => setDialog({ type: 'edit' })}>Edit subject</Button>
      </div>

      <div className="flex flex-col gap-2.5">
        {books.map((b) => (
          <div key={b.name} className={clsx('flex flex-wrap items-center gap-3.5 px-4 py-3 rounded-2xl bg-surface border',
            b.name === book?.name ? 'border-action' : 'border-line')}>
            <button type="button" onClick={() => setChosenBook(b.name)} className="flex-1 min-w-0 flex items-center gap-3.5 text-left">
              <span aria-hidden="true" className="w-8 h-10 shrink-0 rounded-[4px]" style={{ background: b.core ? tones.strong : 'var(--color-line)' }} />
              <span className="min-w-0 flex flex-col gap-0.5">
                <span className="text-[15px] font-bold truncate">{bookTitle(b.name)}</span>
                <span className="text-[13px] text-muted">
                  {b.core ? 'Main book · planned' : 'Extra book · not planned'} · {b.count} {b.count === 1 ? 'chapter' : 'chapters'}
                </span>
              </span>
            </button>
            <div className="flex gap-1">
              {!b.core && b.name !== PRINTED && (
                <IconButton icon={Star} size="sm" label={`Make ${bookTitle(b.name)} the main book`}
                  onClick={() => change(() => subjectsApi.setMainBook(subject.id, b.name), `${bookTitle(b.name)} is now the main book.`)} />
              )}
              {b.document && <Button size="sm" onClick={() => setDialog({ type: 'offset', book: b })}>Offset {b.offset}</Button>}
              {b.name !== PRINTED && (
                <IconButton icon={Trash2} size="sm" variant="quiet" className="text-muted" label={`Delete the book ${bookTitle(b.name)}`}
                  onClick={async () => {
                    if (await confirm({ title: `Delete the book "${bookTitle(b.name)}"?`, description: 'Its chapters and planned lessons are removed. The PDF stays in the Drive folder.', confirmLabel: 'Delete book', danger: true })) {
                      change(() => subjectsApi.deleteBook(subject.id, b.name), 'Book deleted.');
                    }
                  }} />
              )}
            </div>
          </div>
        ))}
        <button type="button" onClick={() => setDialog({ type: 'book' })}
          className="h-12 rounded-2xl border border-dashed border-line flex items-center justify-center gap-2 text-sm font-semibold hover:border-action">
          <Plus aria-hidden="true" className="w-[18px] h-[18px]" />
          Add a book
          <span className="font-medium text-muted">· from Drive, upload, or printed</span>
        </button>
      </div>

      <div className="bg-surface border border-line rounded-2xl overflow-hidden">
        <div className="hidden md:flex items-center gap-4 px-5 py-3 border-b border-line-soft text-xs font-bold tracking-[0.6px] uppercase text-muted">
          <span className="w-8" /><span className="flex-1">Chapter</span><span className="w-24">Pages</span><span className="w-40">When</span><span className="w-32" />
        </div>
        {isLoading && <p className="px-5 py-4 text-muted">Loading…</p>}
        {!isLoading && !chapters.length && (
          <p className="px-5 py-6 text-muted">No chapters yet. Add a book to plan {subject.name}.</p>
        )}
        {finished.length > 0 && (
          <button type="button" onClick={() => setShowDone(!showDone)}
            className="w-full flex items-center gap-2.5 px-5 py-3 border-b border-line-soft bg-paper/60 text-sm font-semibold text-muted text-left hover:text-ink">
            {showDone ? <ChevronDown aria-hidden="true" className="w-4 h-4" /> : <ChevronRight aria-hidden="true" className="w-4 h-4" />}
            {showDone ? 'Hide' : 'Show'} {finished.length} finished {finished.length === 1 ? 'chapter' : 'chapters'}
          </button>
        )}
        {showDone && finished.map(row)}
        {open.map(row)}
      </div>

      {dialog?.type === 'edit' && <EditSubjectDialog subject={subject} child={child} onClose={() => setDialog(null)} onDeleted={onDeleted} />}
      {dialog?.type === 'book' && <AddBookDialog subject={subject} child={child} onClose={() => setDialog(null)} onAdded={() => setChosenBook(null)} />}
      {dialog?.type === 'offset' && (
        <OffsetDialog subject={subject} child={child} book={dialog.book.name} offset={dialog.book.offset} onClose={() => setDialog(null)} />
      )}
    </section>
  );
}

/* ── Screen ────────────────────────────────────────────────────────────── */

export default function Curriculum() {
  const { learner, single } = useLearner();
  const child = learner(single);
  const { data: subjects = [], isLoading } = useSubjects(child?.id);
  const { data: progress } = useChildProgress(child?.id);
  const [chosen, setChosen] = useState(null);
  const [adding, setAdding] = useState(false);
  if (!child) return <><ScreenHeader everyone={false} /><p className="p-10 text-muted">Add a learner in Settings first.</p></>;

  const tones = learnerTones(child.color);
  const subject = subjects.find((s) => s.id === chosen?.id && s.child_id === child.id) || subjects[0];
  const percent = (id) => progress?.subjects.find((p) => p.subject_id === id);

  return (
    <>
      <ScreenHeader everyone={false} actions={<span className="text-sm text-muted">Curriculum is set per learner</span>} />
      <div className="flex flex-col lg:flex-row gap-6 px-4 md:px-10 py-6">
        <nav aria-label="Subjects" className="lg:w-64 shrink-0 flex flex-col gap-1.5">
          <h2 className="mb-2 text-[13px] font-bold tracking-[0.8px] uppercase text-muted">Subjects</h2>
          {isLoading && <p className="text-sm text-muted">Loading…</p>}
          {subjects.map((s) => {
            const p = percent(s.id);
            const selected = s.id === subject?.id;
            const complete = p && p.total_pages && p.progress_percent >= 100;
            return (
              <button key={s.id} type="button" aria-current={selected ? 'true' : undefined} onClick={() => setChosen(s)}
                className={clsx('flex flex-col gap-2 p-3.5 rounded-xl text-left border',
                  selected ? 'bg-surface border-line' : 'border-transparent hover:bg-surface/60')}>
                <span className="flex justify-between gap-2 text-[15px]">
                  <span className={selected ? 'font-bold' : 'font-semibold'}>{s.name}</span>
                  <span className={clsx('text-sm font-semibold', !p?.total_pages ? 'text-attention' : complete ? 'text-action' : 'text-muted')}>
                    {!p ? '' : !p.total_pages ? 'No book yet' : complete ? 'Complete' : `${Math.round(p.progress_percent)}%`}
                  </span>
                </span>
                {p?.total_pages > 0 && (
                  <ProgressBar value={p.progress_percent} height={5} color={complete ? 'var(--color-action)' : tones.strong} label={s.name} />
                )}
              </button>
            );
          })}
          <Button icon={Plus} className="mt-2 border-dashed" onClick={() => setAdding(true)}>Add subject</Button>
        </nav>
        {subject ? (
          <SubjectDetail key={subject.id} subject={subject} child={child} onDeleted={() => setChosen(null)} />
        ) : !isLoading && (
          <div className="flex-1 grid place-items-center p-10 text-center rounded-2xl border border-dashed border-line">
            <div className="flex flex-col items-center gap-3">
              <p className="font-display text-2xl">{child.name} has no subjects yet</p>
              <p className="text-muted">Add a subject, then add its book to plan lessons.</p>
              <Button variant="primary" icon={Plus} onClick={() => setAdding(true)}>Add subject</Button>
            </div>
          </div>
        )}
      </div>
      {adding && <AddSubjectDialog child={child} onClose={() => setAdding(false)} onAdded={(s) => { setAdding(false); setChosen(s); }} />}
    </>
  );
}

