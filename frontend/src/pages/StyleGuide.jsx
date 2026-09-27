import { useState } from 'react';
import { BookOpen, Headphones, Plus, RefreshCw } from 'lucide-react';
import { useChildren } from '../api/queries';
import { learnerTones } from '../utils/colors';
import {
  Badge, Button, CheckButton, Dialog, IconButton, LearnerSwitcher, LessonRow, ProgressBar, SegmentedControl,
  useConfirm, useToast,
} from '../ui';

const SAMPLE = [
  { id: 1, subject_name: 'History', topic_title: 'The Rus Come to Constantinople', time_start: '8:00', time_end: '9:00', page_from: 208, page_to: 210 },
  { id: 2, subject_name: 'Language Arts', topic_title: 'Lesson 71', time_start: '9:00', time_end: '10:00', page_from: 61, page_to: 65 },
  { id: 3, subject_name: 'Portuguese', topic_title: 'Dígrafo RR', time_start: '10:00', time_end: '11:00', page_from: 277, page_to: 277 },
];

function Section({ title, children }) {
  return (
    <section className="flex flex-col gap-4">
      <h2 className="text-[13px] font-bold tracking-[0.8px] uppercase text-muted">{title}</h2>
      {children}
    </section>
  );
}

/** /styleguide: the shared components with sample data, for checking the look. */
export default function StyleGuide() {
  const { data: learners = [] } = useChildren();
  const [learner, setLearner] = useState('all');
  const [view, setView] = useState('week');
  const [lessons, setLessons] = useState(SAMPLE);
  const [dialogOpen, setDialogOpen] = useState(false);
  const confirm = useConfirm();
  const toast = useToast();
  const color = learners[0]?.color || '#4A90D9';

  const toggle = (lesson, done) => setLessons((list) => list.map((l) => (l.id === lesson.id ? { ...l, is_completed: done } : l)));

  return (
    <main className="min-h-screen bg-paper px-6 py-10 md:px-14">
      <div className="max-w-5xl mx-auto flex flex-col gap-10">
        <header className="flex flex-col gap-2">
          <h1 className="font-display text-[44px] font-medium leading-tight">Homeschool style guide</h1>
          <p className="text-muted">The shared building blocks the rebuilt screens use.</p>
        </header>

        <Section title="Type">
          <div className="bg-surface border border-line rounded-2xl p-6 flex flex-col gap-3">
            <p className="font-display text-[40px] font-medium">Good morning</p>
            <p className="font-display text-[28px] font-medium">The lesson title</p>
            <p className="text-[17px] font-bold">Card heading</p>
            <p className="text-[15px]">Body text and list rows</p>
            <p className="text-[13px] text-muted">Supporting detail</p>
          </div>
        </Section>

        <Section title="Learner colours">
          <div className="flex flex-wrap gap-4">
            {learners.map((child) => {
              const tones = learnerTones(child.color);
              return (
                <div key={child.id} className="flex flex-col gap-1.5 w-36">
                  <div className="h-10 rounded-xl" style={{ background: tones.strong }} />
                  <div className="h-5 rounded-md" style={{ background: tones.soft }} />
                  <span className="text-xs font-semibold">{child.name} · {child.color} → {tones.strong}</span>
                </div>
              );
            })}
          </div>
        </Section>

        <Section title="Buttons">
          <div className="flex flex-wrap items-center gap-2.5">
            <Button variant="primary" icon={BookOpen}>Open the lesson</Button>
            <Button variant="strong" icon={RefreshCw}>Re-plan from today</Button>
            <Button icon={Headphones}>Read along</Button>
            <Button variant="quiet">Quiet</Button>
            <Button variant="danger">Delete book</Button>
            <Button size="sm" icon={Plus}>Small</Button>
            <IconButton icon={Plus} label="Add" />
            <Button disabled>Disabled</Button>
          </div>
        </Section>

        <Section title="Switchers and badges">
          <div className="flex flex-wrap items-center gap-4">
            <LearnerSwitcher learners={learners} value={learner} onChange={setLearner} />
            <SegmentedControl label="View" size="sm" value={view} onChange={setView}
              options={[{ value: 'week', label: 'Week' }, { value: 'month', label: 'Month' }]} />
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge color={learnerTones(color).strong} solid>Now</Badge>
            <Badge tone="action">Complete</Badge>
            <Badge tone="attention">Unfinished · 22 Sep</Badge>
            <Badge tone="problem">Book missing</Badge>
            <Badge>Mon · Wed · Fri</Badge>
          </div>
        </Section>

        <Section title="Lessons">
          <div className="bg-surface border border-line rounded-2xl p-2 max-w-xl">
            {lessons.map((lesson, index) => (
              <LessonRow key={lesson.id} lesson={lesson} learnerColor={color} now={index === 0}
                onToggle={toggle} onOpen={() => toast(`Opening ${lesson.topic_title}`)} />
            ))}
          </div>
          <div className="flex items-center gap-3">
            <CheckButton label="To do" onToggle={() => {}} />
            <CheckButton label="Now" current color={learnerTones(color).strong} onToggle={() => {}} />
            <CheckButton label="Done" done color={learnerTones(color).strong} onToggle={() => {}} />
          </div>
        </Section>

        <Section title="Progress">
          <div className="flex flex-col gap-4 max-w-xl">
            <ProgressBar label="History" value={46} marker={72} color={learnerTones(color).strong} />
            <ProgressBar label="Science" value={100} />
          </div>
        </Section>

        <Section title="Dialogs and messages">
          <div className="flex flex-wrap gap-2.5">
            <Button onClick={() => setDialogOpen(true)}>Open a dialog</Button>
            <Button onClick={async () => toast((await confirm({
              title: 'Delete the book "Story of the World V.2"?',
              description: 'Its chapters and planned lessons are removed too.',
              confirmLabel: 'Delete book', danger: true,
            })) ? 'You chose delete (nothing was deleted).' : 'Kept.')}>Ask to confirm</Button>
            <Button onClick={() => toast({ message: 'Could not reach the home server.', tone: 'problem' })}>Show a problem</Button>
          </div>
          <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} title="Edit subject"
            description="Changes re-plan this subject from today."
            footer={<><Button onClick={() => setDialogOpen(false)}>Cancel</Button><Button variant="primary" onClick={() => setDialogOpen(false)}>Save</Button></>}>
            <label className="flex flex-col gap-1.5 text-[13px] font-semibold text-muted">
              Name
              <input defaultValue="History" className="h-11 px-3 rounded-[10px] border border-line text-[15px] text-ink focus:outline-2 focus:outline-action" />
            </label>
          </Dialog>
        </Section>
      </div>
    </main>
  );
}
