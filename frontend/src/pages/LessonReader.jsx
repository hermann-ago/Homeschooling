import React, { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { getDocument } from 'pdfjs-dist';
import PageViewer from '../components/PageViewer';
import ReadAlong from '../components/ReadAlong';
import { getDocumentData } from '../api/documents';
import { tutorApi } from '../api/tutor';
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

/**
 * The lesson reader opened by the tutor: /lesson?learner=&topic=&session=.
 * It shows the original PDF pages (layout, maps, illustrations), the exact
 * assigned boundaries, handwriting tools and the read-along passage. Opening
 * it or finishing the audio never completes the lesson.
 */
export default function LessonReader() {
  const [params] = useSearchParams();
  const learner = params.get('learner');
  const topic = params.get('topic');
  const session = params.get('session');
  const [lesson, setLesson] = useState(null);
  const [error, setError] = useState('');
  const [activeIndex, setActiveIndex] = useState(null);
  const [sentencePages, setSentencePages] = useState([]);
  const [closed, setClosed] = useState(false);

  useEffect(() => {
    if (!learner || !topic) {
      setError('This lesson link is incomplete.');
      return;
    }
    tutorApi.reader(learner, topic, session).then((data) => {
      setLesson(data);
      setClosed(data.reader_state === 'closed');
    }).catch((e) => setError(e.message.replace(/^\/[^:]+: /, '')));
  }, [learner, topic, session]);

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
    document_id: passage.document_id, page_from: passage.printed_pages.start, page_to: passage.printed_pages.end,
    pdf_page_offset: passage.pdf_page_offset, subject_name: lesson.subject_name, topic_title: passage.title,
  }), [passage, lesson]);

  if (error) return <main className="min-h-screen grid place-items-center p-6"><p className="text-red-700">{error}</p></main>;
  if (!lesson) return <main className="min-h-screen grid place-items-center">Opening the lesson…</main>;

  const reviewed = passage.status === 'verified';
  const boundary = [
    passage.start_at && `Start at “${passage.start_at}” (book page ${passage.printed_pages.start}).`,
    passage.stop_before && `Stop before “${passage.stop_before}” (book page ${passage.printed_pages.end}).`,
  ].filter(Boolean).join(' ');
  const highlight = activeIndex !== null ? passage.sentences[activeIndex]?.text : null;

  return (
    <div className="h-screen flex flex-col bg-background">
      <header className="px-4 py-3 border-b bg-surface flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs text-text-secondary">{lesson.learner.name} · {lesson.subject_name}</p>
          <h1 className="font-bold truncate">{passage.title}</h1>
        </div>
        {!reviewed && (
          <p className="text-xs text-amber-800 max-w-xs">Read from the book pages. The tutor has not checked the extracted text yet, so read-along is off.</p>
        )}
      </header>
      {closed && (
        <div role="alert" className="px-4 py-3 bg-emerald-50 border-b border-emerald-200 text-sm">
          This lesson has ended. Your tutor will tell you what comes next.
        </div>
      )}
      <div className="flex-1 min-h-0 flex flex-col lg:flex-row">
        <div className="flex-1 min-h-0 min-w-0">
          <PageViewer slot={slot} childId={Number(learner)} hideClose boundaryNote={boundary}
            highlightSentence={reviewed ? highlight : null}
            requestedPage={activeIndex !== null ? sentencePages[activeIndex] : null} />
        </div>
        {reviewed && (
          <aside className="lg:w-[380px] h-72 lg:h-auto border-t lg:border-t-0 lg:border-l bg-surface min-h-0" aria-label="Read along">
            <ReadAlong passage={passage} tracks={lesson.audio} activeIndex={activeIndex} onActiveIndex={setActiveIndex}
              disabled={closed} />
          </aside>
        )}
      </div>
    </div>
  );
}
