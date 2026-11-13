import LessonWorkspace from '../components/LessonWorkspace';
import useViewportHeight from '../app/useViewportHeight';
import LessonSourcePages from '../components/LessonSourcePages';
import ExerciseAssignment from '../components/ExerciseAssignment';
import LessonPreparationBar from '../components/LessonPreparationBar';
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router';
import { useQueryClient } from '@tanstack/react-query';
import { getDocument } from 'pdfjs-dist';
import { ArrowLeft, BookOpen, Check, Plus, Trash2 } from 'lucide-react';
import clsx from 'clsx';
import PageViewer from '../components/PageViewer';
import ReadAlong from '../components/ReadAlong';
import VoiceBuilder from '../components/VoiceBuilder';
import InteractiveGuidedLesson from '../components/InteractiveGuidedLesson';
import OriginalSourcePage from '../components/OriginalSourcePage';
import { pauseNarration } from '../utils/narration';
import AIEnrichmentPanel from '../components/AIEnrichmentPanel';
import InsertPicker from '../components/InsertPicker';
import { getDocument as getDocumentInfo, getDocumentPages } from '../api/documents';
import { tutorApi } from '../api/tutor';
import { modeHref } from '../api/mode';
import { canvasApi } from '../api/canvas';
import { keys, useInserts, useSetLessonDone } from '../api/queries';
import { useLearner } from '../app/learnerContext';
import { Button, IconButton, SegmentedControl, useConfirm, useToast } from '../ui';
import { learnerTones } from '../utils/colors';
import { locateSentences, locateText, passageOnPages, requestReadFrom } from '../utils/readAlong';

/** Book and tutor side by side (the workspace's lg layout); narrower screens show one at a time. */
const SIDE_BY_SIDE = '(min-width: 1024px)';
function useSideBySide() {
  const [matches, setMatches] = useState(() => window.matchMedia?.(SIDE_BY_SIDE).matches ?? true);
  useEffect(() => {
    const list = window.matchMedia?.(SIDE_BY_SIDE);
    if (!list) return undefined;
    const change = () => setMatches(list.matches);
    list.addEventListener?.('change', change);
    return () => list.removeEventListener?.('change', change);
  }, []);
  return matches;
}

async function pageTexts(documentId, start, end) {
  // The same range as the page viewer's, so the two share one download.
  const info = await getDocumentInfo(documentId);
  const last = Math.min(end, info.page_count || end);
  const data = await getDocumentPages(documentId, start, last);
  const pdf = await getDocument({ data: data.slice() }).promise;
  const texts = [];
  for (let page = start; page <= last; page += 1) {
    const content = await (await pdf.getPage(page - start + 1)).getTextContent();
    texts.push({ page, text: content.items.map((item) => item.str || '').join(' ') });
  }
  return texts;
}

const clean = (error) => (error?.message || String(error)).replace(/^\/[^:]+: /, '');

/** Whether a scheduled lesson is already done, from any list already loaded. */
function useSlotDone(slotId) {
  const client = useQueryClient();
  const [done, setDone] = useState(() => {
    for (const [, slots] of client.getQueriesData({ queryKey: ['slots'] })) {
      const match = Array.isArray(slots) && slots.find((s) => String(s.id) === String(slotId));
      if (match) return Boolean(match.is_completed);
    }
    return false;
  });
  return [done, setDone];
}

function Tabs({ tabs, value, onChange }) {
  return (
    <div role="tablist" aria-label="Lesson tools" className="flex gap-1 px-4 pt-3 border-b border-line shrink-0 overflow-x-auto overflow-y-hidden">
      {tabs.map((tab) => (
        <button key={tab.id} type="button" role="tab" aria-selected={value === tab.id} onClick={() => onChange(tab.id)}
          className={clsx('h-11 px-3.5 text-[15px] whitespace-nowrap border-b-2 -mb-px',
            value === tab.id ? 'border-action font-bold text-ink' : 'border-transparent font-medium text-muted hover:text-ink')}>
          {tab.label}
        </button>
      ))}
    </div>
  );
}

