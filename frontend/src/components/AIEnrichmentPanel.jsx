/**
 * AIEnrichmentPanel  —  Daily Canvas Phase 2
 * ===========================================
 * A self-contained panel that sits between the PDF viewer and the "Insert pages"
 * button in each canvas section.  It exposes four AI-powered tools:
 *
 *   Quiz          → 5-question multiple-choice quiz with scoring
 *   Audio Summary → Gemini-written summary read aloud via SpeechSynthesis
 *   Key Terms     → Flashcard-style vocabulary cards
 *   Explain Simply → "Explain Like I'm 10" simplified paragraph
 *
 * Content is cached per topic+pages+type — a ⚡ badge shows when it's instant.
 *
 * Props
 * -----
 *   topicId       {number}  — CurriculumTopic id
 *   pageStart     {number}  — Logical TOC page start
 *   pageEnd       {number}  — Logical TOC page end
 *   pdfPath       {string}  — Relative PDF path (e.g. 'uploads/book.pdf')
 *   pdfPageOffset {number}  — TOC→physical page offset
 *   language      {string}  — 'pt' or 'en' (default 'en')
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { canvasApi } from '../api/canvas';
import {
  Sparkles, BrainCircuit, Volume2, BookMarked, Lightbulb,
  ChevronDown, ChevronUp, Loader2, CheckCircle2, XCircle,
  Play, Pause, Square, Zap, RefreshCw, AlertCircle
} from 'lucide-react';
import clsx from 'clsx';

// ── Constants ─────────────────────────────────────────────────────────────────

const TOOLS = [
  {
    key: 'quiz',
    label: 'Quiz',
    icon: BrainCircuit,
    color: 'violet',
    description: 'Test your knowledge',
  },
  {
    key: 'audio',
    label: 'Listen',
    icon: Volume2,
    color: 'sky',
    description: 'Hear a summary',
  },
  {
    key: 'terms',
    label: 'Key Terms',
    icon: BookMarked,
    color: 'amber',
    description: 'Learn vocabulary',
  },
  {
    key: 'explain',
    label: 'Simplify',
    icon: Lightbulb,
    color: 'emerald',
    description: 'Explain simply',
  },
];

// Tailwind colour maps — avoids dynamic class generation issues
const COLOUR = {
  violet: {
    bg: 'bg-violet-50',
    border: 'border-violet-200',
    text: 'text-violet-700',
    btn: 'bg-violet-100 hover:bg-violet-200 text-violet-700',
    badge: 'bg-violet-100 text-violet-600',
    icon: 'text-violet-500',
  },
  sky: {
    bg: 'bg-sky-50',
    border: 'border-sky-200',
    text: 'text-sky-700',
    btn: 'bg-sky-100 hover:bg-sky-200 text-sky-700',
    badge: 'bg-sky-100 text-sky-600',
    icon: 'text-sky-500',
  },
  amber: {
    bg: 'bg-amber-50',
    border: 'border-amber-200',
    text: 'text-amber-700',
    btn: 'bg-amber-100 hover:bg-amber-200 text-amber-700',
    badge: 'bg-amber-100 text-amber-600',
    icon: 'text-amber-500',
  },
  emerald: {
    bg: 'bg-emerald-50',
    border: 'border-emerald-200',
    text: 'text-emerald-700',
    btn: 'bg-emerald-100 hover:bg-emerald-200 text-emerald-700',
    badge: 'bg-emerald-100 text-emerald-600',
    icon: 'text-emerald-500',
  },
};

// ── Sub-components ────────────────────────────────────────────────────────────

/** Quiz view: renders questions, radio buttons, submit & score card. */
function QuizView({ questions }) {
  const [answers, setAnswers] = useState({});
  const [submitted, setSubmitted] = useState(false);

  const score = submitted
    ? questions.filter((q, i) => answers[i] === q.answer).length
    : null;

  const handleSubmit = () => {
    if (Object.keys(answers).length < questions.length) return;
    setSubmitted(true);
  };

  const handleRetry = () => {
    setAnswers({});
    setSubmitted(false);
  };

  return (
    <div className="space-y-4">
      {submitted && (
        <div className={clsx(
          'rounded-xl p-4 text-center font-bold text-lg border',
          score === questions.length
            ? 'bg-green-50 border-green-200 text-green-700'
            : score >= Math.ceil(questions.length / 2)
              ? 'bg-amber-50 border-amber-200 text-amber-700'
              : 'bg-red-50 border-red-200 text-red-600'
        )}>
          {score === questions.length ? '🎉 Perfect!' : score >= Math.ceil(questions.length / 2) ? '👍 Good job!' : '💪 Keep studying!'}
          <span className="ml-2 font-normal text-sm">
            {score} / {questions.length} correct
          </span>
        </div>
      )}

      {questions.map((q, idx) => {
        const userAnswer = answers[idx];
        const isCorrect = submitted && userAnswer === q.answer;
        const isWrong = submitted && userAnswer && userAnswer !== q.answer;

        return (
          <div
            key={idx}
            className={clsx(
              'rounded-xl border p-4 transition',
              submitted
                ? isCorrect ? 'border-green-200 bg-green-50/50'
                  : isWrong ? 'border-red-200 bg-red-50/50'
                    : 'border-border bg-white'
                : 'border-border bg-white'
            )}
          >
            <p className="font-semibold text-sm text-text-primary mb-3">
              <span className="text-violet-500 mr-1">{idx + 1}.</span> {q.question}
            </p>
            <div className="space-y-1.5">
              {q.choices.map((choice) => {
                const letter = choice.charAt(0);
                const isSelected = userAnswer === letter;
                const isAnswer = q.answer === letter;

                return (
                  <label
                    key={letter}
                    className={clsx(
                      'flex items-center space-x-2 px-3 py-2 rounded-lg cursor-pointer transition text-sm',
                      submitted
                        ? isAnswer
                          ? 'bg-green-100 text-green-700 font-medium'
                          : isSelected && !isAnswer
                            ? 'bg-red-100 text-red-600'
                            : 'text-text-secondary'
                        : isSelected
                          ? 'bg-violet-100 text-violet-700'
                          : 'hover:bg-gray-50 text-text-primary'
                    )}
                  >
                    <input
                      type="radio"
                      name={`q-${idx}`}
                      value={letter}
                      disabled={submitted}
                      checked={isSelected}
                      onChange={() => setAnswers(prev => ({ ...prev, [idx]: letter }))}
                      className="accent-violet-600"
                    />
                    <span>{choice}</span>
                    {submitted && isAnswer && (
                      <CheckCircle2 className="w-3.5 h-3.5 text-green-600 ml-auto flex-shrink-0" />
                    )}
                    {submitted && isSelected && !isAnswer && (
                      <XCircle className="w-3.5 h-3.5 text-red-500 ml-auto flex-shrink-0" />
                    )}
                  </label>
                );
              })}
            </div>
          </div>
        );
      })}

      <div className="flex gap-2">
        {!submitted ? (
          <button
            onClick={handleSubmit}
            disabled={Object.keys(answers).length < questions.length}
            className={clsx(
              'flex-1 py-2.5 rounded-xl text-sm font-bold transition',
              Object.keys(answers).length < questions.length
                ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                : 'bg-violet-600 hover:bg-violet-700 text-white active:scale-95'
            )}
          >
            Submit Quiz
          </button>
        ) : (
          <button
            onClick={handleRetry}
            className="flex items-center space-x-1.5 px-4 py-2 rounded-xl text-sm font-semibold bg-violet-100 hover:bg-violet-200 text-violet-700 transition"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            <span>Try Again</span>
          </button>
        )}
      </div>
    </div>
  );
}

