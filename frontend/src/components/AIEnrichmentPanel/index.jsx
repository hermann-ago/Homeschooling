import React, { useState, useEffect } from 'react';
import { canvasApi } from '../../api/canvas';
import { getDocument, getDocumentData } from '../../api/documents';
import { extractPdfPages } from '../../utils/pdf';
import {
  Sparkles, ChevronDown, ChevronUp, Loader2, Zap, RefreshCw, AlertCircle
} from 'lucide-react';
import clsx from 'clsx';
import { TOOLS, COLOUR } from './constants';
import QuizView from './QuizView';
import AudioView from './AudioView';
import TermsView from './TermsView';
import ExplainView from './ExplainView';

export default function AIEnrichmentPanel({
  topicId,
  pageStart,
  pageEnd,
  documentId,
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
      if (!documentId) throw new Error('This topic has no hosted document.');
      const document = await getDocument(documentId);
      const pdfData = await getDocumentData(document.blob_path, document.size_bytes);
      const sourceText = await extractPdfPages(pdfData, pageStart, pageEnd, pdfPageOffset);
      if (!sourceText) throw new Error('No selectable text was found in these pages. Scanned pages need OCR first.');
      const res = await canvasApi.generateAIContent({
        topic_id: topicId,
        page_start: pageStart,
        page_end: pageEnd,
        content_type: toolKey,
        source_text: sourceText,
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
          {!documentId && (
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
