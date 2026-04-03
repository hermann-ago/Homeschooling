import React, { useState, useEffect } from 'react';
import { canvasApi } from '../api/canvas';
import { checklistApi } from '../api/checklist';
import InsertPicker from '../components/InsertPicker';
import AIEnrichmentPanel from '../components/AIEnrichmentPanel';
import { API_BASE_URL } from '../api/client';
import { format } from 'date-fns';
import {
  BookOpen, CheckSquare, Plus, Trash2, ChevronDown,
  ChevronUp, Loader2, Layout
} from 'lucide-react';
import clsx from 'clsx';

const DailyCanvas = ({ activeChildId }) => {
  const [slots, setSlots] = useState([]);
  const [loading, setLoading] = useState(true);
  const [insertPicker, setInsertPicker] = useState({ open: false, parentTopicId: null });
  const [collapsedSlots, setCollapsedSlots] = useState({});

  const loadCanvas = async () => {
    if (!activeChildId) return;
    setLoading(true);
    try {
      const data = await canvasApi.getToday(activeChildId);
      setSlots(data);
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

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full p-12">
        <Loader2 className="w-10 h-10 animate-spin text-accent" />
      </div>
    );
  }

  return (
    <div className="min-h-full bg-gray-50/50">
      <div className="max-w-3xl mx-auto p-4 sm:p-8">

        {/* Header */}
        <header className="mb-8">
          <h1 className="text-2xl sm:text-3xl font-bold text-text-primary mb-2 flex items-center">
            <Layout className="w-6 h-6 sm:w-8 sm:h-8 mr-3 text-accent" />
            Daily Canvas
          </h1>
          <p className="text-text-secondary text-sm sm:text-base">
            {format(new Date(), 'EEEE, MMMM do')} — {slots.length === 0
              ? "No assignments for today."
              : `${completedCount} of ${slots.length} sections complete.`}
          </p>

          {slots.length > 0 && (
            <div className="mt-4 bg-white rounded-full h-3 w-full border border-border overflow-hidden shadow-inner">
              <div
                className="bg-accent h-full transition-all duration-700 ease-out rounded-full"
                style={{ width: `${progressPercent}%` }}
              />
            </div>
          )}
        </header>

        {slots.length === 0 && (
          <div className="bg-white rounded-2xl border border-border p-12 text-center shadow-soft">
            <BookOpen className="w-12 h-12 text-text-secondary/30 mx-auto mb-4" />
            <p className="text-text-secondary text-sm">
              No assignments scheduled for today. Head to the Calendar to recalculate your schedule.
            </p>
          </div>
        )}

        {/* Canvas sections */}
        <div className="space-y-6">
          {slots.map((slot, idx) => {
            const pdfUrl = buildPdfUrl(slot.pdf_path, slot.page_from, slot.page_to, slot.pdf_page_offset);
            const isCollapsed = collapsedSlots[slot.id];

            return (
              <section
                key={slot.id}
                className={clsx(
                  "bg-white rounded-2xl border shadow-soft overflow-hidden transition-all",
                  slot.is_completed ? "border-green-200 opacity-80" : "border-border"
                )}
              >
                {/* Section header */}
                <div
                  className={clsx(
                    "p-4 sm:p-5 flex items-center justify-between cursor-pointer transition",
                    slot.is_completed ? "bg-green-50/50" : "bg-gray-50/80 hover:bg-gray-50"
                  )}
                  onClick={() => toggleCollapse(slot.id)}
                >
                  <div className="flex items-center min-w-0 flex-1">
                    <div
                      className={clsx(
                        "w-8 h-8 rounded-lg flex items-center justify-center mr-3 flex-shrink-0 text-sm font-bold",
                        slot.is_completed
                          ? "bg-green-100 text-green-600"
                          : "bg-accent/10 text-accent"
                      )}
                    >
                      {idx + 1}
                    </div>
                    <div className="min-w-0">
                      <h2 className={clsx(
                        "font-bold text-base truncate",
                        slot.is_completed ? "text-green-700 line-through" : "text-text-primary"
                      )}>
                        {slot.subject_name}
                      </h2>
                      <p className="text-xs text-text-secondary truncate">
                        {slot.topic_title}
                        {slot.page_from && slot.page_to && (
                          <span className="ml-2 text-accent/70">Pages {slot.page_from}–{slot.page_to}</span>
                        )}
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center space-x-2 flex-shrink-0">
                    <button
                      onClick={(e) => { e.stopPropagation(); toggleComplete(slot.id, slot.is_completed); }}
                      className={clsx(
                        "p-2 rounded-xl transition active:scale-90",
                        slot.is_completed
                          ? "bg-green-100 text-green-600 hover:bg-green-200"
                          : "bg-gray-100 text-text-secondary hover:bg-accent/10 hover:text-accent"
                      )}
                      title={slot.is_completed ? "Mark as incomplete" : "Mark as done"}
                    >
                      <CheckSquare className="w-5 h-5" />
                    </button>
                    {isCollapsed
                      ? <ChevronDown className="w-4 h-4 text-text-secondary" />
                      : <ChevronUp className="w-4 h-4 text-text-secondary" />
                    }
                  </div>
                </div>

                {/* Expandable content */}
                {!isCollapsed && (
                  <div>
                    {/* Main PDF */}
                    {pdfUrl ? (
                      <div className="border-t border-border">
                        <iframe
                          src={pdfUrl}
                          title={`${slot.subject_name} - ${slot.topic_title}`}
                          className="w-full border-none bg-gray-100"
                          style={{ height: '70vh', minHeight: '400px' }}
                        />
                      </div>
                    ) : (
                      <div className="border-t border-border p-8 text-center bg-gray-50">
                        <BookOpen className="w-8 h-8 text-text-secondary/30 mx-auto mb-2" />
                        <p className="text-sm text-text-secondary">
                          {slot.topic_title || 'No PDF available — read from your physical book.'}
                        </p>
                      </div>
                    )}

                    {/* Inserts */}
                    {slot.inserts && slot.inserts.length > 0 && (
                      <div className="border-t border-dashed border-accent/20">
                        {slot.inserts.map(insert => {
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
                      topicId={slot.topic_id}
                      pageStart={slot.page_from}
                      pageEnd={slot.page_to}
                      pdfPath={slot.pdf_path}
                      pdfPageOffset={slot.pdf_page_offset}
                      language={slot.language}
                    />

                    {/* Insert button */}
                    <div className="p-3 border-t border-border bg-gray-50/50 flex justify-center">
                      <button
                        onClick={() => setInsertPicker({ open: true, parentTopicId: slot.topic_id })}
                        disabled={!slot.topic_id}
                        className={clsx(
                          "flex items-center space-x-1.5 px-4 py-2 rounded-xl text-xs font-semibold transition",
                          slot.topic_id
                            ? "text-accent hover:bg-accent/10 hover:text-accent-dark"
                            : "text-gray-300 cursor-not-allowed"
                        )}
                      >
                        <Plus className="w-4 h-4" />
                        <span>Insert pages from another book</span>
                      </button>
                    </div>
                  </div>
                )}
              </section>
            );
          })}
        </div>

        {/* All done celebration */}
        {slots.length > 0 && completedCount === slots.length && (
          <div className="mt-8 text-center p-8 bg-white rounded-2xl border border-green-200 shadow-soft">
            <div className="text-4xl mb-3">🎉</div>
            <h3 className="text-lg font-bold text-green-700 mb-1">All Done!</h3>
            <p className="text-sm text-text-secondary">
              Great job! All of today's assignments are complete.
            </p>
          </div>
        )}
      </div>

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
