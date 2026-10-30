import { useEffect, useRef, useState } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import { request } from '../api/client';
import { Button, Dialog } from '../ui';

pdfjs.GlobalWorkerOptions.workerSrc = new URL('pdfjs-dist/build/pdf.worker.min.mjs', import.meta.url).toString();

/** The checked, single-page endpoint has no annotations or learner mutations. */
export default function OriginalSourcePage({ map, session, companionSubject, document, page, onClose }) {
  const [file, setFile] = useState(null);
  const [url, setUrl] = useState('');
  const [problem, setProblem] = useState('');
  const [width, setWidth] = useState(640);
  const box = useRef(null);
  useEffect(() => {
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(1, Math.min(800, Math.floor(entry.contentRect.width)))));
    observer.observe(box.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    let active = true; let blobUrl;
    const endpoint = companionSubject ? `/subjects/${companionSubject}/book-companions/${document}/source-pdf/${page}`
      : session ? `/tutor/sessions/${encodeURIComponent(session)}/activity-source/${document}/${page}`
      : `/subject-maps/${map.id}/source-pdf/${document}/${page}`;
    request(endpoint).then(async (response) => {
      if (!response.ok) throw new Error('This original page is unavailable. Use the saved excerpt and check the source edition.');
      const blob = await response.blob();
      const data = new Uint8Array(await blob.arrayBuffer());
      if (active) { blobUrl = URL.createObjectURL(blob); setUrl(blobUrl); setFile({ data }); }
    }).catch((e) => { if (active) setProblem(e.message); });
    return () => { active = false; if (blobUrl) URL.revokeObjectURL(blobUrl); };
  }, [map?.id, session, companionSubject, document, page]);
  return <Dialog open title={`Original PDF page ${page}`} width={950} onClose={onClose} footer={<Button onClick={onClose}>{companionSubject ? 'Back to book JSON' : 'Back to reading'}</Button>}>
    <div ref={box} className="w-full min-w-0">
      {problem && <p role="alert">{problem}</p>}
      {!file && !problem && <p role="status">Loading original page…</p>}
      {file && <Document file={file} onLoadError={() => setProblem('The PDF could not be displayed. You can download this checked page below.')} loading={<p role="status">Opening original PDF…</p>}>
        <Page pageNumber={1} width={width} renderTextLayer={false} renderAnnotationLayer={false}
          loading={<p role="status">Rendering original page…</p>} onRenderError={() => setProblem('The PDF could not be rendered. You can download this checked page below.')} />
      </Document>}
      {url && <a href={url} download={`original-page-${page}.pdf`} className="text-action underline mt-3 inline-block">Download original PDF page {page}</a>}
    </div>
  </Dialog>;
}
