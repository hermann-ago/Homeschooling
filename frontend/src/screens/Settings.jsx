import { useEffect, useState } from 'react';
import { useLocation } from 'react-router';
import { useQueryClient } from '@tanstack/react-query';
import { Plus, X } from 'lucide-react';
import clsx from 'clsx';
import { useLearner } from '../app/learnerContext';
import useReplanAction from '../app/useReplanAction';
import { childrenApi } from '../api/children';
import { subjectsApi } from '../api/subjects';
import { calendarApi } from '../api/calendar';
import { systemApi } from '../api/system';
import { timeWindowsApi } from '../api/timeWindows';
import { keys, useAutoReplan, useFamilyProgress, useNarrationUsage, useSchoolYear, useStorageStatus, useSubjects, useTimeWindows } from '../api/queries';
import { useDevice } from '../components/deviceContext';
import GradeSelect from '../components/GradeSelect';
import { Button, Dialog, Field, IconButton, SegmentedControl, inputClasses, useToast } from '../ui';
import { learnerTones } from '../utils/colors';
import { shortTime } from '../utils/lessons';
import { folderLabel, gradeLabel, sameGrade } from '../utils/grades';

const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
const COLOURS = ['#4A90D9', '#E88AB5', '#7BC67E', '#F5A623', '#8E7CC3', '#E0685C', '#3BA99C', '#6B9E8A'];
const clean = (error) => (error?.message || String(error)).replace(/^\/[^:]+: /, '');

