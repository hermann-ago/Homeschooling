import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router';
import { useQueryClient } from '@tanstack/react-query';
import { getDocument } from 'pdfjs-dist';
import { ArrowLeft, BookOpen, Check, Plus, Sparkles, Trash2 } from 'lucide-react';
import clsx from 'clsx';
import PageViewer from '../components/PageViewer';
import ReadAlong from '../components/ReadAlong';
import VoiceBuilder from '../components/VoiceBuilder';
import AIEnrichmentPanel from '../components/AIEnrichmentPanel';
import InsertPicker from '../components/InsertPicker';
import { getDocumentData } from '../api/documents';
import { tutorApi } from '../api/tutor';
import { canvasApi } from '../api/canvas';
import { keys, useInserts, useSetLessonDone } from '../api/queries';
import { useLearner } from '../app/learnerContext';
import { Button, IconButton, SegmentedControl, useConfirm, useToast } from '../ui';
import { learnerTones } from '../utils/colors';
import { locateSentences } from '../utils/readAlong';

async function pageTexts(documentId, start, end) {
  const data = await getDocumentData(documentId);
  const pdf = await getDocument({ data }).promise;
  const texts = [];
  for (let page = start; page <= Math.min(end, pdf.numPages); page += 1) {
    const content = await (await pdf.getPage(page)).getTextContent();
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
    <div role="tablist" aria-label="Lesson tools" className="flex gap-1 px-4 pt-3 border-b border-line shrink-0 overflow-x-auto">
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

/** The guided lesson: written once by the AI, then read like any passage. */
function GuidePanel({ guide, learner, topic, session, closed, activeIndex, onActiveIndex, language, onChanged }) {
  const [writing, setWriting] = useState(false);
  const [problem, setProblem] = useState('');
  const confirm = useConfirm();
  const write = async (rewrite) => {
    if (rewrite && !(await confirm({
      title: 'Write the guided lesson again?',
      description: 'The AI writes a new version. Its voice will need to be created again.',
      confirmLabel: 'Write again',
    }))) return;
    setWriting(true);
    setProblem('');
    try {
      await tutorApi.writeGuide(learner, topic, rewrite);
      onChanged();
    } catch (error) {
      setProblem(clean(error));
    } finally {
      setWriting(false);
    }
  };

  if (!guide?.current) {
    return (
      <div className="p-5 flex flex-col gap-3">
        <div className="flex items-center gap-2.5">
          <span className="w-9 h-9 rounded-xl bg-action-soft text-action grid place-items-center"><Sparkles aria-hidden="true" className="w-5 h-5" /></span>
          <h2 className="text-base font-bold">Guided lesson</h2>
        </div>
        <p className="text-sm text-muted leading-relaxed">
          The AI turns this lesson into a teacher's walk-through: a welcome, the book text read in full, short
          explanations of hard words and ideas along the way, and a recap. Lessons that are already a teacher's script
          are tidied into one clear reading.
        </p>
        {guide && !guide.current && (
          <p className="text-[13px] text-attention">The book pages for this lesson changed since the guide was written.</p>
        )}
        <Button variant="primary" icon={Sparkles} disabled={writing || closed} onClick={() => write(Boolean(guide))}>
          {writing ? 'Writing the guided lesson…' : guide ? 'Write it again for the new pages' : 'Write the guided lesson'}
        </Button>
        {writing && <p className="text-[13px] text-muted" role="status">This takes about half a minute.</p>}
        {problem && <p className="text-[13px] text-problem">{problem}</p>}
      </div>
    );
  }

  const voiceReady = guide.audio.some((t) => t.synchronized);
  return (
    <>
      <div className="px-4 py-2.5 flex items-center gap-3 border-b border-line text-[13px] text-muted">
        <span className="flex-1">
          {guide.mode === 'tidy' ? 'Tidied' : 'Written'} by AI{guide.created_at ? ` on ${new Date(guide.created_at).toLocaleDateString()}` : ''}. Listen once before the lesson.
        </span>
        {!session && <Button size="sm" variant="quiet" disabled={writing} onClick={() => write(true)}>{writing ? 'Writing…' : 'Write again'}</Button>}
      </div>
      {problem && <p className="px-4 py-2 text-[13px] text-problem">{problem}</p>}
      {!voiceReady && !closed && <VoiceBuilder learner={learner} topic={topic} guide onBuilt={onChanged} />}
      <div className="flex-1 min-h-0">
        <ReadAlong key={`guide-${guide.guide_id}-${guide.audio.map((t) => t.track_id).join()}`} passage={guide} tracks={guide.audio}
          activeIndex={activeIndex} onActiveIndex={onActiveIndex} disabled={closed} language={language} />
      </div>
    </>
  );
}

/**
 * The full-screen lesson: /lesson?learner=&topic=, plus &slot= when opened
 * from the plan (for "Mark lesson done") or &session= when the tutor opens it.
 * It shows the original book pages with handwriting, the read-along, practice
 * and extra pages. Opening it or finishing the audio never completes a lesson.
 * In a tutor session only the pages and the read-along show.
 */
export default function Lesson() {
  const [params] = useSearchParams();
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
  const [guideIndex, setGuideIndex] = useState(null);
  const [readMode, setReadMode] = useState(null);
  const [sentencePages, setSentencePages] = useState([]);
  const [closed, setClosed] = useState(false);
  const [tab, setTab] = useState(null);
  const [viewing, setViewing] = useState(null);
  const [done, setDone] = useSlotDone(slotId);

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

  useEffect(() => {
    if (!session) return undefined;
    const timer = window.setInterval(() => {
      tutorApi.readerState(session).then((s) => setClosed(s.reader_state === 'closed')).catch(() => {});
    }, 10000);
    return () => window.clearInterval(timer);
  }, [session]);

  const passage = lesson?.passage;
  useEffect(() => {
    if (!passage?.document_id || !passage.sentences?.length) return;
    pageTexts(passage.document_id, passage.pdf_pages.start, passage.pdf_pages.end)
      .then((texts) => setSentencePages(locateSentences(texts, passage.sentences)))
      .catch(() => setSentencePages([]));
  }, [passage]);

  const slot = useMemo(() => passage && ({
    topic_id: Number(topic), document_id: passage.document_id, page_from: passage.printed_pages.start,
    page_to: passage.printed_pages.end, pdf_page_offset: passage.pdf_page_offset,
    subject_name: lesson.subject_name, topic_title: passage.title,
  }), [passage, lesson, topic]);

  if (error) return <main className="min-h-dvh grid place-items-center p-6"><p className="text-problem">{error}</p></main>;
  if (!lesson) return <main className="min-h-dvh grid place-items-center text-muted">Opening the lesson…</main>;

  const child = findLearner(Number(learner));
  const tones = learnerTones(child?.color || '#2d5f54');
  const hasBook = Boolean(passage.document_id);
  const hasText = passage.sentences.length > 0;
  const reviewed = passage.status === 'verified';
  const voiceReady = lesson.audio.some((t) => t.synchronized);
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
  const mode = readMode ?? (guide?.current ? 'guide' : 'book');
  // The book sentence being read: directly, or the one a guided-lesson sentence comes from.
  const sourceIndex = mode === 'guide'
    ? (guideIndex !== null ? guide?.sentences[guideIndex]?.source ?? null : null)
    : activeIndex;
  const highlight = sourceIndex !== null ? passage.sentences[sourceIndex]?.text : null;
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
    <div className="h-dvh flex flex-col bg-paper-deep">
      <header className="min-h-[68px] px-4 md:px-5 py-2 flex flex-wrap items-center gap-3 md:gap-4 bg-surface border-b border-line">
        {!session && <IconButton icon={ArrowLeft} label="Back" onClick={goBack} />}
        <div className="flex-1 min-w-0 flex flex-col">
          <span className="text-[13px] text-muted">
            <span className="font-bold" style={{ color: tones.strong }}>{lesson.learner.name}</span> · {lesson.subject_name} · {pages}
          </span>
          <h1 className="font-display text-xl md:text-[21px] font-semibold truncate">{passage.title}</h1>
        </div>
        {slotId && !session && (
          done
            ? <Button onClick={() => markDone(false)} icon={Check}>Done · undo</Button>
            : <Button variant="primary" icon={Check} onClick={() => markDone(true)}>Mark lesson done</Button>
        )}
      </header>
      {closed && (
        <div role="alert" className="px-4 py-3 bg-action-soft text-action border-b border-line text-sm font-medium">
          This lesson has ended. Your tutor will tell you what comes next.
        </div>
      )}
      {hasBook && !hasText && !viewing && (
        <p className="px-4 py-2 text-[13px] text-attention bg-attention-soft border-b border-line">
          {(passage.issues?.[0] || 'This lesson has no text to read along with').replace(/\.$/, '')}, so read-along is not available.
        </p>
      )}
      {hasText && !reviewed && !viewing && (
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

      <div className="flex-1 min-h-0 flex flex-col lg:flex-row">
        <div className="flex-1 min-h-0 min-w-0 bg-surface">
          {viewerSlot?.document_id ? (
            <PageViewer key={viewing?.id ?? 'lesson'} slot={viewerSlot} childId={Number(learner)}
              boundaryNote={viewing ? null : boundary}
              highlightSentence={!viewing && hasText ? highlight : null}
              requestedPage={!viewing && sourceIndex !== null ? sentencePages[sourceIndex] : null} />
          ) : (
            <div className="h-full grid place-items-center p-8 text-center">
              <div className="flex flex-col items-center gap-3 max-w-sm">
                <BookOpen aria-hidden="true" className="w-10 h-10 text-subtle" />
                <p className="font-semibold">Read this lesson from the printed book</p>
                <p className="text-sm text-muted">{passage.title}, {pages}.</p>
              </div>
            </div>
          )}
        </div>
        {tabs.length > 0 && (
          <aside aria-label="Lesson tools" className="lg:w-[400px] h-[50dvh] lg:h-auto shrink-0 bg-surface border-t lg:border-t-0 lg:border-l border-line min-h-0 flex flex-col">
            <Tabs tabs={tabs} value={activeTab} onChange={setTab} />
            <div className="flex-1 min-h-0 overflow-y-auto flex flex-col">
              {activeTab === 'read' && (
                <div className="px-4 pt-3">
                  <SegmentedControl label="What to read" size="sm" value={mode} onChange={setReadMode}
                    options={[{ value: 'guide', label: 'Guided lesson' }, { value: 'book', label: 'Book text' }]} />
                </div>
              )}
              {activeTab === 'read' && mode === 'guide' && (
                <GuidePanel guide={guide} learner={learner} topic={topic} session={session} closed={closed}
                  activeIndex={guideIndex} onActiveIndex={setGuideIndex} language={lesson.language} onChanged={load} />
              )}
              {activeTab === 'read' && mode === 'book' && (
                <>
                  {!voiceReady && !closed && <VoiceBuilder learner={learner} topic={topic} onBuilt={load} />}
                  <div className="flex-1 min-h-0">
                    <ReadAlong key={lesson.audio.map((t) => t.track_id).join()} passage={passage} tracks={lesson.audio}
                      activeIndex={activeIndex} onActiveIndex={setActiveIndex} disabled={closed} language={lesson.language} />
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
      </div>
    </div>
  );
}
