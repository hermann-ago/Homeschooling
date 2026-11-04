import { useEffect, useId, useRef, useState } from 'react';
import clsx from 'clsx';
import { Button } from '../../ui';
import { beginNarration, registerNarrator } from '../../utils/narration';
import { activityDefinition, responseStage } from './registry';
import VideoLesson from './VideoLesson';

export function ReadAloudButton({ text, language = 'en-US', disabled }) {
  const id = useId();
  const [speaking, setSpeaking] = useState(false);
  const available = typeof window !== 'undefined' && window.speechSynthesis && typeof SpeechSynthesisUtterance !== 'undefined';
  const speakingRef = useRef(false);
  useEffect(() => registerNarrator(id, () => {
    if (speakingRef.current) window.speechSynthesis?.cancel();
    speakingRef.current = false; setSpeaking(false);
  }), [id]);
  if (!available || !text) return null;
  return <Button size="sm" variant="quiet" disabled={disabled} onClick={() => {
    if (speakingRef.current) {
      window.speechSynthesis.cancel(); speakingRef.current = false; setSpeaking(false); return;
    }
    beginNarration(id);
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = language;
    utterance.onend = utterance.onerror = () => { speakingRef.current = false; setSpeaking(false); };
    speakingRef.current = true; setSpeaking(true); window.speechSynthesis.speak(utterance);
  }}>{speaking ? 'Stop reading aloud' : 'Read aloud'}</Button>;
}

function NumberLine({ visual }) {
  const minimum = Number(visual.minimum ?? 0);
  const maximum = Number(visual.maximum ?? 10);
  const step = Number(visual.step) || 1;
  const span = maximum - minimum;
  const x = (value) => 35 + ((value - minimum) / span) * 530;
  const ticks = Array.from({ length: Math.min(201, Math.floor(span / step + 1e-9) + 1) }, (_, i) => minimum + i * step);
  const labelEvery = Math.max(1, Math.ceil(ticks.length / 21));
  const alternative = `${visual.caption ? `${visual.caption}. ` : ''}Number line from ${minimum} to ${maximum}, in steps of ${step}.${(visual.points || []).map((point) => ` ${point.label}: ${point.value}.`).join('')}`;
  return <svg role="img" aria-label={alternative} viewBox="0 0 600 105" className="w-full min-w-0">
    <line x1="35" y1="48" x2="565" y2="48" stroke="currentColor" strokeWidth="2" />
    {ticks.map((tick, index) => <g key={tick}><title>{Number(tick.toPrecision(8))}</title><line x1={x(tick)} y1="41" x2={x(tick)} y2="55" stroke="currentColor" />{(index % labelEvery === 0 || index === ticks.length - 1) && <text x={x(tick)} y="74" textAnchor="middle" fontSize="13">{Number(tick.toPrecision(8))}</text>}</g>)}
    {(visual.points || []).map((point, i) => <g key={`${point.value}-${i}`}><circle cx={x(point.value)} cy="48" r="6" fill="var(--color-action)" /><text x={x(point.value)} y={i % 2 ? 98 : 24} textAnchor="middle" fontSize="14" fill="var(--color-action)">{point.label || point.value}</text></g>)}
  </svg>;
}

function Diagram({ visual }) {
  const nodes = visual.nodes || [];
  const position = (id) => {
    const index = nodes.findIndex((node) => node.id === id);
    return index < 0 ? null : { x: 100 + (index % 3) * 200, y: 55 + Math.floor(index / 3) * 100 };
  };
  return <div className="overflow-x-auto"><svg role="img" aria-label={visual.caption || 'Concept diagram'} viewBox={`0 0 600 ${Math.max(120, Math.ceil(nodes.length / 3) * 100 + 10)}`} className="w-full min-w-[280px]">
    {(visual.edges || []).map((edge, i) => {
      const start = position(edge.from_id); const end = position(edge.to_id);
      if (!start || !end) return null;
      return <g key={i}><line x1={start.x} y1={start.y} x2={end.x} y2={end.y} stroke="var(--color-action)" strokeWidth="2" /><text x={(start.x + end.x) / 2} y={(start.y + end.y) / 2 - 7} textAnchor="middle" fontSize="11">{edge.label}</text></g>;
    })}
    {nodes.map((node) => { const point = position(node.id); return <g key={node.id}>
      <rect x={point.x - 82} y={point.y - 25} width="164" height="50" rx="10" fill="var(--color-action-soft)" stroke="var(--color-action)" />
      <title>{node.label}</title><text x={point.x} y={point.y + 4} textAnchor="middle" fontSize="12">{node.label.length > 24 ? `${node.label.slice(0, 23)}…` : node.label}</text>
    </g>; })}
  </svg><ul className="sr-only">{nodes.map((node) => <li key={node.id}>{node.label}</li>)}{(visual.edges || []).map((edge, i) => <li key={`edge-${i}`}>{nodes.find((node) => node.id === edge.from_id)?.label} {edge.label || 'connects to'} {nodes.find((node) => node.id === edge.to_id)?.label}</li>)}</ul></div>;
}

