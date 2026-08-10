import React, { useState, useEffect, useRef } from 'react';
import { checklistApi } from '../api/checklist';
import { CheckSquare, AlertCircle, Calendar, Clock } from 'lucide-react';
import ResponsivePageViewerPanel from '../components/ResponsivePageViewerPanel';
import ChecklistItem from '../components/ChecklistItem';
import clsx from 'clsx';
import { format } from 'date-fns';

const FamilyToday = ({ children }) => {
  const [allSlots, setAllSlots] = useState({});
  const [missedSlots, setMissedSlots] = useState({});
  const [loading, setLoading] = useState(true);
  const [currentTime, setCurrentTime] = useState(new Date());
  const [selectedSlot, setSelectedSlot] = useState(null);
  const [showCatchUp, setShowCatchUp] = useState(true);

  const containerRef = useRef(null);
  const scrollInitialized = useRef(false);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const slotsMap = {};
        const missedMap = {};
        for (const child of children) {
          try {
            const todaySlots = await checklistApi.getToday(child.id);
            slotsMap[child.id] = todaySlots;
          } catch {
            slotsMap[child.id] = [];
          }
          try {
            const missed = await checklistApi.getMissed(child.id);
            missedMap[child.id] = missed;
          } catch {
            missedMap[child.id] = [];
          }
        }
        setAllSlots(slotsMap);
        setMissedSlots(missedMap);
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    };
    if (children.length > 0) load();
  }, [children]);

  useEffect(() => {
    const interval = setInterval(() => setCurrentTime(new Date()), 60000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (!loading && containerRef.current && !scrollInitialized.current) {
      const currentHour = new Date().getHours();
      const scrollTo = Math.max(0, (currentHour - 2) * 60);
      containerRef.current.scrollTop = scrollTo;
      scrollInitialized.current = true;
    }
  }, [loading]);

  const toggleSlot = async (childId, slotId, isCompleted) => {
    try {
      if (isCompleted) {
        await checklistApi.uncompleteSlot(slotId);
      } else {
        await checklistApi.completeSlot(slotId);
      }
      setAllSlots(prev => ({
        ...prev,
        [childId]: prev[childId].map(s => s.id === slotId ? { ...s, is_completed: !isCompleted } : s)
      }));
      setMissedSlots(prev => ({
        ...prev,
        [childId]: (prev[childId] || []).map(s => s.id === slotId ? { ...s, is_completed: !isCompleted } : s)
      }));
    } catch (error) {
      console.error('Failed to toggle slot', error);
    }
  };

  const timeToPixels = (timeStr) => {
    if (!timeStr) return 0;
    const [h, m] = timeStr.split(':').map(Number);
    return h * 60 + m;
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center p-12 h-full">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-accent"></div>
      </div>
    );
  }

  const currentHour = currentTime.getHours();
  const currentMinute = currentTime.getMinutes();
  const currentPixels = currentHour * 60 + currentMinute;

  // Aggregate missed counts
  const allMissed = children.flatMap(child =>
    (missedSlots[child.id] || [])
      .filter(s => !s.is_completed)
      .map(s => ({ ...s, _childId: child.id, _childColor: child.color, _childName: child.name }))
  );

  // Also count overdue from today's slots
  const overdueTodayItems = children.flatMap(child =>
    (allSlots[child.id] || [])
      .filter(slot => {
        if (slot.is_completed) return false;
        const bottom = timeToPixels(slot.time_end);
        return currentPixels > bottom;
      })
      .map(s => ({ ...s, _childId: child.id, _childColor: child.color, _childName: child.name }))
  );

  const allCatchUp = [...allMissed, ...overdueTodayItems];

  return (
    <div className="flex h-full w-full overflow-hidden bg-gray-50/50">
      <div className={clsx(
        "flex flex-col w-full transition-all duration-300",
        selectedSlot ? "lg:flex-1 lg:min-w-0" : ""
      )}>
        {/* Header */}
        <header className="p-4 sm:p-6 lg:p-8 pb-0 flex-shrink-0">
          <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3 mb-4">
            <div>
              <h1 className="text-2xl sm:text-3xl font-bold text-text-primary mb-1 flex items-center">
                <Calendar className="w-6 h-6 sm:w-8 sm:h-8 mr-3 text-accent" />
                Family Schedule
              </h1>
              <p className="text-text-secondary text-sm sm:text-base">
                {format(new Date(), 'EEEE, MMMM do')} — All children's tasks at a glance.
              </p>
            </div>
            <div className="flex items-center gap-3 flex-shrink-0">
              {allCatchUp.length > 0 && (
                <button
                  onClick={() => setShowCatchUp(!showCatchUp)}
                  className={clsx(
                    "flex items-center gap-1.5 text-xs font-bold px-3 py-1.5 rounded-full border transition-colors",
                    showCatchUp
                      ? "bg-red-50 text-red-600 border-red-100"
                      : "bg-gray-100 text-text-secondary border-gray-200 hover:bg-red-50 hover:text-red-600"
                  )}
                >
                  <AlertCircle className="w-3.5 h-3.5" />
                  {allCatchUp.length} to catch up
                </button>
              )}
              <span className="text-xs text-text-secondary flex items-center bg-white px-3 py-1.5 rounded-full border border-border shadow-sm">
                <Clock className="w-3.5 h-3.5 mr-1" />
                {format(currentTime, 'h:mm a')}
              </span>
            </div>
          </div>
        </header>

        {/* Content area */}
        <div className="flex-1 overflow-hidden flex flex-col lg:flex-row gap-0 p-4 sm:p-6 lg:p-8 pt-3 sm:pt-3 lg:pt-4">

          {/* Catch Up Column */}
          {showCatchUp && allCatchUp.length > 0 && (
            <div className="lg:w-[340px] xl:w-[380px] flex-shrink-0 flex flex-col mb-4 lg:mb-0 lg:mr-5">
              <div className="bg-white rounded-2xl border border-red-100 shadow-soft overflow-hidden flex flex-col h-full relative">
                <div className="absolute top-0 left-0 w-1 h-full bg-status-at-risk-text rounded-l-2xl" />
                <div className="flex items-center justify-between p-4 border-b border-red-100 bg-red-50/30 flex-shrink-0">
                  <h2 className="text-sm font-bold text-status-at-risk-text flex items-center">
                    <AlertCircle className="w-4 h-4 mr-2" />
                    Catch Up — All Children
                  </h2>
                  <span className="bg-status-at-risk-bg text-status-at-risk-text text-[10px] px-2 py-0.5 rounded-full font-bold">
                    {allCatchUp.length}
                  </span>
                </div>
                <div className="flex-1 overflow-y-auto p-3 space-y-1.5 custom-scrollbar">
                  {allCatchUp.map((slot, index) => (
                    <div
                      key={`${slot.id}-${index}`}
                      className="flex items-center gap-3 p-3 rounded-xl border border-red-100 bg-red-50/20 hover:bg-red-50/50 transition-all cursor-pointer group"
                      onClick={() => toggleSlot(slot._childId, slot.id, slot.is_completed)}
                    >
                      <button className="flex-shrink-0 transition active:scale-90">
                        {slot.is_completed ? (
                          <CheckSquare className="w-5 h-5 text-gray-400" />
                        ) : (
                          <div className="w-4 h-4 rounded border-2 bg-white" style={{ borderColor: slot._childColor }} />
                        )}
                      </button>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-1.5 mb-0.5">
                          <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: slot._childColor }} />
                          <span className="text-[10px] font-bold text-text-secondary">{slot._childName}</span>
                        </div>
                        <p className="text-sm font-semibold text-text-primary truncate">{slot.subject_name}</p>
                        <p className="text-[11px] text-text-secondary truncate">{slot.topic_title}</p>
                      </div>
                      <div className="text-right flex-shrink-0">
                        {slot.date && (
                          <p className="text-[10px] font-medium text-red-400 whitespace-nowrap">
                            {format(new Date(slot.date + 'T00:00:00'), 'MMM d')}
                          </p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Schedule Grid */}
          <div className="flex-1 bg-white rounded-2xl border border-border shadow-soft overflow-hidden flex flex-col min-h-[500px] min-w-0 relative">
            <div className="flex items-center border-b border-border bg-gray-50/80 sticky top-0 z-30 shadow-sm flex-shrink-0">
              <div className="w-12 sm:w-14 flex-shrink-0 border-r border-border border-transparent"></div>
              {children.map(child => (
                <div key={child.id} className="flex-1 py-3 px-2 text-center border-l border-border first:border-l-0 min-w-0">
                  <h3 className="font-bold text-text-primary text-xs sm:text-sm flex items-center justify-center truncate">
                    <div className="w-2.5 h-2.5 sm:w-3 sm:h-3 rounded-full mr-1.5 sm:mr-2 flex-shrink-0" style={{ backgroundColor: child.color }} />
                    <span className="truncate">{child.name}</span>
                  </h3>
                </div>
              ))}
            </div>

            <div className="flex-1 overflow-y-auto relative custom-scrollbar bg-white" ref={containerRef}>
              <div className="relative h-[1440px] min-w-[500px] w-full flex">
                {/* Hour lines */}
                <div className="absolute inset-0 z-0">
                  {Array.from({ length: 24 }).map((_, i) => (
                    <div key={i} className="absolute w-full border-t border-border" style={{ top: `${i * 60}px`, height: '60px' }}></div>
                  ))}
                </div>

                {/* Hour labels */}
                <div className="w-12 sm:w-14 flex-shrink-0 relative z-20 border-r border-border bg-white/60 backdrop-blur-sm">
                  {Array.from({ length: 24 }).map((_, i) => (
                    <div key={i} className="absolute w-full text-right pr-1.5 sm:pr-2" style={{ top: `${i * 60 - 8}px` }}>
                      <span className="text-[9px] sm:text-[10px] font-medium text-text-secondary bg-white px-0.5">
                        {i === 0 ? '12AM' : i < 12 ? `${i}AM` : i === 12 ? '12PM' : `${i - 12}PM`}
                      </span>
                    </div>
                  ))}
                </div>

                {/* Children Lanes */}
                {children.map(child => (
                  <div key={child.id} className="flex-1 relative border-l border-border/50 first:border-l-0 z-10 w-0">
                    {(allSlots[child.id] || []).map(slot => {
                      const top = timeToPixels(slot.time_start);
                      const bottom = timeToPixels(slot.time_end);
                      const height = Math.max(bottom - top, 25);
                      return (
                        <div
                          key={slot.id}
                          onClick={() => setSelectedSlot(slot)}
                          className={clsx(
                            "absolute left-1 right-1 sm:left-1.5 sm:right-1.5 rounded-lg p-1.5 sm:p-2 border overflow-hidden flex flex-col cursor-pointer transition-all shadow-sm group",
                            slot.is_completed
                              ? "bg-gray-50 border-gray-200 opacity-60 hover:opacity-100"
                              : "bg-white hover:shadow-md hover:-translate-y-[1px]"
                          )}
                          style={{
                            top: `${top}px`,
                            height: `${height}px`,
                            borderColor: slot.is_completed ? undefined : child.color,
                            backgroundColor: slot.is_completed ? undefined : `${child.color}12`
                          }}
                        >
                          <div className="flex justify-between items-start h-full">
                            <div className="flex flex-col min-w-0 pr-1">
                              <div className={clsx("font-bold text-[10px] sm:text-xs truncate", slot.is_completed ? "text-text-secondary line-through" : "text-text-primary")}>
                                {slot.subject_name}
                              </div>
                              <div className="text-[9px] sm:text-[10px] truncate font-medium text-text-secondary">
                                {slot.topic_title}
                              </div>
                            </div>
                            <button
                              onClick={(e) => { e.stopPropagation(); toggleSlot(child.id, slot.id, slot.is_completed); }}
                              className="flex-shrink-0 p-0.5 sm:p-1 rounded-md hover:bg-white/50 transition active:scale-90"
                            >
                              {slot.is_completed ? (
                                <CheckSquare className="w-3.5 h-3.5 sm:w-4 sm:h-4 text-gray-400" />
                              ) : (
                                <div className="w-2.5 h-2.5 sm:w-3 sm:h-3 rounded border-2 bg-white mt-0.5" style={{ borderColor: child.color }} />
                              )}
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ))}

                {/* Current time red line */}
                <div
                  className="absolute left-12 sm:left-14 right-0 border-t-[2px] border-red-500 z-30 pointer-events-none"
                  style={{ top: `${currentPixels}px` }}
                >
                  <div className="w-2.5 h-2.5 rounded-full bg-red-500 absolute -left-1.5 -top-[5px] shadow-sm" />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Right side PDF viewer panel */}
      {selectedSlot && (
        <ResponsivePageViewerPanel slot={selectedSlot} childId={selectedSlot.child_id} onClose={() => setSelectedSlot(null)} />
      )}
    </div>
  );
};

export default FamilyToday;
