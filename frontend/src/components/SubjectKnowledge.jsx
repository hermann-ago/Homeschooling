import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { booksApi } from '../api/books';
import { Button, Dialog } from '../ui';

export default function SubjectKnowledge({ subject, collection }) {
  const client = useQueryClient();
  const [choosing, setChoosing] = useState(false);
  const [selected, setSelected] = useState('');
  const [busy, setBusy] = useState(false);
  const [file, setFile] = useState(null);
  const [problem, setProblem] = useState('');
  const { data, error } = useQuery({ queryKey: ['subject-knowledge-library'], queryFn: booksApi.knowledgeLibrary, enabled: choosing });
  const options = (data?.collections || []).filter((c) => c.source_subject_id !== subject.id && c.collection_id !== collection.id);
  const save = async () => {
    setBusy(true); setProblem('');
    try { setFile(await booksApi.saveKnowledge(subject.id)); }
    catch (e) { setProblem(e.message); }
    finally { setBusy(false); }
  };
  const reuse = async () => {
    setBusy(true); setProblem('');
    try {
      const result = await booksApi.reuseKnowledge(subject.id, { source_subject_id: Number(selected), expected_revision: collection.revision, expected_version_id: collection.version_id });
      setFile(result.knowledge_file);
      await client.invalidateQueries({ queryKey: ['subject-collection', subject.id] });
      await client.invalidateQueries({ queryKey: ['subject-analysis', subject.id] });
      setChoosing(false);
    } catch (e) { setProblem(e.message); }
    finally { setBusy(false); }
  };
  return <div className="border-t border-line-soft pt-3 flex flex-col gap-2 text-sm">
    <h4 className="font-semibold">Reusable subject knowledge</h4>
    <p className="text-muted">Completed analysis is saved as a standard file in this subject’s Subject Knowledge folder. Another child can use the same books and source map; their lessons and learning records stay personal.</p>
    {collection.shared && <p className="text-muted">This family collection is shared. Source corrections apply to its books for everyone. Editing the book list creates a separate collection.</p>}
    <div className="flex flex-wrap gap-2">
      <Button size="sm" disabled={busy || !(collection.knowledge_available ?? ['ready', 'needs_review'].includes(collection.analysis_status))} onClick={save}>Save knowledge file</Button>
      <Button size="sm" disabled={busy} onClick={() => { setProblem(''); setChoosing(true); }}>Use saved subject knowledge</Button>
    </div>
    {file && <p role="status" className="text-action break-words">Saved · {file.path} · no AI charge</p>}
    {!choosing && problem && <p role="alert" className="text-problem">{problem}</p>}
    {choosing && <Dialog open title="Use saved subject knowledge" onClose={busy ? undefined : () => setChoosing(false)}
      description="Choose an already analyzed family collection. This assigns its books and source knowledge without copying another child’s lessons, answers or progress, and without a new AI analysis."
      footer={<><Button disabled={busy} onClick={() => setChoosing(false)}>Cancel</Button><Button variant="primary" disabled={busy || !selected} onClick={reuse}>{busy ? 'Saving…' : 'Use this collection'}</Button></>}>
      <label className="flex flex-col gap-2 text-sm font-semibold">Saved collection
        <select aria-label="Saved knowledge collection" value={selected} disabled={busy} onChange={(e) => setSelected(e.target.value)} className="rounded-lg border border-line p-2 bg-surface">
          <option value="">Choose subject knowledge</option>
          {options.map((c) => <option key={c.source_subject_id} value={c.source_subject_id}>{c.subject} · {c.grade || 'Any grade'} · {c.collection_name} · {c.coverage.books} books</option>)}
        </select>
      </label>
      {data && !options.length && <p className="text-sm text-muted mt-3">No other completed collections are available yet.</p>}
      <p className="text-sm text-muted mt-3">Book editions are checked against their saved file fingerprints. Existing learner work stays in place. Assign reading topics separately and prepare this child’s guide when they need it.</p>
      {(problem || error) && <p role="alert" className="text-sm text-problem mt-3">{problem || error.message}</p>}
    </Dialog>}
  </div>;
}
