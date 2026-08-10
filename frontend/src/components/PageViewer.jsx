import React, { useEffect, useState } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import { ChevronLeft, ChevronRight, X } from 'lucide-react';
import { getDocument, getDocumentData } from '../api/documents';

pdfjs.GlobalWorkerOptions.workerSrc = new URL('pdfjs-dist/build/pdf.worker.min.mjs', import.meta.url).toString();

const PageViewer = ({ slot, onClose }) => {
  const start = slot?.page_from || 1;
  const end = slot?.page_to || start;
  const offset = slot?.pdf_page_offset || 0;
  const [pdfData, setPdfData] = useState(null);
  const [page, setPage] = useState(start + offset);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!slot?.document_id) return;
    let active = true;
    setPdfData(null);
    setError('');
    setPage(start + offset);
    getDocument(slot.document_id)
      .then((document) => getDocumentData(document.blob_path, document.size_bytes))
      .then((nextData) => { if (active) setPdfData(nextData); })
      .catch((nextError) => { if (active) setError(nextError.message); });
    return () => { active = false; };
  }, [slot?.document_id, start, offset]);

  if (!slot || !slot.document_id) return null;
  const physicalStart = start + offset;
  const physicalEnd = end + offset;
  return (
    <div className="flex flex-col h-full bg-surface">
      <div className="flex items-center justify-between p-4 border-b border-border bg-gray-50 flex-shrink-0">
        <div><h3 className="font-bold text-sm">{slot.subject_name}</h3><p className="text-xs text-text-secondary">Assigned: pages {start}–{end}</p></div>
        <button onClick={onClose} className="p-1.5"><X className="w-4 h-4" /></button>
      </div>
      <div className="flex-1 overflow-auto bg-gray-100 p-3 text-center">
        {error && <p className="text-red-700">{error}</p>}
        {!pdfData && !error && <p className="text-text-secondary">Loading assigned pages…</p>}
        {pdfData && <Document file={{ data: pdfData }} loading="Loading PDF…" onLoadError={(loadError) => setError(loadError.message)}><Page pageNumber={page} renderTextLayer renderAnnotationLayer className="mx-auto shadow" /></Document>}
      </div>
      <div className="border-t p-3 flex justify-between items-center">
        <button disabled={page <= physicalStart} onClick={() => setPage((value) => value - 1)} className="p-2 disabled:opacity-30"><ChevronLeft /></button>
        <span className="text-sm">Book page {page} · assigned {physicalStart}–{physicalEnd}</span>
        <button disabled={page >= physicalEnd} onClick={() => setPage((value) => value + 1)} className="p-2 disabled:opacity-30"><ChevronRight /></button>
      </div>
    </div>
  );
};

export default PageViewer;