/** Audio view: play/pause/stop browser TTS for the summary text. */
function AudioView({ text }) {
  const [playing, setPlaying] = useState(false);
  const utteranceRef = useRef(null);

  const stop = useCallback(() => {
    window.speechSynthesis.cancel();
    setPlaying(false);
  }, []);

  // Clean up on unmount
  useEffect(() => () => stop(), [stop]);

  const handlePlay = () => {
    if (playing) {
      window.speechSynthesis.pause();
      setPlaying(false);
      return;
    }
    if (window.speechSynthesis.paused) {
      window.speechSynthesis.resume();
      setPlaying(true);
      return;
    }
    // Start fresh
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 0.9;
    utterance.onend = () => setPlaying(false);
    utterance.onerror = () => setPlaying(false);
    utteranceRef.current = utterance;
    window.speechSynthesis.speak(utterance);
    setPlaying(true);
  };

  return (
    <div className="space-y-4">
      {/* Summary text block */}
      <div className="bg-white rounded-xl border border-sky-200 p-4 text-sm text-text-primary leading-relaxed">
        {text}
      </div>

      {/* Controls */}
      <div className="flex items-center gap-3">
        <button
          onClick={handlePlay}
          className={clsx(
            'flex items-center space-x-2 px-5 py-2.5 rounded-xl text-sm font-bold transition active:scale-95',
            playing
              ? 'bg-sky-600 text-white hover:bg-sky-700'
              : 'bg-sky-100 text-sky-700 hover:bg-sky-200'
          )}
        >
          {playing ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
          <span>{playing ? 'Pause' : 'Play'}</span>
        </button>
        {(playing || window.speechSynthesis.paused) && (
          <button
            onClick={stop}
            className="flex items-center space-x-1.5 px-4 py-2.5 rounded-xl text-sm font-semibold bg-gray-100 hover:bg-gray-200 text-text-secondary transition"
          >
            <Square className="w-3.5 h-3.5" />
            <span>Stop</span>
          </button>
        )}
        <p className="text-xs text-text-secondary ml-auto">
          Powered by your browser's TTS
        </p>
      </div>
    </div>
  );
}

/** Key Terms view: flip-card vocabulary display. */
function TermsView({ terms }) {
  const [flipped, setFlipped] = useState({});

  const toggle = (idx) => setFlipped(prev => ({ ...prev, [idx]: !prev[idx] }));

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
      {terms.map((item, idx) => (
        <button
          key={idx}
          onClick={() => toggle(idx)}
          className={clsx(
            'text-left rounded-xl border p-4 transition cursor-pointer active:scale-95',
            flipped[idx]
              ? 'bg-amber-50 border-amber-300'
              : 'bg-white border-border hover:border-amber-200 hover:bg-amber-50/30'
          )}
        >
          <div className="text-xs text-amber-500 font-semibold uppercase tracking-wide mb-1">
            {flipped[idx] ? 'Definition' : 'Term  — tap to reveal'}
          </div>
          <div className={clsx(
            'text-sm font-medium',
            flipped[idx] ? 'text-amber-800' : 'text-text-primary'
          )}>
            {flipped[idx] ? item.definition : item.term}
          </div>
        </button>
      ))}
    </div>
  );
}

