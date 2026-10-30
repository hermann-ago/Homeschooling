import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Download } from 'lucide-react';
import ScreenHeader from '../app/ScreenHeader';
import { useLearner } from '../app/learnerContext';
import { fetchApi } from '../api/client';
import { modeHref } from '../api/mode';
import { learningLabel } from '../utils/learningLabels';
import { Button, Dialog } from '../ui';

const VIEWS = [['answers', 'Answers and help'], ['lessons', 'Lessons'], ['reviews', 'Topics to revisit'],
  ['pending', 'Unfinished work'], ['reading', 'Reading and understanding'], ['exercises', 'Book exercises'], ['preparation', 'Book preparation']];
const inputStyle = 'block w-full mt-1 rounded-lg border border-line bg-surface px-3 py-2 text-sm font-normal';
const valueText = (value) => value == null || value === '' ? '—' : Array.isArray(value)
  ? value.map(valueText).join('\n\n') : typeof value === 'object'
    ? Object.entries(value).map(([key, text]) => `${key.replaceAll('_', ' ')}: ${valueText(text)}`).join('\n')
    : typeof value === 'boolean' ? value ? 'Yes' : 'No' : String(value);

function recordsQuery(filters) {
  return new URLSearchParams(Object.entries(filters).filter(([, value]) => value !== '' && value != null)).toString();
}

const columnText = (key, value) => ['status', 'independence'].includes(key) && typeof value === 'string' ? learningLabel(value) : valueText(value);

function RecordDetails({ record, columns, onClose }) {
  return <Dialog open onClose={onClose} title={`${record.child} · ${record.subject}`} description={record.topic || 'Saved learning record'} width={760}>
    <div className="max-h-[65vh] overflow-y-auto pb-3">
      {record.lesson_path && <Button as="a" href={modeHref(record.lesson_path)} size="sm" className="mb-4">Open full lesson thread</Button>}
      <dl className="grid gap-4 text-sm">
        {[...columns.map((c) => [c.label, columnText(c.key, record[c.key])]), ...Object.entries(record.details || {}).filter(([key]) => !['evidence', 'conversation'].includes(key)), ['Record ID', record.id]].map(([label, value]) =>
          <div key={label}><dt className="font-semibold text-muted">{label}</dt><dd className="mt-1 whitespace-pre-wrap break-words">{valueText(value)}</dd></div>)}
      </dl>
      {record.details?.conversation?.length > 0 && <section className="mt-5 flex flex-col gap-3"><h3 className="text-sm font-semibold">Saved conversation</h3>
        {record.details.conversation.map((message, index) => <div key={index} className="rounded-xl bg-paper p-3 text-sm"><p className="font-semibold">{message.role === 'student' ? record.child : 'Tutor'} · {learningLabel(message.status)}</p><p className="mt-1 whitespace-pre-wrap break-words">{message.text}</p></div>)}
      </section>}
      {record.details?.evidence?.length > 0 && <div className="mt-5 flex flex-col gap-2"><h3 className="text-sm font-semibold">Saved student work</h3>
        {record.details.evidence.map((e) => <a key={e.id} href={modeHref(`/api/student-work/${encodeURIComponent(e.id)}`)} target="_blank" rel="noreferrer" className="text-action underline text-sm">{e.filename || 'Open saved work'}</a>)}
      </div>}
    </div>
  </Dialog>;
}

