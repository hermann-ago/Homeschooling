import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';
import { ChevronLeft, ChevronRight, X } from 'lucide-react';
import { getDocument, getDocumentData } from '../api/documents';
import AnnotationLayer from './pdfAnnotations/AnnotationLayer';
import AnnotationToolbar from './pdfAnnotations/AnnotationToolbar';
import { usePageAnnotations } from './pdfAnnotations/usePageAnnotations';
import { toPhysicalPage } from './pdfAnnotations/annotationGeometry';


pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url,
).toString();


const PageViewer = ({ slot, childId, onClose }) => {
  const start = slot?.page_from || 1;
  const end = slot?.page_to || start;
  const offset = slot?.pdf_page_offset || 0;
  const physicalStart = toPhysicalPage(start, offset);
  const physicalEnd = toPhysicalPage(end, offset);
  const [pdfData, setPdfData] = useState(null);
  const [documentInfo, setDocumentInfo] = useState(null);
  const [page, setPage] = useState(physicalStart);
  const [pdfError, setPdfError] = useState('');
  const [tool, setTool] = useState('hand');
  const [color, setColor] = useState('#111827');
  const [strokeWidth, setStrokeWidth] = useState(0.005);
  const [zoom, setZoom] = useState(100);
  const [viewportWidth, setViewportWidth] = useState(0);
  const viewportRef = useRef(null);
  const pageSurfaceRef = useRef(null);

  useLayoutEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return undefined;
    let animationFrame = null;
    const updateWidth = () => {
      const nextWidth = Math.max(240, Math.floor(viewport.clientWidth - 24));
      setViewportWidth((currentWidth) => (
        currentWidth === nextWidth ? currentWidth : nextWidth
      ));
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
    setTool('hand');
    getDocument(slot.document_id)
      .then(async (nextDocument) => {
        const nextData = await getDocumentData(nextDocument.blob_path, nextDocument.size_bytes);
        if (active) {
          setDocumentInfo(nextDocument);
          setPdfData(nextData);
        }
      })
      .catch((nextError) => {
        if (active) setPdfError(nextError.message);
      });
    return () => { active = false; };
  }, [physicalStart, slot?.document_id]);

  const annotation = usePageAnnotations({
    childId,
    documentId: slot?.document_id,
    pageNumber: page,
    enabled: Boolean(childId && slot?.document_id && pdfData),
  });

  const pdfFile = useMemo(
    () => (pdfData ? { data: pdfData.slice() } : null),
    [pdfData],
  );
  const renderWidth = Math.max(240, Math.round(viewportWidth * (zoom / 100)));
  const boundedEnd = documentInfo
    ? Math.min(physicalEnd, documentInfo.page_count)
    : physicalEnd;

  if (!slot || !slot.document_id) return null;

  const changePage = async (nextPage) => {
    await annotation.flush();
    setPage(nextPage);
    viewportRef.current?.scrollTo({ top: 0, left: 0 });
  };

  const closeViewer = async () => {
    await annotation.flush();
    onClose?.();
  };

  const clearPage = () => {
    if (window.confirm('Clear all handwriting from this PDF page? You can undo this while the viewer stays open.')) {
      annotation.clear();
    }
  };

  const bookPage = page - offset;

  return (
    <div className="flex flex-col h-full bg-surface min-h-0">
      <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-gray-50 flex-shrink-0 gap-3">
        <div className="min-w-0">
          <h3 className="font-bold text-sm truncate">{slot.subject_name}</h3>
          <p className="text-xs text-text-secondary truncate">{slot.topic_title || `Assigned pages ${start}-${end}`}</p>
        </div>
        <button type="button" aria-label="Close PDF viewer" onClick={closeViewer} className="w-11 h-11 rounded-xl flex items-center justify-center hover:bg-gray-200 flex-shrink-0">
          <X className="w-5 h-5" />
        </button>
      </div>

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

      <div
        ref={viewportRef}
        data-testid="pdf-page-viewport"
        className="flex-1 overflow-x-auto overflow-y-scroll bg-gray-100 p-3 text-center min-h-0"
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
              <div ref={pageSurfaceRef} className="relative inline-block shadow-lg bg-white leading-none">
                <Page
                  pageNumber={page}
                  width={renderWidth}
                  renderTextLayer
                  renderAnnotationLayer
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

      <div className="border-t px-3 py-2 flex justify-between items-center gap-2 flex-shrink-0 bg-white">
        <button type="button" aria-label="Previous assigned page" disabled={page <= physicalStart} onClick={() => changePage(page - 1)} className="w-11 h-11 rounded-xl flex items-center justify-center hover:bg-gray-100 disabled:opacity-30"><ChevronLeft /></button>
        <div className="text-center min-w-0">
          <p className="text-sm font-semibold">Book page {bookPage}</p>
          <p className="text-[10px] text-text-secondary">Assigned {start}-{end}{offset ? ` · PDF page ${page}` : ''}</p>
        </div>
        <button type="button" aria-label="Next assigned page" disabled={page >= boundedEnd} onClick={() => changePage(page + 1)} className="w-11 h-11 rounded-xl flex items-center justify-center hover:bg-gray-100 disabled:opacity-30"><ChevronRight /></button>
      </div>
    </div>
  );
};


export default PageViewer;
