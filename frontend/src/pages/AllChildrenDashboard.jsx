import React, { useState, useEffect, useRef } from 'react';
import { progressApi } from '../api/progress';
import { checklistApi } from '../api/checklist';
import { Users, TrendingUp, CheckSquare, ChevronRight, BookOpen } from 'lucide-react';
import PageViewer from '../components/PageViewer';
import clsx from 'clsx';
import { getStatusColor, getStatusLabel } from '../utils/status';

const AllChildrenDashboard = ({ children, setActiveChildId }) => {
  const [familyProgress, setFamilyProgress] = useState(null);
  const [todayCounts, setTodayCounts] = useState({});
  const [allSlots, setAllSlots] = useState({}); // { childId: [slots] }
  const [loading, setLoading] = useState(true);
  const [currentTime, setCurrentTime] = useState(new Date());
  const [selectedSlot, setSelectedSlot] = useState(null);
  
  const containerRef = useRef(null);
  const scrollInitialized = useRef(false);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const progress = await progressApi.getFamilyOverview();
        setFamilyProgress(progress);

        // Load today's tasks for each child
        const counts = {};
        const slotsMap = {};
        for (const child of children) {
          try {
            const todaySlots = await checklistApi.getToday(child.id);
            const completed = todaySlots.filter(s => s.is_completed).length;
            counts[child.id] = { total: todaySlots.length, completed };
            slotsMap[child.id] = todaySlots;
          } catch {
            counts[child.id] = { total: 0, completed: 0 };
            slotsMap[child.id] = [];
          }
        }
        setTodayCounts(counts);
        setAllSlots(slotsMap);
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    };
    if (children.length > 0) load();
  }, [children]);

  useEffect(() => {
    const interval = setInterval(() => {
      setCurrentTime(new Date());
    }, 60000);
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
      
      // Opt. update 
      setAllSlots(prev => ({
        ...prev,
        [childId]: prev[childId].map(s => s.id === slotId ? { ...s, is_completed: !isCompleted } : s)
      }));
      setTodayCounts(prev => {
        const count = prev[childId] || { total: 0, completed: 0 };
        return {
           ...prev,
           [childId]: { ...count, completed: count.completed + (isCompleted ? -1 : 1) }
        };
      });
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

  const childProgressMap = {};
  if (familyProgress) {
    familyProgress.children.forEach(cp => { childProgressMap[cp.child_id] = cp; });
  }

  const currentHour = currentTime.getHours();
  const currentMinute = currentTime.getMinutes();
  const currentPixels = currentHour * 60 + currentMinute;

  return (
    <div className="flex h-full w-full overflow-hidden bg-gray-50/50">
      <div className={clsx("p-4 sm:p-8 flex flex-col w-full transition-all duration-300", selectedSlot ? "lg:w-3/5 lg:max-w-none lg:pr-8" : "max-w-6xl mx-auto")}>
        
        <header className="mb-6 flex-shrink-0">
          <h1 className="text-2xl sm:text-3xl font-bold text-text-primary mb-2 flex items-center">
            <Users className="w-6 h-6 sm:w-8 sm:h-8 mr-3 text-accent" />
            Family Overview
          </h1>
          <p className="text-text-secondary text-sm sm:text-base">See all your children's progress and today's tasks at a glance.</p>
        </header>

        {/* Progress Cards Row */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:flex lg:flex-row gap-4 sm:gap-6 flex-wrap shrink-0">
        {children.map(child => {
          const progress = childProgressMap[child.id];
          const todayCount = todayCounts[child.id] || { total: 0, completed: 0 };
          const progressPercent = progress?.overall_progress || 0;

          return (
            <div
              key={child.id}
              onClick={() => setActiveChildId(child.id)}
              className="bg-surface border border-border rounded-2xl shadow-soft overflow-hidden cursor-pointer hover:shadow-md transition-all duration-200 group"
            >
              {/* Colored header bar */}
              <div 
                className="h-2 w-full transition-all"
                style={{ backgroundColor: child.color }}
              />
              
              <div className="p-4">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center">
                    <div 
                      className="w-10 h-10 rounded-full flex items-center justify-center text-white text-lg font-bold mr-3 shadow-sm"
                      style={{ backgroundColor: child.color }}
                    >
                      {child.name.charAt(0)}
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="text-base font-bold text-text-primary leading-tight">{child.name}</h3>
                        {progress && (
                          <span className={clsx("text-[10px] font-bold px-2 py-0.5 rounded-full border", getStatusColor(progress.overall_status))}>
                            {getStatusLabel(progress.overall_status)}
                          </span>
                        )}
                      </div>
                      <p className="text-text-secondary text-xs">{child.grade_year || 'No grade'}</p>
                    </div>
                  </div>
                  <ChevronRight className="w-4 h-4 text-gray-300 group-hover:text-text-secondary transition" />
                </div>

                <div className="flex gap-4 items-center mb-1">
                  {/* Progress bar */}
                  <div className="flex-1">
                    <div className="flex justify-between text-xs mb-1">
                      <span className="font-semibold text-text-primary flex items-center">
                        <TrendingUp className="w-3.5 h-3.5 mr-1" />
                        Overall Yr
                      </span>
                      <span className="font-bold text-[10px]" style={{ color: child.color }}>
                        {progressPercent}%
                      </span>
                    </div>
                    <div className="w-full bg-gray-100 rounded-full h-2 border border-gray-200 overflow-hidden">
                      <div 
                        className="h-2 rounded-full transition-all duration-1000"
                        style={{ width: `${progressPercent}%`, backgroundColor: child.color }}
                      />
                    </div>
                  </div>

                  {/* Today's tasks */}
                  <div className="flex-[0.8] border-l border-border pl-4">
                    <div className="flex items-center justify-between text-xs mb-1">
                      <span className="font-medium text-text-secondary flex items-center">
                        <CheckSquare className="w-3.5 h-3.5 mr-1" />
                        Today
                      </span>
                      <span className="font-bold text-text-primary text-[10px]">
                        {todayCount.completed}/{todayCount.total}
                      </span>
                    </div>
                    <div className="w-full bg-gray-100 rounded-full h-2 overflow-hidden">
                      <div 
                        className="h-2 rounded-full transition-all"
                        style={{
                          width: `${todayCount.total > 0 ? (todayCount.completed / todayCount.total) * 100 : 0}%`,
                          backgroundColor: child.color
                        }}
                      />
                    </div>
                  </div>
                </div>
              </div>
            </div>
          );
        })}
        </div>

        {/* Master Schedule Grid */}
        <div className="mt-8 flex-1 bg-white rounded-2xl border border-border shadow-soft overflow-hidden flex flex-col min-h-[500px] relative">
           
           <div className="flex items-center border-b border-border bg-gray-50/80 sticky top-0 z-30 shadow-sm">
               <div className="w-12 sm:w-16 flex-shrink-0 border-r border-border border-transparent"></div>
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
              <div className="relative h-[1440px] min-w-[600px] w-full flex">
                  {/* Hour lines (background) */}
                  <div className="absolute inset-0 z-0">
                      {Array.from({ length: 24 }).map((_, i) => (
                         <div key={i} className="absolute w-full border-t border-border" style={{ top: `${i * 60}px`, height: '60px' }}></div>
                      ))}
                  </div>

                  {/* Hour labels (left col) */}
                  <div className="w-12 sm:w-16 flex-shrink-0 relative z-20 border-r border-border bg-white/60 backdrop-blur-sm">
                      {Array.from({ length: 24 }).map((_, i) => (
                         <div key={i} className="absolute w-full text-right pr-2 sm:pr-3" style={{ top: `${i * 60 - 8}px` }}>
                            <span className="text-[10px] sm:text-xs font-medium text-text-secondary bg-white px-1">
                               {i === 0 ? '12 AM' : i < 12 ? `${i} AM` : i === 12 ? '12 PM' : `${i - 12} PM`}
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
                                    "absolute left-1 right-1 sm:left-2 sm:right-2 rounded-lg p-1 sm:p-2 border overflow-hidden flex flex-col cursor-pointer transition-all shadow-sm group",
                                    slot.is_completed 
                                      ? "bg-gray-50 border-gray-200 opacity-60 hover:opacity-100" 
                                      : "bg-white hover:shadow-md hover:-translate-y-[1px]"
                                  )}
                                  style={{ 
                                    top: `${top}px`, 
                                    height: `${height}px`,
                                    borderColor: slot.is_completed ? undefined : child.color,
                                    backgroundColor: slot.is_completed ? undefined : `${child.color}15`
                                  }}
                               >
                                  <div className="flex justify-between items-start h-full">
                                     <div className="flex flex-col min-w-0 pr-1">
                                       <div className={clsx("font-bold text-[10px] sm:text-xs truncate", slot.is_completed ? "text-text-secondary line-through" : "text-text-primary")}>
                                         {slot.subject_name}
                                       </div>
                                       <div className={clsx("text-[9px] sm:text-[10px] truncate font-medium", slot.is_completed ? "text-text-secondary" : "text-text-secondary")}>
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
                            )
                         })}
                     </div>
                  ))}

                  {/* Universal Red Line Overlay */}
                  <div 
                     className="absolute left-12 sm:left-16 right-0 border-t-[2px] border-red-500 z-30 pointer-events-none"
                     style={{ top: `${currentPixels}px` }}
                  >
                     <div className="w-2.5 h-2.5 rounded-full bg-red-500 absolute -left-1.5 -top-[5px] shadow-sm" />
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

export default AllChildrenDashboard;