/** Simple Explanation view: clean readable card. */
function ExplainView({ text }) {
  return (
    <div className="bg-white rounded-xl border border-emerald-200 p-5">
      <div className="flex items-center space-x-2 mb-3">
        <Lightbulb className="w-4 h-4 text-emerald-500" />
        <span className="text-xs font-semibold text-emerald-600 uppercase tracking-wide">
          Simple Explanation
        </span>
      </div>
      <p className="text-sm text-text-primary leading-relaxed">{text}</p>
    </div>
  );
}

// ── Main Component ────────────────────────────────────────────────────────────

export default function AIEnrichmentPanel({
  topicId,
  pageStart,
  pageEnd,
  pdfPath,
  pdfPageOffset = 0,
  language = 'en',
}) {
  const [open, setOpen] = useState(false);
  const [activeTool, setActiveTool] = useState(null);
  const [loadingTool, setLoadingTool] = useState(null);
  const [results, setResults] = useState({});   // { [content_type]: { content, from_cache } }
  const [error, setError] = useState(null);
  const [cachedTypes, setCachedTypes] = useState(new Set());

  // On open: fetch which types are already cached (for ⚡ badges)
  useEffect(() => {
    if (!open || !topicId) return;
    canvasApi.getAIContentForTopic(topicId)
      .then(rows => {
        const types = new Set(rows.map(r => r.content_type));
        setCachedTypes(types);
        // Pre-populate results with cached data
        const preloaded = {};
        rows.forEach(r => {
          preloaded[r.content_type] = { content: r.content, from_cache: true };
        });
        setResults(prev => ({ ...preloaded, ...prev }));
      })
      .catch(() => { /* silent — badges are cosmetic */ });
  }, [open, topicId]);

  const handleToolClick = async (toolKey) => {
    setError(null);

    // If already have the result, just toggle it
    if (activeTool === toolKey) {
      setActiveTool(null);
      return;
    }

    // If already loaded (from cache or previous click), just show it
    if (results[toolKey]) {
      setActiveTool(toolKey);
      return;
    }

    // Generate
    setLoadingTool(toolKey);
    setActiveTool(toolKey);
    try {
      const res = await canvasApi.generateAIContent({
        topic_id: topicId,
        page_start: pageStart,
        page_end: pageEnd,
        content_type: toolKey,
        pdf_path: pdfPath,
        pdf_page_offset: pdfPageOffset,
        language: language || 'en',
      });
      setResults(prev => ({
        ...prev,
        [toolKey]: { content: res.content, from_cache: res.from_cache },
      }));
      if (res.from_cache) setCachedTypes(prev => new Set([...prev, toolKey]));
    } catch (err) {
      const msg = err?.message || 'AI generation failed. Please try again.';
      setError(msg);
      setActiveTool(null);
    } finally {
      setLoadingTool(null);
    }
  };

  /** Parse content based on tool type. */
  const parseContent = (toolKey, rawContent) => {
    if (toolKey === 'quiz' || toolKey === 'terms') {
      try { return JSON.parse(rawContent); } catch { return null; }
    }
    return rawContent; // plain string for audio / explain
  };

  const activeResult = activeTool && results[activeTool]
    ? parseContent(activeTool, results[activeTool].content)
    : null;

  const activeTool$ = TOOLS.find(t => t.key === activeTool);

  // Don't render if no topicId (can't call API without it)
  if (!topicId) return null;

  return (
    <div className="border-t border-dashed border-violet-200 bg-gradient-to-b from-violet-50/40 to-transparent">

      {/* Toggle bar */}
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-5 py-3 hover:bg-violet-50/60 transition group"
      >
        <div className="flex items-center space-x-2">
          <Sparkles className="w-4 h-4 text-violet-500 group-hover:scale-110 transition-transform" />
          <span className="text-sm font-semibold text-violet-700">AI Learning Tools</span>
          {cachedTypes.size > 0 && (
            <span className="text-[10px] bg-violet-100 text-violet-600 px-2 py-0.5 rounded-full font-semibold">
              {cachedTypes.size} cached
            </span>
          )}
        </div>
        {open
          ? <ChevronUp className="w-4 h-4 text-violet-400" />
          : <ChevronDown className="w-4 h-4 text-violet-400" />
        }
      </button>

      {/* Expanded panel */}
      {open && (
        <div className="px-4 pb-5 space-y-4">

          {/* Tool buttons row */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {TOOLS.map(tool => {
              const isCached = cachedTypes.has(tool.key);
              const isActive = activeTool === tool.key;
              const isLoading = loadingTool === tool.key;
              const c = COLOUR[tool.color];
              const Icon = tool.icon;

              return (
                <button
                  key={tool.key}
                  onClick={() => handleToolClick(tool.key)}
                  disabled={!!loadingTool}
                  className={clsx(
                    'relative flex flex-col items-center p-3 rounded-xl border transition text-center',
                    'disabled:opacity-60 disabled:cursor-not-allowed',
                    'active:scale-95',
                    isActive
                      ? `${c.bg} ${c.border} ${c.text} shadow-sm`
                      : `bg-white border-border hover:${c.bg} hover:${c.border} text-text-secondary hover:${c.text}`
                  )}
                >
                  {/* Cached badge */}
                  {isCached && !isLoading && (
                    <span className="absolute top-1.5 right-1.5">
                      <Zap className={`w-2.5 h-2.5 ${c.icon}`} />
                    </span>
                  )}

                  {isLoading
                    ? <Loader2 className={`w-5 h-5 mb-1 animate-spin ${c.icon}`} />
                    : <Icon className={`w-5 h-5 mb-1 ${isActive ? c.icon : 'text-gray-400'}`} />
                  }
                  <span className="text-xs font-semibold leading-tight">{tool.label}</span>
                  <span className="text-[10px] leading-tight mt-0.5 opacity-70">{tool.description}</span>
                </button>
              );
            })}
          </div>

          {/* Error state */}
          {error && (
            <div className="flex items-start space-x-2 p-3 bg-red-50 border border-red-200 rounded-xl">
              <AlertCircle className="w-4 h-4 text-red-500 flex-shrink-0 mt-0.5" />
              <p className="text-xs text-red-700">{error}</p>
            </div>
          )}

          {/* No-PDF notice */}
          {!pdfPath && (
            <p className="text-xs text-center text-text-secondary py-2">
              AI tools require a PDF to be linked to this topic.
            </p>
          )}

          {/* Active result panel */}
          {activeTool && !loadingTool && activeResult && activeTool$ && (
            <div className={clsx(
              'rounded-2xl border p-4',
              COLOUR[activeTool$.color].bg,
              COLOUR[activeTool$.color].border,
            )}>
              {/* Panel header */}
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center space-x-2">
                  <activeTool$.icon className={`w-4 h-4 ${COLOUR[activeTool$.color].icon}`} />
                  <span className={`text-sm font-bold ${COLOUR[activeTool$.color].text}`}>
                    {activeTool$.label}
                  </span>
                  {results[activeTool]?.from_cache && (
                    <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-semibold flex items-center gap-0.5 ${COLOUR[activeTool$.color].badge}`}>
                      <Zap className="w-2.5 h-2.5" /> Cached
                    </span>
                  )}
                </div>
                <button
                  onClick={() => {
                    // Force re-generate by clearing the result for this tool
                    setResults(prev => {
                      const next = { ...prev };
                      delete next[activeTool];
                      return next;
                    });
                    setCachedTypes(prev => {
                      const next = new Set(prev);
                      next.delete(activeTool);
                      return next;
                    });
                    handleToolClick(activeTool);
                  }}
                  title="Re-generate"
                  className={`p-1.5 rounded-lg transition ${COLOUR[activeTool$.color].btn}`}
                >
                  <RefreshCw className="w-3.5 h-3.5" />
                </button>
              </div>

              {/* Tool-specific views */}
              {activeTool === 'quiz' && Array.isArray(activeResult) && (
                <QuizView questions={activeResult} />
              )}
              {activeTool === 'audio' && typeof activeResult === 'string' && (
                <AudioView text={activeResult} />
              )}
              {activeTool === 'terms' && Array.isArray(activeResult) && (
                <TermsView terms={activeResult} />
              )}
              {activeTool === 'explain' && typeof activeResult === 'string' && (
                <ExplainView text={activeResult} />
              )}
            </div>
          )}

          {/* Loading skeleton */}
          {loadingTool && (
            <div className="rounded-2xl border border-dashed border-violet-300 bg-violet-50/50 p-8 flex flex-col items-center space-y-3">
              <Loader2 className="w-8 h-8 text-violet-400 animate-spin" />
              <p className="text-sm text-violet-500 font-medium">
                Generating {TOOLS.find(t => t.key === loadingTool)?.label}…
              </p>
              <p className="text-xs text-violet-400">This may take a few seconds.</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