function VisualAid({ visual, onSource }) {
  if (!visual) return null;
  return <figure className="rounded-xl border border-line bg-paper/40 p-3">
    {visual.type === 'number_line' && <NumberLine visual={visual} />}
    {visual.type === 'timeline' && <ol aria-label={visual.caption || 'Timeline'} className="border-l-2 border-action ml-2 pl-5 flex flex-col gap-4">{(visual.events || []).map((event, i) => <li key={i} className="relative"><span className="absolute -left-[27px] top-1.5 rounded-full w-2.5 h-2.5 bg-action" /><span className="font-semibold">{event.date ?? 'Date not specified'}</span><p>{event.label}</p></li>)}</ol>}
    {visual.type === 'diagram' && <Diagram visual={visual} />}
    {visual.type === 'book_illustration' && <><p>Look at the illustration on book page {visual.page}.</p>{onSource && <Button size="sm" onClick={() => onSource({ document_id: visual.document_id, page: visual.page })}>Show book illustration</Button>}</>}
    {visual.caption && <figcaption className="mt-2 text-sm text-muted">{visual.caption}</figcaption>}
  </figure>;
}

/** Content rendering is deliberately ordinary React text, never arbitrary HTML. */
/** The tutor's own commentary, as opposed to the book's words or exercises. */
const teacherWords = (activity) => ['introduce', 'close_lesson'].includes(activity.kind)
  || (activity.kind === 'explain_or_observe' && activity.origin !== 'required_book');