function ExtraPages({ topicId, learner, viewing, onView }) {
  const { data: inserts = [] } = useInserts(topicId);
  const [picking, setPicking] = useState(false);
  const client = useQueryClient();
  const toast = useToast();
  const confirm = useConfirm();
  const refresh = () => client.invalidateQueries({ queryKey: keys.inserts(topicId) });

  const add = async (topic) => {
    setPicking(false);
    try {
      await canvasApi.createInsert({ parent_topic_id: topicId, insert_topic_id: topic.id });
      await refresh();
    } catch (error) {
      toast({ tone: 'problem', message: `Could not add the pages: ${clean(error)}` });
    }
  };
  const remove = async (insert) => {
    if (!(await confirm({ title: `Remove "${insert.insert_topic_title}" from this lesson?`, confirmLabel: 'Remove' }))) return;
    try {
      await canvasApi.deleteInsert(insert.id);
      if (viewing?.id === insert.id) onView(null);
      await refresh();
    } catch (error) {
      toast({ tone: 'problem', message: `Could not remove it: ${clean(error)}` });
    }
  };

  return (
    <div className="p-5 flex flex-col gap-3">
      <p className="text-sm text-muted">Pages from another book to read with this lesson.</p>
      {inserts.length === 0 && <p className="text-sm text-subtle">None added yet.</p>}
      <ul className="flex flex-col gap-2">
        {inserts.map((insert) => (
          <li key={insert.id} className={clsx('flex items-center gap-3 p-3 rounded-xl border',
            viewing?.id === insert.id ? 'border-action bg-action-soft' : 'border-line')}>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold truncate">{insert.insert_topic_title}</p>
              <p className="text-[13px] text-muted">{insert.insert_subject_name} · pp. {insert.insert_page_start}–{insert.insert_page_end}</p>
            </div>
            {insert.insert_document_id && (
              <Button size="sm" onClick={() => onView(viewing?.id === insert.id ? null : insert)}>
                {viewing?.id === insert.id ? 'Back to lesson' : 'Show'}
              </Button>
            )}
            <IconButton icon={Trash2} size="sm" variant="quiet" label={`Remove ${insert.insert_topic_title}`} onClick={() => remove(insert)} />
          </li>
        ))}
      </ul>
      <Button icon={Plus} onClick={() => setPicking(true)}>Add pages from another book</Button>
      {picking && <InsertPicker childId={learner} onSelect={add} onClose={() => setPicking(false)} />}
    </div>
  );
}

export function LessonReadMode({ mode, onChange, resumePath }) {
  return <div className="px-4 pt-3">
    {resumePath && <Button as={Link} to={modeHref(resumePath)} variant="primary" className="mb-3">Resume this tutoring lesson</Button>}
    <SegmentedControl label="What to read" size="sm" value={mode} onChange={onChange}
      options={[{ value: 'guide', label: 'Guided lesson' }, { value: 'book', label: 'Book text' }]} />
  </div>;
}

/** The guided lesson: written once by the AI, then read like any passage. */
export function GuidePanel({ guide, learner, topic, session, pinned, slotId, closed, resumeLesson, earlierVersion, newerVersion, warmUp, activeIndex, onActiveIndex, language, onChanged, onStarted, onFinished, onPassageModeChange, onSource, bookOnPage = false }) {
  const preparation = <LessonPreparationBar learner={learner} topic={topic} guide={guide} pinned={pinned} onChanged={onChanged} />;
  if (!guide) return <div className="flex flex-col min-h-0">
    {preparation}
    <div className="p-5 flex flex-col gap-3">
      <h2 className="text-base font-bold">Guided lesson</h2>
      <p className="text-sm text-muted leading-relaxed">Prepare a teacher’s walk-through of the assigned pages, with the original reading, useful explanations and activities. The guide and recorded voice are saved for every device.</p>
    </div>
  </div>;
  return <div className="guide-chat-panel" data-in-session={Boolean(session)}>
    {preparation}
    <InteractiveGuidedLesson key={`guide-${guide.guide_id}`} guide={guide} learner={learner} topic={topic} session={session} slotId={slotId} resumeLesson={resumeLesson} earlierVersion={earlierVersion} newerVersion={newerVersion} warmUp={warmUp}
      activeIndex={activeIndex} onActiveIndex={onActiveIndex} closed={closed} language={language} onStarted={onStarted} onFinished={onFinished}
      onPassageModeChange={onPassageModeChange} onSource={onSource} onVoiceBuilt={onChanged} bookOnPage={bookOnPage} lessonOptions={<>
        <LessonSourcePages topic={topic}/>
        <ExerciseAssignment topic={topic}/>
        <p className="text-xs text-muted">Prepared{guide.created_at ? ` on ${new Date(guide.created_at).toLocaleDateString()}` : ''}. Guide and voice generation are available above the lesson.</p>
      </>} />
  </div>;
}

