import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';
import { ChevronLeft, ChevronRight, Printer } from 'lucide-react';
import { getDocument, getDocumentPages } from '../api/documents';
import AnnotationLayer from './pdfAnnotations/AnnotationLayer';
import AnnotationToolbar from './pdfAnnotations/AnnotationToolbar';
import { usePageAnnotations } from './pdfAnnotations/usePageAnnotations';
import { toPhysicalPage } from './pdfAnnotations/annotationGeometry';
import { followScroll, highlightItemIndices, sentenceForItem } from '../utils/readAlong';
import { useConfirm } from '../ui/useFeedback';
import { printLessonPages } from '../utils/printLessonPages';
import { pauseNarration } from '../utils/narration';
import LessonPrintDialog from './LessonPrintDialog';


pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url,
).toString();


function escapeHtml(text) {
  return text.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}


/**
 * The book pages of a lesson with handwriting, used by the Lesson screen
 * (which shows the subject and title in its own header).
 */
const PageViewer = ({ slot, childId, highlightSentence = null, highlightAfter = null, requestedPage = null, boundaryNote = null, readableSentences = null, onReadFrom = null }) => {
  const start = slot?.page_from || 1;
  const end = slot?.page_to || start;
  const offset = slot?.pdf_page_offset || 0;
  const physicalStart = toPhysicalPage(start, offset);
  const physicalEnd = toPhysicalPage(end, offset);
  const [pdfData, setPdfData] = useState(null);
  const [documentInfo, setDocumentInfo] = useState(null);
  const [page, setPage] = useState(physicalStart);
  const [pdfError, setPdfError] = useState('');
  const [printing, setPrinting] = useState(false);
  const [printStatus, setPrintStatus] = useState('');
  const [printOptionsOpen, setPrintOptionsOpen] = useState(false);
  const [savedPrintOptions, setSavedPrintOptions] = useState(null);
  const [tool, setTool] = useState('hand');
  const [color, setColor] = useState('#111827');
  const [strokeWidth, setStrokeWidth] = useState(0.005);
  const [zoom, setZoom] = useState(100);
  const [viewportWidth, setViewportWidth] = useState(0);
  const [viewportHeight, setViewportHeight] = useState(0);
  const [pageRatio, setPageRatio] = useState(null);
  // Phones read a page at its full width; a whole page there is too small to read.
const initialFit = () => (typeof window !== 'undefined' && window.innerWidth < 640 ? 'width' : 'page');
  const [fit, setFit] = useState(initialFit);
  const [textItems, setTextItems] = useState([]);
  const viewportRef = useRef(null);
  const pageSurfaceRef = useRef(null);
  const touchedAt = useRef(0);
  const followed = useRef('');

  useLayoutEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return undefined;
    let animationFrame = null;
    const updateWidth = () => {
      const nextWidth = Math.max(240, Math.floor(viewport.clientWidth - 24));
      setViewportWidth((currentWidth) => (
        currentWidth === nextWidth ? currentWidth : nextWidth
      ));
      setViewportHeight(Math.max(0, viewport.clientHeight - 24));
    };
    const measure = () => {
      if (animationFrame !== null) cancelAnimationFrame(animationFrame);
      animationFrame = requestAnimationFrame(updateWidth);
    };
    updateWidth();
    const observer = new ResizeObserver(measure);
    observer.observe(viewport);
    return () => {
      observer.disconnect();
      if (animationFrame !== null) cancelAnimationFrame(animationFrame);
    };
  }, []);

  useEffect(() => {
    if (!slot?.document_id) return undefined;
    let active = true;
    setPdfData(null);
    setDocumentInfo(null);
    setPdfError('');
    setPage(physicalStart);
    setZoom(100);
    setPageRatio(null);
    setFit('page');
    setTool('hand');
    getDocument(slot.document_id)
      .then(async (nextDocument) => {
        const last = Math.min(physicalEnd, nextDocument.page_count || physicalEnd);
        const nextData = await getDocumentPages(nextDocument.id, physicalStart, last);
        if (active) {
          setDocumentInfo(nextDocument);
          setPdfData(nextData);
        }
      })
      .catch((nextError) => {
        if (active) setPdfError(nextError.message);
      });
    return () => { active = false; };
  }, [physicalStart, physicalEnd, slot?.document_id]);

  const annotation = usePageAnnotations({
    childId,
    documentId: slot?.document_id,
    pageNumber: page,
    enabled: Boolean(childId && slot?.document_id && pdfData),
  });
  const confirm = useConfirm();

  // Save handwriting at once when the viewer goes away (Back, or other pages shown).
  const flushRef = useRef(annotation.flush);
  useEffect(() => { flushRef.current = annotation.flush; });
  useEffect(() => () => { flushRef.current(); }, []);

  const highlighted = useMemo(
    () => highlightItemIndices(textItems, highlightSentence, highlightAfter),
    [textItems, highlightSentence, highlightAfter],
  );
  // A lesson reading can be heard again from any of its lines: each piece of text carries its index.
  const readable = Boolean(onReadFrom && readableSentences?.length);
  const renderText = useMemo(() => {
    if (!highlighted.size && !readable) return undefined;
    return ({ str, itemIndex }) => {
      const text = highlighted.has(itemIndex) ? `<mark class="readalong-mark">${escapeHtml(str)}</mark>` : escapeHtml(str);
      return readable ? `<span data-readable-item="${itemIndex}">${text}</span>` : text;
    };
  }, [highlighted, readable]);
  const readFromTap = (event) => {
    const item = event.target.closest?.('[data-readable-item]');
    if (!item || !readable || window.getSelection?.()?.toString()) return; // a drag selects text instead
    const key = sentenceForItem(textItems, Number(item.dataset.readableItem), readableSentences);
    if (key !== null) onReadFrom(key);
  };

  useEffect(() => {
    if (!requestedPage || requestedPage === page || !pdfData) return;
    if (requestedPage < physicalStart || requestedPage > physicalEnd) return;
    annotation.flush().then(() => setPage(requestedPage));
    // Also once the pages have loaded: a sentence spoken before that still turns the page.
  }, [requestedPage, pdfData]);

  const pdfFile = useMemo(
    () => (pdfData ? { data: pdfData.slice() } : null),
    [pdfData],
  );
  const fittedWidth = fit === 'page' && pageRatio && viewportHeight > 0 ? Math.min(viewportWidth, viewportHeight * pageRatio) : viewportWidth;
  const renderWidth = Math.max(160, Math.round(fittedWidth * (zoom / 100)));
  const boundedEnd = documentInfo
    ? Math.min(physicalEnd, documentInfo.page_count)
    : physicalEnd;

  // Keep the sentence being read in view when the page is zoomed past the
  // screen. The text layer draws its marks after rendering, so wait for them.
  // A child who moves the page by hand keeps it for a few seconds.
  useEffect(() => {
    const viewport = viewportRef.current;
    const surface = pageSurfaceRef.current;
    if (!viewport || !surface || !highlighted.size) return undefined;
    const key = `${page}|${renderWidth}|${highlightSentence}`;
    let frame = 0;
    const follow = () => {
      frame = 0;
      if (followed.current === key || Date.now() - touchedAt.current < 4000) return;
      const marks = [...surface.querySelectorAll('mark.readalong-mark')].map((mark) => mark.getBoundingClientRect()).filter((rect) => rect.width || rect.height);
      if (!marks.length) return;
      followed.current = key;
      const box = { top: Math.min(...marks.map((r) => r.top)), bottom: Math.max(...marks.map((r) => r.bottom)),
        left: Math.min(...marks.map((r) => r.left)), right: Math.max(...marks.map((r) => r.right)) };
      const target = followScroll(viewport.getBoundingClientRect(), box, { top: viewport.scrollTop, left: viewport.scrollLeft });
      if (target) viewport.scrollTo?.({ ...target, behavior: 'smooth' });
    };
    const schedule = () => { if (!frame) frame = window.requestAnimationFrame(follow); };
    const observer = new MutationObserver(schedule);
    observer.observe(surface, { childList: true, subtree: true });
    schedule();
    return () => { observer.disconnect(); if (frame) window.cancelAnimationFrame(frame); };
  }, [highlighted, page, renderWidth, highlightSentence]);
  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return undefined;
    const touched = () => { touchedAt.current = Date.now(); };
    const events = ['pointerdown', 'wheel', 'touchstart', 'keydown'];
    events.forEach((name) => viewport.addEventListener(name, touched, { passive: true }));
    return () => events.forEach((name) => viewport.removeEventListener(name, touched));
  }, []);

  if (!slot || !slot.document_id) return null;

  const changePage = async (nextPage) => {
    await annotation.flush();
    setPage(nextPage);
    viewportRef.current?.scrollTo({ top: 0, left: 0 });
  };

  const clearPage = async () => {
    if (await confirm({
      title: 'Clear the handwriting on this page?',
      description: 'You can undo this while the lesson stays open.',
      confirmLabel: 'Clear page', danger: true,
    })) {
      annotation.clear();
    }
  };

  const bookPage = page - offset;
  const printRange = `${slot.document_id}.${physicalStart}.${boundedEnd}`;
  const printPages = async (options) => {
    pauseNarration();
    setSavedPrintOptions({ range: printRange, options });
    setPrinting(true); setPrintStatus('Preparing lesson pages for printing…');
    try {
      await printLessonPages({ data: pdfData, first: physicalStart, last: boundedEnd,
        offset, base: physicalStart, ...options,
        title: `${slot.topic_title || documentInfo?.original_filename || 'Lesson'} · book pages ${start}–${boundedEnd - offset}`,
        onProgress: ({ done, total }) => setPrintStatus(`Preparing print page ${done} of ${total}…`),
        onReady: () => { setPrintOptionsOpen(false); setPrintStatus('Selected pages are ready. Choose your printer, copies and colour in the print dialog.'); } });
    } catch (error) { setPrintStatus(error.message); }
    finally { setPrinting(false); }
  };

  return (
    <div className="pdf-reader relative flex flex-col h-full bg-surface min-h-0">
      {printOptionsOpen && <LessonPrintDialog key={printRange} first={physicalStart} last={boundedEnd} offset={offset} initialOptions={savedPrintOptions?.range === printRange ? savedPrintOptions.options : undefined} busy={printing} onClose={() => setPrintOptionsOpen(false)} onPrint={printPages} />}
      {boundaryNote && (
        <div className="px-4 py-2 bg-action-soft border-b border-line text-[13px] text-action" data-testid="boundary-note">{boundaryNote}</div>
      )}
      {printStatus && <div role="status" className="absolute top-14 right-4 z-20 max-w-sm rounded-xl border border-line bg-white p-3 shadow-sm text-sm text-action flex items-start gap-3"><span>{printStatus}</span>{!printing && <button type="button" aria-label="Dismiss print message" onClick={() => setPrintStatus('')}>×</button>}</div>}

      {annotation.conflict && (
        <div className="px-3 py-2 bg-amber-50 border-b border-amber-200 text-xs text-amber-900 flex flex-wrap items-center gap-2">
          <span className="font-semibold flex-1 min-w-48">This page changed on another device. Your local handwriting is still safe.</span>
          <button type="button" onClick={annotation.reloadConflict} className="px-3 py-2 rounded-lg bg-white border border-amber-300 font-semibold">Reload saved</button>
          <button type="button" onClick={annotation.keepMine} className="px-3 py-2 rounded-lg bg-amber-600 text-white font-semibold">Keep mine</button>
        </div>
      )}

      {annotation.error && !annotation.conflict && (
        <div className="px-3 py-2 bg-red-50 border-b border-red-200 text-xs text-red-700 flex items-center gap-2">
          <span className="flex-1">{annotation.error}. Your drawing remains on this device.</span>
          <button type="button" onClick={annotation.retry} className="px-3 py-2 rounded-lg bg-white border border-red-200 font-semibold">Retry</button>
        </div>
      )}

      <div className="flex flex-1 min-h-0 flex-col lg:flex-row">
        {childId && (
          <AnnotationToolbar
            tool={tool}
            setTool={setTool}
            color={color}
            setColor={setColor}
            strokeWidth={strokeWidth}
            setStrokeWidth={setStrokeWidth}
            zoom={zoom}
            setZoom={setZoom}
            saveStatus={annotation.saveStatus}
            canUndo={annotation.canUndo}
            canRedo={annotation.canRedo}
            hasStrokes={annotation.strokes.length > 0}
            onUndo={annotation.undo}
            onRedo={annotation.redo}
            onClear={clearPage}
            onRetry={annotation.retry}
          />
        )}

        <div className="pdf-reading-area relative flex-1 min-h-0 min-w-0 flex">
        <nav aria-label="Book page controls" className="pdf-page-controls">
          <button type="button" aria-label="Previous assigned page" disabled={page <= physicalStart} onClick={() => changePage(page - 1)}><ChevronLeft size={18} /></button>
          <span className="text-xs font-semibold whitespace-nowrap" title={`Assigned ${start}–${end}${offset ? ` · PDF page ${page}` : ''}`}>Book page {bookPage}</span>
          <button type="button" aria-label="Next assigned page" disabled={page >= boundedEnd} onClick={() => changePage(page + 1)}><ChevronRight size={18} /></button>
          <button type="button" aria-pressed={fit === 'page' && zoom === 100} onClick={() => { setFit('page'); setZoom(100); }}>Fit page</button>
          <button type="button" aria-pressed={fit === 'width' && zoom === 100} onClick={() => { setFit('width'); setZoom(100); }}>Fit width</button>
          <button type="button" aria-label="Print lesson pages" title={`Print book pages ${start}–${boundedEnd - offset}`} disabled={!pdfData || printing || Boolean(pdfError)} onClick={() => { pauseNarration(); setPrintOptionsOpen(true); }}><Printer size={17} /></button>
        </nav>
        <div
          ref={viewportRef}
          data-testid="pdf-page-viewport"
          className="flex-1 overflow-auto bg-paper-deep/60 p-3 text-center min-h-0 min-w-0"
          style={{ scrollbarGutter: 'stable' }}
        >
        {pdfError && <p className="text-red-700 p-4">{pdfError}</p>}
        {!pdfData && !pdfError && <p className="text-text-secondary p-4">Loading assigned pages...</p>}
        {pdfFile && viewportWidth > 0 && (
          <Document
            file={pdfFile}
            loading="Loading PDF..."
            onLoadError={(loadError) => setPdfError(loadError.message)}
          >
            <div className="min-w-max flex justify-center">
              <div ref={pageSurfaceRef} className="relative inline-block shadow-lg bg-white leading-none" data-readable={readable || undefined} onClick={readFromTap}>
                <Page
                  // The loaded PDF holds only the assigned pages, starting at physicalStart.
                  pageNumber={page - physicalStart + 1}
                  width={renderWidth}
                  onLoadSuccess={(loadedPage) => {
                    const bounds = loadedPage.getViewport({ scale: 1 });
                    setPageRatio(bounds.width / bounds.height);
                  }}
                  renderTextLayer
                  renderAnnotationLayer
                  customTextRenderer={renderText}
                  onGetTextSuccess={({ items }) => setTextItems(items)}
                  loading={<div className="bg-white p-8 text-sm text-text-secondary">Rendering page...</div>}
                />
                {childId && (
                  <AnnotationLayer
                    surfaceRef={pageSurfaceRef}
                    strokes={annotation.strokes}
                    tool={tool}
                    color={color}
                    strokeWidth={strokeWidth}
                    disabled={annotation.loading}
                    onAddStroke={annotation.addStroke}
                    onEraseStrokes={annotation.eraseStrokes}
                  />
                )}
              </div>
            </div>
          </Document>
        )}
        </div>
        </div>
      </div>
    </div>
  );
};


export default PageViewer;