function RecordsTable({ child }) {
  const [filters, setFilters] = useState({ view: 'answers', subject_id: '', date_from: '', date_to: '', q: '', status: '', sort: 'date', order: 'desc' });
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [opened, setOpened] = useState(null);
  const { data: options } = useQuery({ queryKey: ['records-options'], queryFn: () => fetchApi('/records/options') });
  const query = recordsQuery({ ...filters, child_id: child === 'all' ? '' : child });
  const { data, error, isLoading, isFetching, refetch } = useQuery({ queryKey: ['records', query, page],
    queryFn: () => fetchApi(`/records?${query}&page=${page}&limit=25`) });
  const change = (name, value) => {
    setFilters((current) => ({ ...current, [name]: value, ...(name === 'view' ? { status: '', sort: 'date', order: 'desc' } : {}) }));
    setPage(1); setOpened(null);
  };
  const sortBy = (key) => {
    setFilters((current) => ({ ...current, sort: key, order: current.sort === key && current.order === 'asc' ? 'desc' : 'asc' }));
    setPage(1);
  };
  const pages = Math.max(1, Math.ceil((data?.total || 0) / 25));
  const subjects = options?.subjects?.filter((s) => child === 'all' || s.child_id === child) || [];
  return <>
    <form className="grid sm:grid-cols-2 xl:grid-cols-4 gap-4 rounded-2xl border border-line bg-surface p-5"
      onSubmit={(event) => { event.preventDefault(); change('q', search); }}>
      <label className="text-sm font-semibold">Records<select className={inputStyle} value={filters.view} onChange={(e) => change('view', e.target.value)}>
        {VIEWS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select></label>
      <label className="text-sm font-semibold">Subject<select className={inputStyle} value={filters.subject_id} onChange={(e) => change('subject_id', e.target.value)}>
        <option value="">All subjects</option>{subjects.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
      </select></label>
      <label className="text-sm font-semibold">From date<input className={inputStyle} type="date" value={filters.date_from} onChange={(e) => change('date_from', e.target.value)} /></label>
      <label className="text-sm font-semibold">Through date<input className={inputStyle} type="date" value={filters.date_to} onChange={(e) => change('date_to', e.target.value)} /></label>
      <label className="text-sm font-semibold">Result or status<select className={inputStyle} value={filters.status} onChange={(e) => change('status', e.target.value)}>
        <option value="">All results</option>{[...new Set([...(data?.statuses || []), ...(filters.status ? [filters.status] : [])])].map((status) => <option key={status} value={status}>{learningLabel(status)}</option>)}
      </select></label>
      <label className="text-sm font-semibold sm:col-span-2">Search answers, topics or notes<input className={inputStyle} type="search" maxLength={200} value={search} onChange={(e) => setSearch(e.target.value)} /></label>
      <div className="flex items-end gap-2"><Button type="submit">Search</Button><Button type="button" variant="quiet" onClick={() => {
        setSearch(''); setFilters({ view: filters.view, subject_id: '', date_from: '', date_to: '', q: '', status: '', sort: 'date', order: 'desc' }); setPage(1);
      }}>Clear filters</Button></div>
    </form>
    <div className="flex flex-wrap justify-between items-center gap-3">
      <p role="status" className="text-sm text-muted">{isLoading ? 'Loading records…' : `${data?.total || 0} saved records${isFetching ? ' · updating…' : ''}`}</p>
      <Button as="a" href={modeHref(`/api/records/export?${query}`)} size="sm"><Download aria-hidden="true" className="w-4 h-4" />Download filtered CSV</Button>
    </div>
    {error && <div role="alert" className="rounded-xl bg-problem-soft p-4"><p>{error.message}</p><Button size="sm" onClick={() => refetch()}>Try again</Button></div>}
    {!isLoading && !error && data && <>
      <div role="region" aria-label="Learning records table" tabIndex={0} className="overflow-x-auto rounded-2xl border border-line bg-surface focus-visible:outline-2 focus-visible:outline-action">
        <table className="w-full text-sm text-left">
          <caption className="sr-only">{VIEWS.find(([key]) => key === filters.view)?.[1]} · page {page} of {pages}. Select Details to read a complete record.</caption>
          <thead className="bg-paper-deep"><tr>{data.columns.map((column) => <th key={column.key} scope="col" className="px-4 py-3 whitespace-nowrap"
            aria-sort={filters.sort === column.key ? filters.order === 'asc' ? 'ascending' : 'descending' : 'none'}>
            <button type="button" className="font-semibold hover:text-action focus-visible:outline-2 focus-visible:outline-action" onClick={() => sortBy(column.key)}>{column.label}{filters.sort === column.key ? filters.order === 'asc' ? ' ↑' : ' ↓' : ''}</button>
          </th>)}<th scope="col" className="px-4 py-3">Record</th></tr></thead>
          <tbody className="divide-y divide-line-soft">{data.rows.map((row) => <tr key={row.id} className="hover:bg-paper/50">
            {data.columns.map((column) => <td key={column.key} className="px-4 py-3 align-top min-w-28 max-w-72"><span className="block line-clamp-3 break-words">{columnText(column.key, row[column.key])}</span></td>)}
            <td className="px-4 py-3 align-top"><Button size="sm" onClick={() => setOpened(row)} aria-label={`Details for ${row.child}, ${row.reference || row.topic || row.book || row.date}`}>Details</Button></td>
          </tr>)}{!data.rows.length && <tr><td colSpan={data.columns.length + 1} className="p-8 text-muted text-center">No records match these filters.</td></tr>}</tbody>
        </table>
      </div>
      <div className="flex flex-wrap gap-3 justify-between items-center text-sm text-muted">
        <span>Page {page} of {pages} · 25 records per page</span>
        <div className="flex gap-2"><Button size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button><Button size="sm" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</Button></div>
      </div>
      {opened && <RecordDetails record={opened} columns={data.columns} onClose={() => setOpened(null)} />}
    </>}
  </>;
}

export default function Records() {
  const { selected } = useLearner();
  return <><ScreenHeader /><div className="px-4 md:px-10 py-7 flex flex-col gap-5">
    <div><h1 className="font-display text-3xl md:text-4xl font-medium">Learning records</h1>
      <p className="text-muted mt-2">Your saved work, help and progress. Choose a learner at the top, then explore the records.</p></div>
    <p className="text-sm text-muted">Reading completion and independent understanding are recorded separately. These tables are read-only; downloading or opening saved work uses no AI credits.</p>
    <RecordsTable key={selected} child={selected} />
  </div></>;
}
