import React, { useState, useEffect } from 'react';
import { calendarApi } from '../api/calendar';
import { schedulerApi } from '../api/scheduler';
import { format, startOfMonth, endOfMonth, eachDayOfInterval, isSameMonth, isSameDay, startOfWeek, endOfWeek, addMonths, subMonths } from 'date-fns';
import { ChevronLeft, ChevronRight, Ban, RefreshCw, Calendar as CalendarIcon, Umbrella, ShieldAlert, CheckCircle2 } from 'lucide-react';
import clsx from 'clsx';
import InputDialog from '../components/InputDialog';

const Calendar = ({ activeChildId }) => {
  const [currentDate, setCurrentDate] = useState(new Date());
  const [blockedDays, setBlockedDays] = useState([]);
  const [scheduledSlots, setScheduledSlots] = useState([]);
  const [recalculating, setRecalculating] = useState(false);
  const [loading, setLoading] = useState(true);
  const [blockPrompt, setBlockPrompt] = useState({ open: false, date: null });
  const [notification, setNotification] = useState(null);

  const loadData = async () => {
    setLoading(true);
    try {
      const monthStart = startOfMonth(currentDate);
      const monthEnd = endOfMonth(currentDate);
      const startDate = format(startOfWeek(monthStart, { weekStartsOn: 0 }), 'yyyy-MM-dd');
      const endDate = format(endOfWeek(monthEnd, { weekStartsOn: 0 }), 'yyyy-MM-dd');

      const [days, slots] = await Promise.all([
        calendarApi.getBlockedDays({ child_id: activeChildId, start_date: startDate, end_date: endDate }),
        schedulerApi.getSchedule(activeChildId, { start_date: startDate, end_date: endDate }),
      ]);
      setBlockedDays(days);
      setScheduledSlots(slots);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [currentDate, activeChildId]);

  const handleRecalculate = async () => {
    setRecalculating(true);
    try {
      const result = await schedulerApi.recalculate(activeChildId);
      if (result.warnings && result.warnings.length > 0) {
        setNotification(result.warnings.map(w => w.message).join('\n'));
      } else {
        setNotification(`Schedule recalculated successfully! ${result.slots_created} slots created.`);
      }
      await loadData();
    } catch (error) {
      setNotification(`Failed to recalculate: ${error.message}`);
    } finally {
      setRecalculating(false);
    }
  };

  const handleDayClick = async (date) => {
    const dateStr = format(date, 'yyyy-MM-dd');
    const existing = blockedDays.find(b => b.date === dateStr);

    try {
      if (existing) {
        await calendarApi.deleteBlockedDay(existing.id);
        loadData();
      } else {
        // Open the InputDialog instead of window.prompt
        setBlockPrompt({ open: true, date: dateStr });
      }
    } catch (error) {
      console.error(error);
    }
  };

  const handleBlockSubmit = async (text) => {
    // If text matches holiday/sick, use that as type, otherwise use 'custom' with the text as note
    const lowerText = text.toLowerCase();
    let type = 'custom';
    let note = text;
    
    if (lowerText === 'holiday') {
        type = 'holiday';
        note = null;
    } else if (lowerText === 'sick') {
        type = 'sick';
        note = null;
    }

    try {
      await calendarApi.createBlockedDay({
        date: blockPrompt.date,
        block_type: type,
        note: note,
        child_id: activeChildId // Make it child-specific by default
      });
      loadData();
    } catch (error) {
      console.error(error);
      setNotification("Failed to block day: " + error.message);
    }
    setBlockPrompt({ open: false, date: null });
  };

  // Group slots by date 
  const slotsByDate = {};
  scheduledSlots.forEach(slot => {
    if (!slotsByDate[slot.date]) slotsByDate[slot.date] = [];
    slotsByDate[slot.date].push(slot);
  });

  const monthStart = startOfMonth(currentDate);
  const monthEnd = endOfMonth(currentDate);
  const startDate = startOfWeek(monthStart, { weekStartsOn: 0 });
  const endDate = endOfWeek(monthEnd, { weekStartsOn: 0 });

  const rows = [];
  let days = [];
  let day = startDate;

  while (day <= endDate) {
    for (let i = 0; i < 7; i++) {
      const cloneDay = new Date(day);
      const dateStr = format(day, 'yyyy-MM-dd');
      const blocked = blockedDays.find(b => b.date === dateStr);
      const daySlots = slotsByDate[dateStr] || [];
      
      days.push(
        <div 
          key={day.toString()}
          onClick={() => handleDayClick(cloneDay)}
          className={clsx(
            "min-h-[70px] sm:min-h-[110px] border border-border p-1 sm:p-1.5 transition-all cursor-pointer relative group flex flex-col",
            !isSameMonth(day, monthStart) ? "bg-gray-50 text-gray-400" : "bg-white",
            isSameDay(day, new Date()) ? "ring-2 ring-inset ring-accent" : "",
            blocked ? "bg-red-50" : "hover:bg-gray-50"
          )}
        >
          <span className={clsx(
            "text-xs font-semibold mb-1", 
            isSameDay(day, new Date()) ? "text-accent" : "text-text-primary",
            !isSameMonth(day, monthStart) && "opacity-50"
          )}>
            {format(day, 'd')}
          </span>
          
          {blocked && (
            <div className="absolute inset-0 flex flex-col items-center justify-center opacity-80 z-10">
              {blocked.block_type === 'holiday' ? <Umbrella className="w-5 h-5 text-orange-500 mb-0.5" /> :
               blocked.block_type === 'sick' ? <ShieldAlert className="w-5 h-5 text-red-500 mb-0.5" /> :
               <Ban className="w-5 h-5 text-gray-500 mb-0.5" />}
              <span className="text-[9px] uppercase font-bold text-text-secondary tracking-wider text-center px-1 truncate w-full">
                {blocked.note || blocked.block_type}
              </span>
            </div>
          )}
          
          {/* Activity chips */}
          {!blocked && daySlots.length > 0 && (
            <div className="flex-1 overflow-hidden space-y-0.5">
              {daySlots.slice(0, 3).map(slot => (
                <div 
                  key={slot.id} 
                  className={clsx(
                    "text-[10px] leading-tight px-1.5 py-0.5 rounded truncate flex items-center",
                    slot.is_completed 
                      ? "bg-green-50 text-green-700 line-through opacity-70" 
                      : "bg-accent-light text-accent"
                  )}
                  title={`${slot.subject_name}: ${slot.topic_title || 'Study'} (p${slot.page_from}-${slot.page_to})`}
                >
                  {slot.is_completed && <CheckCircle2 className="w-2.5 h-2.5 mr-0.5 flex-shrink-0" />}
                  <span className="truncate">{slot.subject_name}</span>
                </div>
              ))}
              {daySlots.length > 3 && (
                <div className="text-[9px] text-text-secondary font-medium px-1.5">
                  +{daySlots.length - 3} more
                </div>
              )}
            </div>
          )}
          
          {/* Hover overlay for blocking — only show when no activities are visible */}
          {!blocked && daySlots.length === 0 && (
            <div className="absolute inset-0 bg-black/5 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
              <span className="bg-surface px-2 py-1 rounded shadow-sm text-[10px] font-medium text-text-primary">
                Block Day
              </span>
            </div>
          )}
        </div>
      );
      day = new Date(day.setDate(day.getDate() + 1));
    }
    rows.push(
      <div className="grid grid-cols-7" key={day.toString()}>
        {days}
      </div>
    );
    days = [];
  }

  return (
    <div className="p-4 sm:p-6 lg:p-8 w-full min-h-full bg-gray-50/50">
      <header className="mb-6 sm:mb-10 flex flex-col sm:flex-row justify-between sm:items-end gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-text-primary mb-2 flex items-center">
            <CalendarIcon className="w-6 h-6 sm:w-8 sm:h-8 mr-3 text-accent" />
            Calendar & Schedule
          </h1>
          <p className="text-text-secondary text-sm sm:text-base">Manage holidays, sick days, and view the study schedule.</p>
        </div>
        
        <button 
          onClick={handleRecalculate}
          disabled={recalculating}
          className="flex items-center bg-accent text-white px-4 sm:px-5 py-2.5 rounded-xl font-medium shadow-sm hover:bg-accent-hover transition disabled:opacity-50 self-start sm:self-auto text-sm sm:text-base"
        >
          <RefreshCw className={clsx("w-4 h-4 sm:w-5 sm:h-5 mr-2", recalculating && "animate-spin")} />
          {recalculating ? 'Recalculating...' : 'Recalculate Schedule'}
        </button>
      </header>

      <div className="bg-surface border border-border rounded-2xl shadow-soft overflow-hidden">
        <div className="flex items-center justify-between p-6 border-b border-border">
          <h2 className="text-xl font-bold text-text-primary">
            {format(currentDate, 'MMMM yyyy')}
          </h2>
          <div className="flex space-x-2">
            <button onClick={() => setCurrentDate(subMonths(currentDate, 1))} className="p-2 hover:bg-gray-100 rounded-lg text-text-secondary transition">
              <ChevronLeft className="w-5 h-5" />
            </button>
            <button onClick={() => setCurrentDate(new Date())} className="px-3 text-sm font-medium hover:bg-gray-100 rounded-lg text-text-secondary transition">
              Today
            </button>
            <button onClick={() => setCurrentDate(addMonths(currentDate, 1))} className="p-2 hover:bg-gray-100 rounded-lg text-text-secondary transition">
              <ChevronRight className="w-5 h-5" />
            </button>
          </div>
        </div>
        
        <div className="grid grid-cols-7 border-b border-border bg-gray-50">
          {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map((d) => (
            <div key={d} className="py-3 text-center text-xs font-semibold text-text-secondary uppercase tracking-wider">{d}</div>
          ))}
        </div>
        
        <div className="bg-surface relative">
          {loading && (
            <div className="absolute inset-0 bg-white/50 backdrop-blur-sm z-10 flex items-center justify-center">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-accent"></div>
            </div>
          )}
          {rows}
        </div>
      </div>

      {/* Block type input dialog */}
      <InputDialog
        open={blockPrompt.open}
        title="Block Day"
        label="Reason (e.g. holiday, sick, or Special Event)"
        placeholder="Holiday"
        defaultValue="Holiday"
        submitLabel="Block Day"
        onSubmit={handleBlockSubmit}
        onCancel={() => setBlockPrompt({ open: false, date: null })}
      />

      {/* Notification toast */}
      {notification && (
        <div className="fixed bottom-6 right-6 z-50 max-w-sm bg-surface border border-border rounded-2xl shadow-2xl p-4 animate-in slide-in-from-bottom-5 duration-300">
          <p className="text-sm text-text-primary whitespace-pre-line">{notification}</p>
          <button 
            onClick={() => setNotification(null)}
            className="mt-2 text-xs font-medium text-accent hover:text-accent-hover transition"
          >
            Dismiss
          </button>
        </div>
      )}
    </div>
  );
};

export default Calendar;
