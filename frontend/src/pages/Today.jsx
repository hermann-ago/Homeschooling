import React, { useState, useEffect, useRef } from 'react';
import { checklistApi } from '../api/checklist';
import ChecklistItem from '../components/ChecklistItem';
import PageViewer from '../components/PageViewer';
import { format } from 'date-fns';
import { CheckSquare, Calendar, AlertCircle, Clock } from 'lucide-react';
import clsx from 'clsx';

const Today = ({ activeChildId }) => {
  const [slots, setSlots] = useState([]);
  const [missedSlots, setMissedSlots] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedSlot, setSelectedSlot] = useState(null);
  const [currentTime, setCurrentTime] = useState(new Date());
  
  // Ref to automatically scroll to current time on load (optional but nice)
  const containerRef = useRef(null);
  const scrollInitialized = useRef(false);

  useEffect(() => {
    if (!activeChildId) return;

    setLoading(true);
    Promise.all([
      checklistApi.getToday(activeChildId),
      checklistApi.getMissed(activeChildId)
    ])
    .then(([todayData, missedData]) => {
      setSlots(todayData);
      setMissedSlots(missedData);
    })
    .catch(console.error)
    .finally(() => setLoading(false));
  }, [activeChildId]);

  useEffect(() => {
    const interval = setInterval(() => {
      setCurrentTime(new Date());
    }, 60000);
    return () => clearInterval(interval);
  }, []);

  // Set initial scroll to near current time
  useEffect(() => {
    if (!loading && containerRef.current && !scrollInitialized.current) {
      const currentHour = new Date().getHours();
      // Scroll to 2 hours before current time
      const scrollTo = Math.max(0, (currentHour - 2) * 60);
      containerRef.current.scrollTop = scrollTo;
      scrollInitialized.current = true;
    }
  }, [loading]);

  const toggleSlot = async (id, isCompleted) => {
    try {
      if (isCompleted) {
        await checklistApi.uncompleteSlot(id);
      } else {
        await checklistApi.completeSlot(id);
      }
      
      setSlots(slots.map(s => s.id === id ? { ...s, is_completed: !isCompleted } : s));
      setMissedSlots(missedSlots.map(s => s.id === id ? { ...s, is_completed: !isCompleted } : s));
    } catch (error) {
      console.error('Failed to toggle slot', error);
    }
  };

  const timeToPixels = (timeStr) => {
    if (!timeStr) return 0;
    const [h, m] = timeStr.split(':').map(Number);
    return h * 60 + m; // 1px per minute, 60px per hour
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center p-12 h-full">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-accent"></div>
      </div>
    );
  }

  const completedTodayCount = slots.filter(s => s.is_completed).length;
  const progressPercent = slots.length > 0 ? (completedTodayCount / slots.length) * 100 : 0;

  const currentHour = currentTime.getHours();
  const currentMinute = currentTime.getMinutes();
  const currentPixels = currentHour * 60 + currentMinute;

  const overdueTodaySlots = slots.filter(slot => {
    if (slot.is_completed) return false;
    const bottom = timeToPixels(slot.time_end);
    return currentPixels > bottom;
  });

  const displayedMissedSlots = [...missedSlots, ...overdueTodaySlots];
  const pendingMissed = displayedMissedSlots.filter(s => !s.is_completed);

  return (
    <div className="flex h-full w-full overflow-hidden bg-gray-50/50">
      <div className={clsx(
        "flex flex-col w-full transition-all duration-300",
        selectedSlot ? "lg:w-3/5 lg:max-w-none" : ""
      )}>
        
        {/* Header Section */}
        <header className="p-4 sm:p-6 lg:p-8 pb-0 flex-shrink-0">
          <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3 mb-4">
            <div>
              <h1 className="text-2xl sm:text-3xl font-bold text-text-primary mb-1 flex items-center">
                <Calendar className="w-6 h-6 sm:w-8 sm:h-8 mr-3 text-accent" />
                Today, {format(new Date(), 'EEEE MMM do')}
              </h1>
              <p className="text-text-secondary text-sm sm:text-base">
                {slots.length === 0 
                  ? "No tasks scheduled for today." 
                  : `${completedTodayCount} of ${slots.length} tasks completed.`}
              </p>
            </div>
            
            {slots.length > 0 && (
              <div className="flex items-center gap-3 flex-shrink-0">
                {pendingMissed.length > 0 && (
                  <div className="flex items-center gap-1.5 bg-red-50 text-red-600 text-xs font-bold px-3 py-1.5 rounded-full border border-red-100">
                    <AlertCircle className="w-3.5 h-3.5" />
                    {pendingMissed.length} to catch up
                  </div>
                )}
              </div>
            )}
          </div>
          
          {slots.length > 0 && (
            <div className="bg-surface rounded-full h-3 w-full border border-border overflow-hidden shadow-inner">
              <div 
                className="bg-accent h-full transition-all duration-500 ease-out rounded-full"
                style={{ width: `${progressPercent}%` }}
              />
            </div>
          )}
        </header>

        {/* Content: Side-by-side on wide screens */}
        <div className="flex-1 overflow-hidden p-4 sm:p-6 lg:p-8 pt-4 sm:pt-4 lg:pt-6">
          <div className={clsx(
            "flex flex-col h-full gap-5",
            pendingMissed.length > 0 ? "lg:flex-row" : ""
          )}>

            {/* Catch Up Column — only visible if there are missed tasks */}
            {pendingMissed.length > 0 && (
              <div className="lg:w-[340px] xl:w-[380px] flex-shrink-0 flex flex-col">
                <div className="bg-white rounded-2xl border border-red-100 shadow-soft overflow-hidden flex flex-col h-full relative">
                  {/* Red accent bar */}
                  <div className="absolute top-0 left-0 w-1 h-full bg-status-at-risk-text rounded-l-2xl" />
                  
                  <div className="flex items-center justify-between p-4 border-b border-red-100 bg-red-50/30 flex-shrink-0">
                    <h2 className="text-sm font-bold text-status-at-risk-text flex items-center">
                      <AlertCircle className="w-4 h-4 mr-2" />
                      Catch Up
                    </h2>
                    <span className="bg-status-at-risk-bg text-status-at-risk-text text-[10px] px-2 py-0.5 rounded-full font-bold">
                      {pendingMissed.length}
                    </span>
                  </div>
                  
                  <div className="flex-1 overflow-y-auto p-3 space-y-1.5 custom-scrollbar">
                    {pendingMissed.map((slot, index) => (
                      <ChecklistItem 
                        key={`${slot.id}-${index}`} 
                        slot={slot} 
                        onToggle={toggleSlot} 
                        onViewPages={setSelectedSlot}
                        showDate={true}
                      />
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* Schedule Grid Column */}
            <div className="flex-1 bg-white rounded-2xl border border-border shadow-soft overflow-hidden flex flex-col min-h-0 min-w-0 relative">
              <div className="flex items-center p-4 border-b border-border bg-gray-50/80 sticky top-0 z-30 shadow-sm flex-shrink-0">
                <CheckSquare className="w-5 h-5 mr-2 text-text-secondary" />
                <h2 className="text-sm font-bold text-text-primary uppercase tracking-wider">Schedule</h2>
                <span className="ml-auto text-xs text-text-secondary flex items-center">
                  <Clock className="w-3.5 h-3.5 mr-1" />
                  {format(currentTime, 'h:mm a')}
                </span>
              </div>
              
              <div 
                className="flex-1 overflow-y-auto relative custom-scrollbar bg-white"
                ref={containerRef}
              >
                {/* Day Grid Container: 24 hours, 60px per hour */}
                <div className="relative h-[1440px] min-w-[400px] w-full mt-2 mb-8">
                   
                   {/* Hour Lines */}
                   {Array.from({ length: 24 }).map((_, i) => (
                      <div key={i} className="absolute w-full border-t border-border flex items-start" style={{ top: `${i * 60}px`, height: '60px' }}>
                         <div className="w-14 flex-shrink-0 text-right pr-3 -mt-2.5">
                            <span className="text-[10px] sm:text-xs font-medium text-text-secondary bg-white px-1">
                               {i === 0 ? '12 AM' : i < 12 ? `${i} AM` : i === 12 ? '12 PM' : `${i - 12} PM`}
                            </span>
                         </div>
                      </div>
                   ))}

                   {/* Current Time Indicator Line */}
                   <div 
                      className="absolute left-14 right-0 border-t-[2px] border-red-500 z-20 pointer-events-none"
                      style={{ top: `${currentPixels}px` }}
                   >
                      <div className="w-2.5 h-2.5 rounded-full bg-red-500 absolute -left-1.5 -top-[5px] shadow-sm" />
                   </div>

                   {/* Slot Blocks */}
                   {slots.map(slot => {
                      const top = timeToPixels(slot.time_start);
                      const bottom = timeToPixels(slot.time_end);
                      const height = Math.max(bottom - top, 25); // min height

                      return (
                         <div
                           key={slot.id}
                           onClick={() => setSelectedSlot(slot)}
                           className={clsx(
                             "absolute left-14 right-3 rounded-xl p-2.5 border overflow-hidden flex flex-col cursor-pointer transition-all shadow-sm z-10 group",
                             slot.is_completed 
                               ? "bg-gray-50 border-gray-200 opacity-60 hover:opacity-100" 
                               : "bg-accent/10 border-accent/40 hover:border-accent hover:shadow-md hover:-translate-y-[1px]"
                           )}
                           style={{ top: `${top}px`, height: `${height}px` }}
                         >
                            <div className="flex justify-between items-start h-full">
                               <div className="flex flex-col min-w-0 pr-2">
                                 <div className={clsx("font-bold text-sm truncate", slot.is_completed ? "text-text-secondary line-through" : "text-accent-dark")}>
                                   {slot.subject_name}
                                 </div>
                                 <div className={clsx("text-xs truncate font-medium", slot.is_completed ? "text-text-secondary" : "text-text-primary")}>
                                   {slot.topic_title}
                                 </div>
                                 <div className="text-[10px] text-text-secondary mt-0.5 font-medium flex items-center">
                                   {slot.time_start} - {slot.time_end}
                                   {slot.page_from && slot.page_to && (
                                     <span className="ml-2 px-1.5 bg-white/50 rounded-md inline-block text-accent-dark/80">Pages {slot.page_from}-{slot.page_to}</span>
                                   )}
                                 </div>
                               </div>
                               
                               <button 
                                 onClick={(e) => { e.stopPropagation(); toggleSlot(slot.id, slot.is_completed); }}
                                 className="flex-shrink-0 mt-0.5 p-1 rounded-md hover:bg-white/50 transition active:scale-90"
                               >
                                  {slot.is_completed ? (
                                      <CheckSquare className="w-5 h-5 text-accent fill-accent/20" />
                                  ) : (
                                      <div className="w-4 h-4 rounded border-2 border-accent bg-white mt-0.5 mr-0.5" />
                                  )}
                               </button>
                            </div>
                         </div>
                      )
                   })}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Right side panel for PDF viewer */}
      {selectedSlot && (
        <>
          <div className="lg:hidden fixed inset-0 z-50 bg-surface">
            <PageViewer slot={selectedSlot} onClose={() => setSelectedSlot(null)} />
          </div>
          <div className="hidden lg:block lg:w-2/5 min-w-[380px] border-l border-border bg-surface h-full shadow-[-4px_0_15px_-3px_rgba(0,0,0,0.05)] z-40 flex-shrink-0">
            <PageViewer slot={selectedSlot} onClose={() => setSelectedSlot(null)} />
          </div>
        </>
      )}
    </div>
  );
};

export default Today;