function Section({ id, title, action, children }) {
  return (
    <section id={id} className="scroll-mt-6 bg-surface border border-line rounded-2xl p-5 md:p-6 flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-[17px] font-bold">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

/* ── Family ────────────────────────────────────────────────────────────── */

function LearnerDialog({ learner, onClose, onGradeChanged }) {
  const [form, setForm] = useState({
    name: learner?.name || '', nickname: learner?.nickname || '', grade_year: learner?.grade_year || 'N/A', color: learner?.color || COLOURS[0],
  });
  const [saving, setSaving] = useState(false);
  const client = useQueryClient();
  const toast = useToast();
  const set = (changes) => setForm((current) => ({ ...current, ...changes }));
  const save = async () => {
    setSaving(true);
    const data = { ...form, name: form.name.trim(), nickname: form.nickname.trim() || null, grade_year: form.grade_year || 'N/A' };
    try {
      if (learner) await childrenApi.update(learner.id, data);
      else await childrenApi.create(data);
      await client.invalidateQueries({ queryKey: keys.children });
      await client.invalidateQueries({ queryKey: ['progress'] });
      toast(learner ? `${data.name} saved.` : `${data.name} added.`);
      onClose();
      if (learner && !sameGrade(learner.grade_year, data.grade_year)) onGradeChanged?.({ ...learner, ...data });
    } catch (error) {
      toast({ tone: 'problem', message: `Not saved: ${clean(error)}` });
      setSaving(false);
    }
  };
  const tones = learnerTones(form.color);
  return (
    <Dialog open onClose={onClose} title={learner ? `Edit ${learner.name}` : 'Add a learner'}
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" disabled={!form.name.trim() || saving} onClick={save}>Save</Button></>}>
      <div className="flex flex-col gap-4">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Name" value={form.name} onChange={(e) => set({ name: e.target.value })} />
          <Field label="Nickname (optional)" value={form.nickname} onChange={(e) => set({ nickname: e.target.value })} />
        </div>
        <GradeSelect value={form.grade_year} onChange={(grade_year) => set({ grade_year })}
          hint="New subjects start at this grade. Each subject keeps its own grade, so a learner can be ahead in one subject and still finishing another." />
        <div className="flex flex-col gap-2">
          <span className="text-[13px] font-semibold text-muted">Colour</span>
          <div role="radiogroup" aria-label="Colour" className="flex flex-wrap items-center gap-2">
            {COLOURS.map((colour) => (
              <button key={colour} type="button" role="radio" aria-checked={form.color.toLowerCase() === colour.toLowerCase()}
                aria-label={colour} onClick={() => set({ color: colour })}
                className={clsx('w-9 h-9 rounded-full border-2', form.color.toLowerCase() === colour.toLowerCase() ? 'border-ink' : 'border-transparent')}
                style={{ background: colour }} />
            ))}
            <label className="h-9 px-3 rounded-full border border-line flex items-center gap-2 text-[13px] font-semibold cursor-pointer">
              Other
              <input type="color" value={form.color} onChange={(e) => set({ color: e.target.value })} className="w-6 h-6 border-0 p-0 bg-transparent" />
            </label>
          </div>
          <span className="text-[13px] font-semibold px-2.5 py-1 rounded-full self-start" style={{ background: tones.soft, color: tones.strong }}>
            {form.name || 'Name'} · how it looks as text
          </span>
        </div>
      </div>
    </Dialog>
  );
}

/** After a learner's grade changes: choose which subjects move up now (the rest keep their grade). */
function MoveUpDialog({ learner, onClose }) {
  const { data: subjects = [] } = useSubjects(learner.id);
  const [chosen, setChosen] = useState(() => new Set());
  const [saving, setSaving] = useState(false);
  const client = useQueryClient();
  const toast = useToast();
  const candidates = subjects.filter((s) => !sameGrade(s.grade, learner.grade_year));
  const toggle = (id) => setChosen((current) => {
    const next = new Set(current);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });
  const move = async () => {
    setSaving(true);
    try {
      for (const id of chosen) await subjectsApi.update(id, { grade: learner.grade_year });
      await client.invalidateQueries({ queryKey: keys.subjects(learner.id) });
      await client.invalidateQueries({ queryKey: ['progress'] });
      toast(`Moved ${chosen.size} ${chosen.size === 1 ? 'subject' : 'subjects'} to ${gradeLabel(learner.grade_year)}; their folders are ready in Drive.`);
      onClose();
    } catch (error) {
      toast({ tone: 'problem', message: `Not all subjects moved: ${clean(error)}` });
      setSaving(false);
    }
  };
  if (!candidates.length) return null;
  return (
    <Dialog open onClose={onClose} title={`Which of ${learner.name}'s subjects move to ${gradeLabel(learner.grade_year)} now?`}
      description="Tick the subjects that start the new grade. The others keep their grade until you move them (Curriculum › Edit subject)."
      footer={<><Button onClick={onClose}>Not now</Button>
        <Button variant="primary" disabled={!chosen.size || saving} onClick={move}>{saving ? 'Moving…' : `Move ${chosen.size || ''} to ${gradeLabel(learner.grade_year)}`}</Button></>}>
      <ul className="flex flex-col gap-2">
        {candidates.map((subject) => (
          <li key={subject.id}>
            <label className="flex items-start gap-3 p-3 rounded-xl border border-line cursor-pointer hover:bg-paper">
              <input type="checkbox" className="mt-0.5 w-5 h-5 accent-[var(--color-action)]" checked={chosen.has(subject.id)} onChange={() => toggle(subject.id)} />
              <span className="flex flex-col gap-0.5">
                <span className="text-[15px] font-semibold">{subject.name} <span className="font-normal text-muted">· now {gradeLabel(subject.grade)}</span></span>
                <span className="text-[13px] text-muted">
                  {chosen.has(subject.id) ? `New files go in ${folderLabel(learner.name, learner.grade_year, subject.name)}` : `Stays in ${(subject.folder || '').split('/').join(' › ')}`}
                </span>
              </span>
            </label>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-[13px] text-subtle">Books, audio and handwriting already saved stay where they are.</p>
    </Dialog>
  );
}

function Family() {
  const { learners } = useLearner();
  const [editing, setEditing] = useState(null);
  const [movingUp, setMovingUp] = useState(null);
  return (
    <Section id="family" title="Family" action={<Button size="sm" icon={Plus} onClick={() => setEditing('new')}>Add learner</Button>}>
      <ul className="flex flex-col divide-y divide-line-soft">
        {learners.map((child) => {
          const tones = learnerTones(child.color);
          return (
            <li key={child.id} className="flex items-center gap-3 py-2.5">
              <span className="w-9 h-9 rounded-[10px] grid place-items-center font-bold" style={{ background: tones.soft, color: tones.strong }}>
                {child.name.charAt(0)}
              </span>
              <span className="flex-1 text-[15px] font-semibold">
                {child.name}
                <span className="font-normal text-muted"> · {gradeLabel(child.grade_year)}</span>
              </span>
              <Button size="sm" variant="quiet" onClick={() => setEditing(child)}>Edit</Button>
            </li>
          );
        })}
      </ul>
      {editing && <LearnerDialog learner={editing === 'new' ? null : editing} onClose={() => setEditing(null)} onGradeChanged={setMovingUp} />}
      {movingUp && <MoveUpDialog learner={movingUp} onClose={() => setMovingUp(null)} />}
    </Section>
  );
}

/* ── School year ───────────────────────────────────────────────────────── */

function SchoolYear() {
  const { data: year } = useSchoolYear();
  const [form, setForm] = useState(null);
  const [saving, setSaving] = useState(false);
  const client = useQueryClient();
  const toast = useToast();
  const replan = useReplanAction();
  const { learners } = useLearner();
  const { data: family } = useFamilyProgress();
  const values = form || year || { start_date: '', end_date: '' };
  const changed = form && year && (form.start_date !== year.start_date || form.end_date !== year.end_date);

  const save = async () => {
    if (form.end_date <= form.start_date) {
      toast({ tone: 'problem', message: 'The school year must end after it starts.' });
      return;
    }
    setSaving(true);
    try {
      await calendarApi.updateSchoolYearSettings(form);
      await client.invalidateQueries({ queryKey: keys.schoolYear });
      await client.invalidateQueries({ queryKey: ['progress'] });
      setForm(null);
      toast('School year saved.');
      const planned = learners.filter((c) => family?.children.find((p) => p.child_id === c.id)?.subjects.length);
      replan.run(planned);
    } catch (error) {
      toast({ tone: 'problem', message: `Not saved: ${clean(error)}` });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Section id="school-year" title="School year">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
        <Field label="Starts" type="date" value={values.start_date} onChange={(e) => setForm({ ...values, start_date: e.target.value })} />
        <Field label="Ends" type="date" value={values.end_date} onChange={(e) => setForm({ ...values, end_date: e.target.value })} />
      </div>
      <AutoReplan />
      <div className="flex flex-wrap items-center gap-3">
        <p className="flex-1 min-w-[14rem] text-[13px] text-muted">
          Subjects without their own finish date aim for the end of the school year. Saving offers to re-plan every learner.
        </p>
        {changed && (
          <>
            <Button size="sm" onClick={() => setForm(null)}>Cancel</Button>
            <Button size="sm" variant="primary" disabled={saving} onClick={save}>Save dates</Button>
          </>
        )}
      </div>
    </Section>
  );
}

function AutoReplan() {
  const { data } = useAutoReplan();
  const client = useQueryClient();
  const toast = useToast();
  const change = async (enabled) => {
    try {
      await calendarApi.setAutoReplan(enabled);
      await client.invalidateQueries({ queryKey: keys.autoReplan });
      toast(enabled ? 'Unfinished lessons will move forward each morning.' : 'Unfinished lessons now stay until you re-plan.');
    } catch (error) {
      toast({ tone: 'problem', message: `Not saved: ${clean(error)}` });
    }
  };
  return (
    <label className="flex items-start gap-3 p-4 rounded-xl bg-paper text-sm cursor-pointer">
      <input type="checkbox" className="mt-0.5 w-5 h-5 accent-[var(--color-action)]" checked={Boolean(data?.enabled)}
        disabled={!data} onChange={(e) => change(e.target.checked)} />
      <span className="flex flex-col gap-0.5">
        <span className="font-semibold">Move unfinished lessons forward each morning</span>
        <span className="text-[13px] text-muted">
          Before the day's first lesson, lessons not marked done are planned again from today, in order. A school
          day already under way is never changed.
        </span>
      </span>
    </label>
  );
}

/* ── Study times ───────────────────────────────────────────────────────── */

function StudyTimes() {
  const { learners, single, learner: find } = useLearner();
  const [chosen, setChosen] = useState(single);
  const child = find(chosen) || learners[0];
  const { data: windows = [] } = useTimeWindows(child?.id);
  const [adding, setAdding] = useState(null);
  const [dirty, setDirty] = useState(false);
  const client = useQueryClient();
  const toast = useToast();
  const replan = useReplanAction();
  if (!child) return null;
  const tones = learnerTones(child.color);

  const refresh = () => client.invalidateQueries({ queryKey: keys.timeWindows(child.id) });
  const add = async () => {
    if (adding.end_time <= adding.start_time) {
      toast({ tone: 'problem', message: 'The end time must be after the start time.' });
      return;
    }
    try {
      await timeWindowsApi.create({ ...adding, child_id: child.id });
      await refresh();
      setAdding(null);
      setDirty(true);
    } catch (error) {
      toast({ tone: 'problem', message: `Not added: ${clean(error)}` });
    }
  };
  const remove = async (window) => {
    try {
      await timeWindowsApi.delete(window.id);
      await refresh();
      setDirty(true);
    } catch (error) {
      toast({ tone: 'problem', message: `Not removed: ${clean(error)}` });
    }
  };

  const byDay = WEEKDAYS.map((day, index) => ({ day, index, windows: windows.filter((w) => w.weekday === index).sort((a, b) => a.start_time.localeCompare(b.start_time)) }));

  return (
    <Section id="study-times" title="Study times" action={(
      <SegmentedControl label="Learner" size="sm" value={child.id} onChange={(id) => { setChosen(id); setAdding(null); setDirty(false); }}
        options={learners.map((c) => ({ value: c.id, label: c.name, dot: c.color }))} />
    )}>
      <p className="text-[13px] text-muted">Lessons are planned only inside these times.</p>
      <ul className="flex flex-col gap-2">
        {byDay.filter((d) => d.windows.length).map(({ day, windows: list }) => (
          <li key={day} className="flex flex-wrap items-center gap-3">
            <span className="w-12 text-sm font-bold">{day.slice(0, 3)}</span>
            {list.map((w) => (
              <span key={w.id} className="inline-flex items-center gap-1 pl-3 pr-1 h-9 rounded-full text-sm font-semibold"
                style={{ background: tones.soft, color: tones.strong }}>
                {shortTime(w.start_time)} – {shortTime(w.end_time)}
                <IconButton icon={X} size="sm" variant="quiet" label={`Remove ${day} ${w.start_time}–${w.end_time}`}
                  onClick={() => remove(w)} className="!w-7 !h-7 rounded-full" />
              </span>
            ))}
          </li>
        ))}
        {!windows.length && <li className="text-sm text-subtle">No study times yet, so nothing can be planned for {child.name}.</li>}
      </ul>
      {adding ? (
        <div className="flex flex-wrap items-end gap-3 p-4 rounded-xl bg-paper">
          <Field label="Day" className="w-40">
            <select className={inputClasses} value={adding.weekday} onChange={(e) => setAdding({ ...adding, weekday: Number(e.target.value) })}>
              {WEEKDAYS.map((d, i) => <option key={d} value={i}>{d}</option>)}
            </select>
          </Field>
          <Field label="From" type="time" className="w-32" value={adding.start_time} onChange={(e) => setAdding({ ...adding, start_time: e.target.value })} />
          <Field label="To" type="time" className="w-32" value={adding.end_time} onChange={(e) => setAdding({ ...adding, end_time: e.target.value })} />
          <Button onClick={() => setAdding(null)}>Cancel</Button>
          <Button variant="primary" onClick={add}>Add</Button>
        </div>
      ) : (
        <Button size="sm" icon={Plus} className="self-start" onClick={() => setAdding({ weekday: 0, start_time: '08:00', end_time: '11:00' })}>
          Add a study time
        </Button>
      )}
      {dirty && (
        <div className="flex flex-wrap items-center gap-3 px-4 py-3 rounded-xl bg-attention-soft text-sm">
          <span className="flex-1">The plan still uses the old times until you re-plan {child.name}.</span>
          <Button size="sm" variant="strong" onClick={async () => { if (await replan.run([child])) setDirty(false); }}>Re-plan {child.name}</Button>
        </div>
      )}
    </Section>
  );
}

/* ── Home server ───────────────────────────────────────────────────────── */

function backupTime(name) {
  const match = /homeschooling-(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z/.exec(name || '');
  if (!match) return name;
  const [, y, mo, d, h, mi, s] = match;
  return new Date(Date.UTC(+y, +mo - 1, +d, +h, +mi, +s)).toLocaleString();
}

function HomeServer() {
  const device = useDevice();
  const { data: storage } = useStorageStatus();
  const { data: usage } = useNarrationUsage();
  const [folder, setFolder] = useState(null);
  const [busy, setBusy] = useState('');
  const client = useQueryClient();
  const toast = useToast();
  const isHost = Boolean(device?.host);

  const run = async (label, action, success) => {
    setBusy(label);
    try {
      const result = await action();
      await client.invalidateQueries({ queryKey: keys.storage });
      toast(typeof success === 'function' ? success(result) : success);
    } catch (error) {
      toast({ tone: 'problem', message: clean(error) });
    } finally {
      setBusy('');
    }
  };

  return (
    <Section id="home-server" title="Home server and backups">
      <p className="text-[13px] text-muted">
        Records are kept in a database on the family computer. Books, handwriting, audio and backups are files in the
        Homeschooling folder that Google Drive for desktop keeps in sync.
      </p>
      <dl className="grid grid-cols-[8rem_1fr] gap-x-3 gap-y-2 text-sm">
        <dt className="text-muted">Records</dt>
        <dd className="font-semibold">{storage ? 'Saved on this computer' : 'Home server not answering'}</dd>
        <dt className="text-muted">Drive folder</dt>
        <dd className="break-all">
          <span className="font-mono text-[13px]">{storage?.drive_folder || 'Not set'}</span>
          {storage && !storage.drive_folder_available && (
            <span className="block text-attention font-semibold">Not available. Is Google Drive for desktop running and signed in?</span>
          )}
        </dd>
        <dt className="text-muted">Last backup</dt>
        <dd className="font-semibold">{storage?.last_backup ? backupTime(storage.last_backup) : 'None yet'}</dd>
        {usage && (
          <>
            <dt className="text-muted">Read-along voices</dt>
            <dd>{usage.characters.toLocaleString()} of {usage.monthly_limit.toLocaleString()} characters this month</dd>
          </>
        )}
      </dl>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="strong" disabled={Boolean(busy)}
          onClick={() => run('backup', systemApi.backupNow, (r) => `Backup saved: ${r.name}`)}>
          {busy === 'backup' ? 'Backing up…' : 'Back up now'}
        </Button>
        <Button size="sm" disabled={Boolean(busy)}
          onClick={() => run('export', systemApi.exportNow, (r) => (r.path ? 'Excel copy written to the Drive folder.' : 'The Drive folder is not available.'))}>
          {busy === 'export' ? 'Writing…' : 'Write the Excel copy'}
        </Button>
      </div>
      <p className="text-[13px] text-subtle">
        A verified backup goes to the folder's _App Backups every day and when the server stops (the newest 30 are kept).
        The Excel copy is for reading only and leaves out answer keys. For lessons without internet, right-click the
        Homeschooling folder in File Explorer and choose Offline access → Available offline.
      </p>
      {isHost ? (
        <form className="flex flex-wrap items-end gap-2" onSubmit={(e) => {
          e.preventDefault();
          run('folder', () => systemApi.setDriveFolder((folder ?? storage?.drive_folder ?? '').trim()), 'Drive folder saved.');
        }}>
          <Field label="Change the Drive folder" className="flex-1 min-w-[16rem]" value={folder ?? storage?.drive_folder ?? ''}
            placeholder="G:\My Drive\…\Homeschooling" onChange={(e) => setFolder(e.target.value)} />
          <Button type="submit" size="md" disabled={Boolean(busy) || folder === null}>Use this folder</Button>
        </form>
      ) : (
        <p className="text-[13px] text-subtle">The Drive folder can be changed only on the family computer.</p>
      )}
    </Section>
  );
}

export default function Settings() {
  const { hash } = useLocation();
  useEffect(() => {
    if (hash) document.getElementById(hash.slice(1))?.scrollIntoView({ block: 'start' });
  }, [hash]);
  return (
    <div className="px-4 md:px-10 py-8 flex flex-col gap-6">
      <h1 className="font-display text-3xl md:text-4xl font-medium">Settings</h1>
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-5 items-start">
        <div className="flex flex-col gap-5"><Family /><SchoolYear /></div>
        <div className="flex flex-col gap-5"><StudyTimes /><HomeServer /></div>
      </div>
    </div>
  );
}
