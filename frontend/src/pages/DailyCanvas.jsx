import React, { useState, useEffect } from 'react';
import { canvasApi } from '../api/canvas';
import { checklistApi } from '../api/checklist';
import InsertPicker from '../components/InsertPicker';
import AIEnrichmentPanel from '../components/AIEnrichmentPanel';
import { API_BASE_URL } from '../api/client';
import { format } from 'date-fns';
import {
  BookOpen, CheckSquare, Plus, Trash2, ChevronDown,
  ChevronUp, Loader2, Layout, FileText
} from 'lucide-react';
import clsx from 'clsx';

const DailyCanvas = ({ activeChildId }) => {
  const [slots, setSlots] = useState([]);
  const [loading, setLoading] = useState(true);
  const [insertPicker, setInsertPicker] = useState({ open: false, parentTopicId: null });
  const [collapsedSlots, setCollapsedSlots] = useState({});
  const [activeSlotId, setActiveSlotId] = useState(null);

  const loadCanvas = async () => {
    if (!activeChildId) return;
    setLoading(true);
    try {
      const data = await canvasApi.getToday(activeChildId);
      setSlots(data);
      // Auto-select first incomplete slot, or first slot
      if (data.length > 0) {
        const firstIncomplete = data.find(s => !s.is_completed);
        setActiveSlotId(firstIncomplete?.id || data[0].id);
      }
    } catch (err) {
      console.error('Failed to load canvas:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadCanvas();
  }, [activeChildId]);

  const toggleComplete = async (slotId, isCompleted) => {
    try {
      if (isCompleted) {
        await checklistApi.uncompleteSlot(slotId);
      } else {
        await checklistApi.completeSlot(slotId);
      }
      setSlots(prev => prev.map(s =>
        s.id === slotId ? { ...s, is_completed: !isCompleted } : s
      ));
    } catch (err) {
      console.error('Failed to toggle completion:', err);
    }
  };

  const handleInsertSelect = async (topic) => {
    try {
      await canvasApi.createInsert({
        parent_topic_id: insertPicker.parentTopicId,
        insert_topic_id: topic.id,
      });
      setInsertPicker({ open: false, parentTopicId: null });
      await loadCanvas();
    } catch (err) {
      alert('Failed to insert: ' + err.message);
    }
  };

  const handleDeleteInsert = async (insertId) => {
    try {
      await canvasApi.deleteInsert(insertId);
      await loadCanvas();
    } catch (err) {
      console.error('Failed to delete insert:', err);
    }
  };

  const toggleCollapse = (slotId) => {
    setCollapsedSlots(prev => ({ ...prev, [slotId]: !prev[slotId] }));
  };

  const buildPdfUrl = (pdfPath, pageFrom, pageTo, offset) => {
    if (!pdfPath) return null;
    const physicalStart = (pageFrom || 1) + (offset || 0);
    const physicalEnd = (pageTo || pageFrom || 1) + (offset || 0);
    return `${API_BASE_URL}/pdf/slice?path=${encodeURIComponent(pdfPath)}&start=${physicalStart}&end=${physicalEnd}#view=FitH`;
  };

  const completedCount = slots.filter(s => s.is_completed).length;
  const progressPercent = slots.length > 0 ? (completedCount / slots.length) * 100 : 0;

  const activeSlot = slots.find(s => s.id === activeSlotId);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full p-12">
        <Loader2 className="w-10 h-10 animate-spin text-accent" />
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col bg-gray-50/50 overflow-hidden">
      {/* Header */}
      <header className="flex-shrink-0 p-4 sm:p-6 lg:p-8 pb-0">
        <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3 mb-3">
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold text-text-primary mb-1 flex items-center">
              <Layout className="w-6 h-6 sm:w-8 sm:h-8 mr-3 text-accent" />
              Daily Canvas
            </h1>
            <p className="text-text-secondary text-sm sm:text-base">
              {format(new Date(), 'EEEE, MMMM do')} — {slots.length === 0
                ? "No assignments for today."
                : `${completedCount} of ${slots.length} sections complete.`}
            </p>
          </div>
        </div>

        {slots.length > 0 && (
          <div className="bg-white rounded-full h-3 w-full border border-border overflow-hidden shadow-inner">
            <div
              className="bg-accent h-full transition-all duration-700 ease-out rounded-full"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
        )}
      </header>

      {slots.length === 0 && (
        <div className="flex-1 flex items-center justify-center p-8">
          <div className="bg-white rounded-2xl border border-border p-12 text-center shadow-soft max-w-md">
            <BookOpen className="w-12 h-12 text-text-secondary/30 mx-auto mb-4" />
            <p className="text-text-secondary text-sm">
              No assignments scheduled for today. Head to the Calendar to recalculate your schedule.
            </p>
          </div>
        </div>
      )}

      {/* Two-column layout */}
      {slots.length > 0 && (
        <div className="flex-1 overflow-hidden flex flex-col lg:flex-row gap-0 lg:gap-0 p-4 sm:p-6 lg:p-8 pt-4 sm:pt-4 lg:pt-5">

          {/* Left: Section list */}
          <div className="lg:w-[320px] xl:w-[360px] flex-shrink-0 flex flex-col lg:border-r lg:border-border lg:pr-5 mb-4 lg:mb-0">
            <h2 className="text-xs font-bold text-text-secondary uppercase tracking-wider mb-3 flex items-center">
              <FileText className="w-3.5 h-3.5 mr-1.5" />
              Sections
            </h2>
            <div className="flex-1 overflow-y-auto space-y-2 custom-scrollbar pr-1">
              {slots.map((slot, idx) => {
                const isActive = activeSlotId === slot.id;
                return (
                  <button
                    key={slot.id}
                    onClick={() => setActiveSlotId(slot.id)}
                    className={clsx(
                      "w-full text-left p-3 rounded-xl border transition-all duration-200 group flex items-start gap-3",
                      isActive
                        ? "bg-accent/10 border-accent/30 shadow-sm"
                        : slot.is_completed
                          ? "bg-gray-50 border-gray-200 opacity-70 hover:opacity-100"
                          : "bg-white border-gray-200 hover:border-accent/20 hover:shadow-sm"
                    )}
                  >
                    {/* Number badge */}
                    <div className={clsx(
                      "w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 text-xs font-bold",
                      slot.is_completed
                        ? "bg-green-100 text-green-600"
                        : isActive
                          ? "bg-accent text-white"
                          : "bg-gray-100 text-text-secondary"
                    )}>
                      {slot.is_completed ? '✓' : idx + 1}
                    </div>

                    <div className="flex-1 min-w-0">
                      <p className={clsx(
                        "text-sm font-bold truncate",
                        slot.is_completed ? "text-text-secondary line-through" :
                          isActive ? "text-accent-dark" : "text-text-primary"
                      )}>
                        {slot.subject_name}
                      </p>
                      <p className="text-[11px] text-text-secondary truncate">{slot.topic_title}</p>
                      {slot.page_from && slot.page_to && (
                        <p className="text-[10px] text-accent/70 mt-0.5">Pages {slot.page_from}–{slot.page_to}</p>
                      )}
                    </div>

                    {/* Completion toggle */}
                    <button
                      onClick={(e) => { e.stopPropagation(); toggleComplete(slot.id, slot.is_completed); }}
                      className={clsx(
                        "p-1.5 rounded-lg transition active:scale-90 flex-shrink-0",
                        slot.is_completed
                          ? "bg-green-100 text-green-600 hover:bg-green-200"
                          : "bg-gray-100 text-text-secondary hover:bg-accent/10 hover:text-accent"
                      )}
                      title={slot.is_completed ? "Mark as incomplete" : "Mark as done"}
                    >
                      <CheckSquare className="w-4 h-4" />
                    </button>
                  </button>
                );
              })}
            </div>

            {/* All done celebration */}
            {completedCount === slots.length && (
              <div className="mt-3 text-center p-4 bg-white rounded-xl border border-green-200 shadow-soft">
                <div className="text-2xl mb-1">🎉</div>
                <p className="text-sm font-bold text-green-700">All Done!</p>
              </div>
            )}
          </div>

          {/* Right: Active section content viewer */}
          <div className="flex-1 flex flex-col min-w-0 min-h-0">
            {activeSlot ? (
              <div className="flex-1 flex flex-col bg-white rounded-2xl border border-border shadow-soft overflow-hidden">
                {/* Section header */}
                <div className={clsx(
                  "p-4 sm:p-5 flex items-center justify-between flex-shrink-0",
                  activeSlot.is_completed ? "bg-green-50/50" : "bg-gray-50/80"
                )}>
                  <div className="flex items-center min-w-0 flex-1">
                    <div className={clsx(
                      "w-8 h-8 rounded-lg flex items-center justify-center mr-3 flex-shrink-0 text-sm font-bold",
                      activeSlot.is_completed
                        ? "bg-green-100 text-green-600"
                        : "bg-accent/10 text-accent"
                    )}>
                      {slots.findIndex(s => s.id === activeSlot.id) + 1}
                    </div>
                    <div className="min-w-0">
                      <h2 className={clsx(
                        "font-bold text-base sm:text-lg truncate",
                        activeSlot.is_completed ? "text-green-700 line-through" : "text-text-primary"
                      )}>
                        {activeSlot.subject_name}
                      </h2>
                      <p className="text-xs text-text-secondary truncate">
                        {activeSlot.topic_title}
                        {activeSlot.page_from && activeSlot.page_to && (
                          <span className="ml-2 text-accent/70">Pages {activeSlot.page_from}–{activeSlot.page_to}</span>
                        )}
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center space-x-2 flex-shrink-0 ml-3">
                    <button
                      onClick={() => toggleComplete(activeSlot.id, activeSlot.is_completed)}
                      className={clsx(
                        "p-2 rounded-xl transition active:scale-90",
                        activeSlot.is_completed
                          ? "bg-green-100 text-green-600 hover:bg-green-200"
                          : "bg-gray-100 text-text-secondary hover:bg-accent/10 hover:text-accent"
                      )}
                      title={activeSlot.is_completed ? "Mark as incomplete" : "Mark as done"}
                    >
                      <CheckSquare className="w-5 h-5" />
                    </button>
                  </div>
                </div>

                {/* Content area */}
                <div className="flex-1 overflow-y-auto min-h-0">
                  {/* Main PDF */}
                  {(() => {
                    const pdfUrl = buildPdfUrl(activeSlot.pdf_path, activeSlot.page_from, activeSlot.page_to, activeSlot.pdf_page_offset);
                    if (pdfUrl) {
                      return (
                        <div className="border-t border-border h-full">
                          <iframe
                            src={pdfUrl}
                            title={`${activeSlot.subject_name} - ${activeSlot.topic_title}`}
                            className="w-full h-full border-none bg-gray-100"
                            style={{ minHeight: '500px' }}
                          />
                        </div>
                      );
                    }
                    return (
                      <div className="border-t border-border p-8 text-center bg-gray-50 flex-1 flex flex-col items-center justify-center">
                        <BookOpen className="w-10 h-10 text-text-secondary/30 mx-auto mb-3" />
                        <p className="text-sm text-text-secondary">
                          {activeSlot.topic_title || 'No PDF available — read from your physical book.'}
                        </p>
                      </div>
                    );
                  })()}

                  {/* Inserts */}
                  {activeSlot.inserts && activeSlot.inserts.length > 0 && (
                    <div className="border-t border-dashed border-accent/20">
                      {activeSlot.inserts.map(insert => {
                        const insertPdfUrl = buildPdfUrl(
                          insert.insert_pdf_path,
                          insert.insert_page_start,
                          insert.insert_page_end,
                          insert.insert_pdf_page_offset
                        );
                        return (
                          <div key={insert.id} className="border-b border-border last:border-b-0">
                            <div className="px-4 py-3 bg-amber-50/50 flex items-center justify-between">
                              <div className="flex items-center min-w-0">
                                <div className="w-6 h-6 rounded bg-amber-100 flex items-center justify-center mr-2 flex-shrink-0">
                                  <BookOpen className="w-3.5 h-3.5 text-amber-600" />
                                </div>
                                <div className="min-w-0">
                                  <span className="text-sm font-semibold text-amber-800 truncate block">
                                    {insert.insert_subject_name}: {insert.insert_topic_title}
                                  </span>
                                  <span className="text-[10px] text-amber-600">
                                    Pages {insert.insert_page_start}–{insert.insert_page_end}
                                  </span>
                                </div>
                              </div>
                              <button
                                onClick={() => handleDeleteInsert(insert.id)}
                                className="p-1.5 text-amber-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition"
                                title="Remove insert"
                              >
                                <Trash2 className="w-4 h-4" />
                              </button>
                            </div>
                            {insertPdfUrl && (
                              <iframe
                                src={insertPdfUrl}
                                title={`Insert: ${insert.insert_topic_title}`}
                                className="w-full border-none bg-gray-100"
                                style={{ height: '50vh', minHeight: '300px' }}
                              />
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}

                  {/* AI Enrichment Panel (Phase 2) */}
                  <AIEnrichmentPanel
                    topicId={activeSlot.topic_id}
                    pageStart={activeSlot.page_from}
                    pageEnd={activeSlot.page_to}
                    pdfPath={activeSlot.pdf_path}
                    pdfPageOffset={activeSlot.pdf_page_offset}
                    language={activeSlot.language}
                  />

                  {/* Insert button */}
                  <div className="p-3 border-t border-border bg-gray-50/50 flex justify-center">
                    <button
                      onClick={() => setInsertPicker({ open: true, parentTopicId: activeSlot.topic_id })}
                      disabled={!activeSlot.topic_id}
                      className={clsx(
                        "flex items-center space-x-1.5 px-4 py-2 rounded-xl text-xs font-semibold transition",
                        activeSlot.topic_id
                          ? "text-accent hover:bg-accent/10 hover:text-accent-dark"
                          : "text-gray-300 cursor-not-allowed"
                      )}
                    >
                      <Plus className="w-4 h-4" />
                      <span>Insert pages from another book</span>
                    </button>
                  </div>
                </div>
              </div>
            ) : (
              <div className="flex-1 flex items-center justify-center bg-white rounded-2xl border border-border shadow-soft">
                <div className="text-center">
                  <BookOpen className="w-10 h-10 text-text-secondary/30 mx-auto mb-3" />
                  <p className="text-sm text-text-secondary">Select a section from the left to view.</p>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Insert picker modal */}
      {insertPicker.open && (
        <InsertPicker
          childId={activeChildId}
          onSelect={handleInsertSelect}
          onClose={() => setInsertPicker({ open: false, parentTopicId: null })}
        />
      )}
    </div>
  );
};

export default DailyCanvas;