/**
 * The full-screen lesson: /lesson?learner=&topic=, plus &slot= when opened
 * from the plan (for "Mark lesson done") or &session= when the tutor opens it.
 * It shows the original book pages with handwriting, the read-along, practice
 * and extra pages. Opening it or finishing the audio never completes a lesson.
 * In a tutor session only the pages and the read-along show.
 */
export default function Lesson() {
  useViewportHeight();
  const [params, setParams] = useSearchParams();
  const learner = params.get('learner');
  const topic = params.get('topic');
  const session = params.get('session');
  const slotId = params.get('slot');
  const navigate = useNavigate();
  const toast = useToast();
  const { learner: findLearner } = useLearner();
  const setLessonDone = useSetLessonDone();
  const [lesson, setLesson] = useState(null);
  const [error, setError] = useState('');
  const [activeIndex, setActiveIndex] = useState(null);
  const [passageVoice, setPassageVoice] = useState(false);
  const [guideIndex, setGuideIndex] = useState(null);
  const [readMode, setReadMode] = useState(null);
  const [sentencePages, setSentencePages] = useState([]);
  const [bookTexts, setBookTexts] = useState([]);
  const [closed, setClosed] = useState(false);
  const [tab, setTab] = useState(null);
  const [viewing, setViewing] = useState(null);
  const [sourcePage, setSourcePage] = useState(null);
  const sideBySide = useSideBySide();
  const [done, setDone] = useSlotDone(slotId);
  const started = useCallback((id) => {
    setParams((previous) => { const next = new URLSearchParams(previous); next.set('session', id); return next; }, { replace: true });
  }, [setParams]);

  const load = useCallback(() => {
    if (!learner || !topic) {
      setError('This lesson link is incomplete.');
      return;
    }
    tutorApi.reader(learner, topic, session).then((data) => {
      setLesson(data);
      setClosed(data.reader_state === 'closed');
    }).catch((e) => setError(clean(e)));
  }, [learner, topic, session]);

  useEffect(load, [load]);
  const voicePreparing = ['queued', 'running', 'aligning'].includes(lesson?.guide?.voice_preparation?.status);
  useEffect(() => {
    if (!voicePreparing) return undefined;
    const timer = window.setInterval(load, 4000);
    return () => window.clearInterval(timer);
  }, [voicePreparing, load]);

  useEffect(() => {
    if (!session) return undefined;
    const timer = window.setInterval(() => {
      tutorApi.readerState(session).then((s) => setClosed(s.reader_state === 'closed')).catch(() => {});
    }, 10000);
    return () => window.clearInterval(timer);
  }, [session]);

  const passage = lesson?.passage;
  useEffect(() => {
    if (!passage?.document_id || passage.hide_pdf || !passage.sentences?.length) return;
    pageTexts(passage.document_id, passage.pdf_pages.start, passage.pdf_pages.end)
      .then((texts) => { setBookTexts(texts); setSentencePages(locateSentences(texts, passage.sentences)); })
      .catch(() => { setBookTexts([]); setSentencePages([]); });
  }, [passage]);

  const slot = useMemo(() => passage && ({
    topic_id: Number(topic), document_id: passage.hide_pdf ? null : passage.document_id, page_from: passage.printed_pages.start,
    page_to: passage.printed_pages.end, pdf_page_offset: passage.pdf_page_offset,
    subject_name: lesson.subject_name, topic_title: passage.title,
  }), [passage, lesson, topic]);

  if (error) return <main className="min-h-dvh grid place-items-center p-6"><p className="text-problem">{error}</p></main>;
  if (!lesson) return <main className="min-h-dvh grid place-items-center text-muted">Opening the lesson…</main>;

  const child = findLearner(Number(learner));
  const tones = learnerTones(child?.color || '#2d5f54');
  const hasBook = Boolean(passage.document_id && !passage.hide_pdf);
  // The book's words are followed on the highlighted page beside the tutor, so
  // the tutor panel shows only the teacher's words. The script is unchanged.
  const bookOnPage = hasBook && sideBySide && !viewing && !passageVoice && passageOnPages(bookTexts, passage.sentences);
  const hasText = passage.sentences.length > 0;
  const reviewed = passage.status === 'verified';
  const voiceReady = lesson.audio.some((t) => t.synchronized && (t.preferred ?? true));
  const tabs = [
    hasText && { id: 'read', label: 'Read along' },
    !session && hasBook && { id: 'practice', label: 'Practice' },
    !session && { id: 'extra', label: 'Extra pages' },
  ].filter(Boolean);
  const activeTab = tabs.some((t) => t.id === tab) ? tab : tabs[0]?.id;
  const goBack = () => (window.history.length > 1 ? navigate(-1) : navigate('/'));
  const boundary = [
    passage.start_at && `Start at “${passage.start_at}” (book page ${passage.printed_pages.start}).`,
    passage.stop_before && `Stop before “${passage.stop_before}” (book page ${passage.printed_pages.end}).`,
  ].filter(Boolean).join(' ');
  const guide = lesson.guide;
  const activitySession = Boolean(session && guide?.activity_contract_version);
  const mode = activitySession ? 'guide' : readMode ?? (guide?.current ? 'guide' : 'book');
  // The book sentence being read: directly, or the one a guided-lesson sentence comes from.
  const sourceIndex = mode === 'guide'
    ? (guideIndex !== null ? guide?.sentences[guideIndex]?.source ?? null : null)
    : activeIndex;
  // A transcribed reading has no link to the page's text layer: follow the spoken book sentence itself.
  const spoken = mode === 'guide' && guideIndex !== null && sourceIndex === null && guide?.sentences[guideIndex]?.kind === 'book'
    ? guide.sentences[guideIndex].text : null;
  const highlight = sourceIndex !== null ? passage.sentences[sourceIndex]?.text : spoken;
  // A tap on a line of the book page reads again from that sentence of the guided reading.
  const readableSentences = mode === 'guide' && guide?.sentences
    ? guide.sentences.map((sentence, index) => sentence.kind === 'book'
      ? { key: index, text: sentence.source !== null && sentence.source !== undefined ? passage.sentences[sentence.source]?.text || sentence.text : sentence.text } : null).filter(Boolean)
    : null;
  // The book sentence read just before: a repeated phrase is found after it, not at its first appearance.
  const before = (index) => { for (let i = index - 1; i >= 0; i -= 1) if (guide?.sentences[i]?.kind === 'book') return guide.sentences[i]; return null; };
  const previousSpoken = mode === 'guide' && guideIndex !== null ? before(guideIndex) : null;
  const highlightAfter = sourceIndex !== null
    ? (mode === 'guide' ? (previousSpoken ? passage.sentences[previousSpoken.source]?.text ?? previousSpoken.text : null) : passage.sentences[sourceIndex - 1]?.text ?? null)
    : previousSpoken?.text ?? null;
  const previousPage = previousSpoken ? locateText(bookTexts, previousSpoken.text) : null;
  const spokenPage = spoken ? (locateText(bookTexts, spoken, previousPage?.index ?? 0) ?? locateText(bookTexts, spoken))?.page ?? null : null;
  const pages = passage.printed_pages.start === passage.printed_pages.end
    ? `page ${passage.printed_pages.start}` : `pages ${passage.printed_pages.start}–${passage.printed_pages.end}`;

  const markDone = (value) => {
    setDone(value);
    setLessonDone.mutate({ slotId: Number(slotId), done: value }, {
      onSuccess: () => value && toast('Lesson marked done.'),
      onError: (e) => { setDone(!value); toast({ tone: 'problem', message: `Not saved: ${clean(e)}` }); },
    });
  };

  const viewerSlot = viewing ? {
    topic_id: viewing.insert_topic_id, document_id: viewing.insert_document_id, page_from: viewing.insert_page_start,
    page_to: viewing.insert_page_end, pdf_page_offset: viewing.insert_pdf_page_offset,
    subject_name: viewing.insert_subject_name, topic_title: viewing.insert_topic_title,
  } : slot;

  return (
    <div className="lesson-workspace h-dvh flex flex-col bg-paper-deep">
      <header className="lesson-header px-3 flex items-center gap-3 bg-surface border-b border-line shrink-0">
        <IconButton icon={ArrowLeft} label="Back" onClick={goBack} />
        <div className="flex-1 min-w-0 flex flex-col">
          <span className="text-xs text-muted">
            <span className="font-bold" style={{ color: tones.strong }}>{lesson.learner.name}</span> · {lesson.subject_name} · {pages}
          </span>
          <h1 className="font-display text-base md:text-lg font-semibold truncate">{passage.title}</h1>
        </div>
        <details className="book-details"><summary className="text-xs font-semibold cursor-pointer">Book details</summary><div className="book-details-content">
          {boundary && <p>{boundary}</p>}
          {hasText && !reviewed && <p className="text-muted">The text was taken from the book automatically. If anything looks different, follow the book pages.</p>}
          {hasText && !activitySession && guide?.activity_contract_version && <Button size="sm" onClick={() => { pauseNarration(); setReadMode(mode === 'guide' ? 'book' : 'guide'); }}>{mode === 'guide' ? 'Read book text only' : 'Return to guided lesson'}</Button>}
          {closed && <p>This lesson is saved. Your answers remain in the lesson thread.</p>}
        </div></details>
        {slotId && !session && (
          done
            ? <Button onClick={() => markDone(false)} icon={Check}>Done · undo</Button>
            : <Button variant="primary" icon={Check} onClick={() => markDone(true)}>Mark lesson done</Button>
        )}
      </header>
      {lesson.finished_lesson && !session && <div className="px-4 py-3 bg-action-soft text-sm flex flex-wrap gap-3">
        <span>{lesson.finished_lesson.unfinished ? `This lesson was finished with ${lesson.finished_lesson.unfinished === 1 ? 'one thing' : `${lesson.finished_lesson.unfinished} things`} left to do.` : 'This lesson was finished.'}</span>
        <Link to={lesson.finished_lesson.path} className="font-semibold underline">See the finished lesson</Link>
      </div>}
      {lesson.resume_lesson && <div className="px-4 py-3 bg-attention-soft text-sm flex flex-wrap gap-3">
        <span>Your place in {lesson.resume_lesson.title} is saved. You can start this lesson now.</span>
        <Link to={lesson.resume_lesson.path} className="font-semibold underline">Resume unfinished lesson</Link>
      </div>}
      {closed && !guide?.activity_contract_version && (
        <div role="alert" className="px-4 py-3 bg-action-soft text-action border-b border-line text-sm font-medium">
          This lesson has ended and its progress is saved. You can review the learning summary in Progress.
        </div>
      )}
      {hasBook && !hasText && !viewing && (
        <p className="px-4 py-2 text-[13px] text-attention bg-attention-soft border-b border-line">
          {(passage.issues?.[0] || 'This lesson has no text to read along with').replace(/\.$/, '')}, so read-along is not available.
        </p>
      )}
      {hasText && !reviewed && !viewing && !guide?.activity_contract_version && (
        <p className="px-4 py-2 text-[13px] text-muted bg-surface border-b border-line">
          The text was taken from the book automatically. If anything looks different, follow the book pages.
        </p>
      )}
      {viewing && (
        <div className="px-4 py-2 flex items-center gap-3 text-sm bg-action-soft text-action border-b border-line">
          <span className="flex-1">Showing extra pages: <strong>{viewing.insert_topic_title}</strong></span>
          <Button size="sm" onClick={() => setViewing(null)}>Back to the lesson</Button>
        </div>
      )}

      <LessonWorkspace hasBook={hasBook} hasTutor={tabs.length > 0} book={
        <>
          {viewerSlot?.document_id ? (
            <PageViewer key={viewing?.id ?? 'lesson'} slot={viewerSlot} childId={Number(learner)}
              highlightSentence={!viewing && hasText && !passageVoice ? highlight : null} highlightAfter={highlightAfter}
              requestedPage={viewing ? null : sourceIndex !== null ? sentencePages[sourceIndex] : spokenPage}
              readableSentences={viewing ? null : readableSentences} onReadFrom={requestReadFrom} />
          ) : (
            <div className="h-full grid place-items-center p-8 text-center">
              <div className="flex flex-col items-center gap-3 max-w-sm">
                <BookOpen aria-hidden="true" className="w-10 h-10 text-subtle" />
                <p className="font-semibold">Read this lesson from the printed book</p>
                <p className="text-sm text-muted">{passage.title}, {pages}.</p>
              </div>
            </div>
          )}
        </>
      }>
        {tabs.length > 0 && (
          <aside aria-label="Lesson tools" className="lesson-tutor-panel shrink-0 bg-surface border-t lg:border-t-0 lg:border-l border-line min-h-0 flex flex-col">
            {tabs.length > 1 && <Tabs tabs={tabs} value={activeTab} onChange={setTab} />}
            <div role="region" aria-label="Lesson panel content" tabIndex={0} className={clsx('flex-1 min-h-0 overscroll-contain', activeTab === 'read' && mode === 'guide' && guide?.activity_contract_version ? 'flex flex-col overflow-hidden' : 'overflow-y-auto')}>
              {activeTab === 'read' && !activitySession && (!guide?.activity_contract_version || mode === 'book') && (
                <LessonReadMode mode={mode} resumePath={lesson.resume_current_lesson?.path}
                  onChange={(next) => { pauseNarration(); setReadMode(next); }} />
              )}
              {activeTab === 'read' && mode === 'guide' && (
                <GuidePanel guide={guide} learner={learner} topic={topic} session={session} pinned={lesson.interactive} slotId={slotId} closed={closed} resumeLesson={lesson.resume_lesson} earlierVersion={lesson.resume_current_lesson?.earlier_version ? lesson.resume_current_lesson : null} newerVersion={lesson.newer_version} warmUp={lesson.warm_up}
                  activeIndex={guideIndex} onActiveIndex={setGuideIndex} language={lesson.language} onChanged={load}
                  onPassageModeChange={setPassageVoice} bookOnPage={bookOnPage}
                  onSource={(source) => { pauseNarration(); setSourcePage(source); }}
                  onStarted={started} onFinished={() => { setClosed(true); setDone(true); load(); }} />
              )}
              {activeTab === 'read' && mode === 'book' && (
                <>
                  {!voiceReady && !closed && <VoiceBuilder learner={learner} topic={topic} onBuilt={load} />}
                  <div>
                    <ReadAlong key={lesson.audio.map((t) => t.track_id).join()} passage={passage} tracks={lesson.audio}
                      activeIndex={activeIndex} onActiveIndex={setActiveIndex} disabled={closed} language={lesson.language} onPassageModeChange={setPassageVoice} />
                  </div>
                </>
              )}
              {activeTab === 'practice' && (
                <AIEnrichmentPanel topicId={Number(topic)} pageStart={slot.page_from} pageEnd={slot.page_to}
                  documentId={slot.document_id} pdfPageOffset={slot.pdf_page_offset} language={lesson.language} embedded />
              )}
              {activeTab === 'extra' && (
                <ExtraPages topicId={Number(topic)} learner={Number(learner)} viewing={viewing} onView={setViewing} />
              )}
            </div>
          </aside>
        )}
      </LessonWorkspace>
      {sourcePage && session && <OriginalSourcePage session={session} document={sourcePage.document_id}
        page={sourcePage.page} onClose={() => setSourcePage(null)} />}
    </div>
  );
}