export default function ActivityCard({ activity, language, busy, onEvent, onSource, renderReading, renderTeacherText, state, readOnly = false, docked = false }) {
  const content = activity.content || {};
  const definition = activityDefinition(activity);
  const stage = responseStage(activity);
  const stepIndex = String(stage).startsWith('example:') ? Number(String(stage).split(':')[1]) : ['practice', 'complete'].includes(stage) ? (content.steps || []).length : Number.isFinite(Number(stage)) ? Number(stage) : Number(activity.stage_index || 0);
  const steps = content.steps || [];
  const totalSteps = activity.stage_count || steps.length;
  const hasPractice = activity.has_practice || Boolean(content.practice_prompt);
  const revealed = ['reflection', 'revealed', 'check', 'complete', 'completed'].includes(String(stage)) || activity.revealed === true;
  let prompt = readOnly ? content.prompt || activity.interactions?.[0]?.prompt || activity.interaction?.prompt : activity.interaction?.prompt || (activity.kind === 'predict_then_check' && revealed ? content.reflection_prompt : content.prompt);
  if (!readOnly && prompt && content.choices?.length) {
    // Original book prompts may already contain every option. The active
    // response control renders those options; keep the complete text in history.
    let stem = prompt.replace(/\s+/g, ' ').trim();
    for (const choice of [...content.choices].reverse()) {
      const label = choice.label.replace(/\s+/g, ' ').trim();
      if (!stem.endsWith(label)) { stem = ''; break; }
      stem = stem.slice(0, -label.length).trim();
    }
    if (stem) prompt = stem;
  }
  return <div className="flex flex-col gap-3">
    {content.title && <h3 className="font-semibold text-lg">{content.title}</h3>}
    {teacherWords(activity) && content.text
      ? <div className={clsx('teacher-note', activity.kind === 'introduce' && 'activity-introduction')}>
          <span className="teacher-note-label">Teacher</span>
          <div className="whitespace-pre-wrap">{renderTeacherText?.(activity) || content.text}</div>
        </div>
      : content.text && !(definition.family === 'reading' && renderReading) && <p className="whitespace-pre-wrap leading-relaxed">{content.text}</p>}
    {content.video && <VideoLesson video={content.video} readOnly={readOnly || activity.status !== 'pending'} onWatched={() => onEvent?.('video_watched')} />}
    {definition.family === 'reading' && renderReading?.({ activity, state, complete: () => onEvent('reading_done') })}
    {definition.family === 'reading' && !renderReading && !readOnly && !docked && activity.status === 'pending' && <Button size="sm" disabled={busy} onClick={() => onEvent('reading_done')}>I have finished this reading</Button>}
    {definition.family === 'physical' && <div className="rounded-xl border border-line bg-paper p-3">
      <p className="font-semibold">{content.book_name || content.book || activity.exercise?.book_name || 'Your physical book'}</p>
      <p className="text-sm text-muted">{content.printed_page || content.page || content.pages?.join(', ') ? `Page ${content.printed_page || content.page || content.pages?.join(', ')}` : ''}{content.exercise_reference || content.exercise_ref || content.reference ? ` · Exercise ${content.exercise_reference || content.exercise_ref || content.reference}` : ''}</p>
      {content.instructions && <p className="mt-2 whitespace-pre-wrap">{content.instructions}</p>}
      <p className="mt-2 text-sm text-muted">{content.evidence_requirement === 'spelling' ? 'Type the complete word below, including its accents. You can also write it in your book.' : content.matching ? 'Choose the matches below. You can also complete the matching in your book.' : content.blanks ? 'Type each answer below, or send a photo of your book.' : 'Write in your book first. We will capture what you wrote afterward.'}</p>
    </div>}
    {definition.family === 'comparison' && <div className="grid grid-cols-1 sm:grid-cols-2 gap-3" aria-label="Items to compare">{(content.items || []).map((item) => <article key={item.id} className="rounded-xl border border-line bg-paper/50 p-3"><h4 className="font-semibold">{item.title}</h4><p className="whitespace-pre-wrap mt-1">{item.text}</p></article>)}</div>}
    {definition.family === 'worked' && <>
      <p className="text-xs text-muted">Support: {content.support_level || 'modeled'}</p>
      <ol aria-label="Worked example steps" className="flex flex-col gap-2 list-decimal pl-5">{steps.slice(0, readOnly && activity.status === 'answered' ? steps.length : stepIndex + 1).map((step, i) => <li key={i}><span className="font-semibold">{step.label}</span><p className="whitespace-pre-wrap">{step.text}</p></li>)}</ol>
      {!readOnly && !['practice', 'complete'].includes(stage) && stepIndex < totalSteps && <Button size="sm" disabled={busy} onClick={() => onEvent('advance_stage')}>{stepIndex < totalSteps - 1 ? 'Show next example step' : hasPractice ? 'Try it yourself' : 'Finish the example'}</Button>}
      {content.practice_prompt && stage === 'practice' && <p className="font-semibold whitespace-pre-wrap">{content.practice_prompt}</p>}
    </>}
    {definition.family === 'visual' && <VisualAid visual={content.visual} onSource={onSource} />}
    {definition.family === 'puzzle' && <div className="rounded-xl border border-attention bg-attention-soft p-3"><p className="font-bold text-attention">{content.puzzle_label || 'Find the mistake puzzle'}</p><p className="text-sm text-muted mt-1">This example deliberately contains a mistake. Find it and explain your correction.</p><pre className="font-sans whitespace-pre-wrap mt-3">{content.example}</pre></div>}
    {definition.family === 'transfer' && <div className="rounded-xl border border-line bg-paper p-3 whitespace-pre-wrap">{content.scenario}</div>}
    {definition.family === 'prediction' && <>
      {!revealed && <p className="text-sm text-muted">Save your prediction and your reason before checking the next part.</p>}
      {revealed && <div className="rounded-xl border border-action/30 bg-action-soft p-3" aria-label="Prediction check"><p className="font-semibold mb-1">Now check</p><p className="whitespace-pre-wrap">{content.reveal?.text}</p></div>}
    </>}
    {prompt && prompt !== content.text && <p className="font-semibold whitespace-pre-wrap">{prompt}</p>}
    {!docked && content.prompt && prompt && content.prompt !== prompt && <p className="text-sm text-muted">Original question: {content.prompt}</p>}
    {!readOnly && !docked && definition.family !== 'reading' && <ReadAloudButton text={[...new Set([content.text, prompt].filter(Boolean))].join('\n')} language={language} disabled={busy} />}
  </div>;
}
