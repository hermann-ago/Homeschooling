import { useEffect, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { subjectsApi } from '../api/subjects';
import { libraryApi } from '../api/library';
import { Button, SegmentedControl, useToast } from '../ui';

function inline(text) {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*)/g).map((part, i) => part.startsWith('**')
    ? <strong key={i}>{part.slice(2, -2)}</strong>
    : part.startsWith('`') ? <code key={i} className="rounded bg-paper-deep px-1 text-[13px]">{part.slice(1, -1)}</code>
    : part.startsWith('*') ? <em key={i}>{part.slice(1, -1)}</em> : part);
}

/** Plain React text rendering deliberately keeps raw HTML out of instruction previews. */
export function MarkdownPreview({ content }) {
  const body = content.replace(/^---\r?\n[\s\S]*?\r?\n---\r?\n/, '');
  const blocks = [];
  let current = null;
  let code = false;
  const flush = () => { if (current) blocks.push(current); current = null; };
  body.split(/\r?\n/).forEach((line) => {
    if (/^\s*```/.test(line)) {
      if (code) { flush(); code = false; }
      else { flush(); current = { type: 'code', lines: [] }; code = true; }
      return;
    }
    if (code) { current.lines.push(line); return; }
    if (!line.trim()) { flush(); return; }
    const heading = /^(#{1,6})\s+(.+)$/.exec(line);
    if (heading) { flush(); blocks.push({ type: 'heading', level: heading[1].length, text: heading[2] }); return; }
    const list = /^\s*(?:([-*])|\d+\.)\s+(.+)$/.exec(line);
    const type = list ? list[1] ? 'ul' : 'ol' : 'paragraph';
    if (current?.type !== type) { flush(); current = { type, lines: [] }; }
    current.lines.push(list ? list[2] : line);
  });
  flush();
  return <div className="flex flex-col gap-4 text-[15px] leading-relaxed text-ink">
    {blocks.map((block, i) => {
      if (block.type === 'heading') {
        const Tag = `h${block.level}`;
        return <Tag key={i} className={block.level === 1 ? 'font-display text-2xl font-semibold' : 'text-base font-bold mt-2'}>{inline(block.text)}</Tag>;
      }
      if (block.type === 'ul' || block.type === 'ol') {
        const Tag = block.type;
        return <Tag key={i} className={`${block.type === 'ol' ? 'list-decimal' : 'list-disc'} pl-5 flex flex-col gap-1.5`}>{block.lines.map((line, n) => <li key={n}>{inline(line)}</li>)}</Tag>;
      }
      if (block.type === 'code') return <pre key={i} className="rounded-xl bg-paper-deep p-4 overflow-x-auto text-sm"><code>{block.lines.join('\n')}</code></pre>;
      return <p key={i} className="whitespace-pre-line">{inline(block.lines.join('\n'))}</p>;
    })}
  </div>;
}

export default function TeachingSkillEditor({ subject, libraryBook }) {
  const client = useQueryClient();
  const toast = useToast();
  const api = libraryBook ? libraryApi : subjectsApi;
  const id = libraryBook || subject.id;
  const key = [libraryBook ? 'library-teaching-skill' : 'teaching-skill', id];
  const { data, isLoading, error } = useQuery({ queryKey: key, queryFn: () => api.teachingSkill(id) });
  const { data: history = [] } = useQuery({ queryKey: [...key, 'history'], queryFn: () => api.skillHistory(id) });
  const [content, setContent] = useState('');
  const [baseline, setBaseline] = useState(null);
  const [mode, setMode] = useState('edit');
  const [pastVersion, setPastVersion] = useState('');
  const [saving, setSaving] = useState(false);
  const [problem, setProblem] = useState('');
  useEffect(() => {
    if (data && (!baseline || baseline.subjectId !== subject.id || content === baseline.content)) {
      setContent(data.content);
      setBaseline({ ...data, subjectId: subject.id });
    }
  }, [data, subject.id]);
  const past = history.find((r) => String(r.version) === pastVersion);
  const save = async (text = content) => {
    setSaving(true);
    setProblem('');
    try {
      const saved = await api.saveSkill(id, text, baseline?.version ?? data.version);
      setContent(saved.content);
      setBaseline({ ...saved, subjectId: subject.id });
      client.setQueryData(key, saved);
      await client.invalidateQueries({ queryKey: [...key, 'history'] });
      if (libraryBook) await client.invalidateQueries({ queryKey: ['teaching-skill'] });
      setPastVersion('');
      toast(libraryBook ? 'Shared book instructions saved for every reader. Existing sessions keep their saved version.' : 'Teaching skill saved. New guided lessons will use these instructions.');
    } catch (e) {
      setProblem(e.message);
    } finally { setSaving(false); }
  };
  const exportFile = async () => {
    try {
      const saved = await api.exportSkill(id);
      client.setQueryData(key, saved);
      toast('Markdown exported to this subject’s Teaching Skill folder.');
    } catch (e) { setProblem(e.message); }
  };
  const reload = async () => {
    try {
      const saved = await api.teachingSkill(id);
      setContent(saved.content);
      setBaseline({ ...saved, subjectId: subject.id });
      client.setQueryData(key, saved);
      setProblem('');
    } catch (e) { setProblem(e.message); }
  };
  if (isLoading) return <p className="text-muted">Opening teaching instructions…</p>;
  if (error) return <p role="alert" className="text-problem">{error.message}</p>;
  if (!data) return null;
  return <section className="rounded-2xl border border-line bg-surface overflow-hidden">
    <div className="p-5 border-b border-line flex flex-wrap gap-4 items-start justify-between">
      <div className="flex flex-col gap-1.5 max-w-2xl">
        <h2 className="text-lg font-bold">How to teach {subject.name}</h2>
        <p className="text-sm text-muted leading-relaxed">{libraryBook ? 'Shared instructions for this book, for every child now and in the future. Prepared lessons contain reusable explanations and quiz questions; live conversation adapts to each child separately.' : 'These instructions shape the guided reading, student activities, and AI feedback. This subject has its own copy, so you can adapt it for this learner.'}</p>
        <span className="text-xs text-muted">Version {baseline?.version || data.version || 'starter'} · {content !== baseline?.content ? 'Unsaved changes' : 'Saved instructions'}</span>
        {baseline && baseline.version !== data.version && <p className="text-xs text-attention">The saved instructions changed elsewhere. Your draft is kept; saving will check its original version.</p>}
      </div>
      <Button variant="primary" disabled={saving || !content.trim() || content === baseline?.content} onClick={() => save()}>{saving ? 'Saving…' : 'Save'}</Button>
    </div>
    <div className="p-4 border-b border-line flex flex-wrap gap-3 items-center justify-between">
      <SegmentedControl label="Teaching skill view" value={mode} onChange={setMode}
        options={[{ value: 'edit', label: 'Edit instructions' }, { value: 'preview', label: 'Formatted preview' }]} />
      <label className="text-sm text-muted flex items-center gap-2">Previous versions
        <select aria-label="Previous skill versions" value={pastVersion} onChange={(e) => setPastVersion(e.target.value)} className="rounded-lg border border-line bg-surface p-2 text-ink">
          <option value="">Current</option>
          {history.filter((r) => r.version !== data.version).map((r) => <option key={r.id} value={r.version}>Version {r.version}</option>)}
        </select>
      </label>
    </div>
    {problem && <p role="alert" className="px-5 py-3 text-sm text-problem">{problem} <button className="underline" onClick={reload}>Reload saved version</button></p>}
    {past ? <div className="p-6 flex flex-col gap-5">
      <div className="flex gap-4 items-center justify-between"><span className="text-sm text-muted">Viewing version {past.version}. Restoring creates a new version and keeps the history.</span>
        <Button disabled={saving} onClick={() => save(past.content)}>Restore this version</Button></div>
      <MarkdownPreview content={past.content} />
    </div> : mode === 'edit' ? <div className="p-5">
      <label className="sr-only" htmlFor={`skill-${subject.id}`}>Teaching instructions for {subject.name}</label>
      <textarea id={`skill-${subject.id}`} value={content} onChange={(e) => setContent(e.target.value)} maxLength={30000}
        className="w-full min-h-[520px] rounded-xl border border-line bg-paper/50 p-5 text-[15px] leading-7 resize-y focus-visible:outline-action" spellCheck />
      <p className="mt-2 text-xs text-muted">Use # headings, short paragraphs, and lists. {content.length.toLocaleString()} / 30,000 characters.</p>
    </div> : <div className="p-6 min-h-[520px]"><MarkdownPreview content={content} /></div>}
    <div className="px-5 py-4 bg-paper/50 border-t border-line text-xs text-muted flex flex-wrap gap-3 items-center justify-between">
      <span>{data.file_path ? `Markdown copy: ${data.file_path.split('/').join(' › ')}` : 'The database keeps these instructions. Export a Markdown copy when the Drive folder is available.'}</span>
      {!data.file_path && data.version > 0 && <Button size="sm" onClick={exportFile}>Export Markdown</Button>}
    </div>
  </section>;
}
