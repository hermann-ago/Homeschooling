import React, { useState, useEffect } from 'react';
import { checklistApi } from '../api/checklist';
import ChecklistItem from '../components/ChecklistItem';
import { format, parseISO, isSameDay } from 'date-fns';

const Weekly = ({ activeChildId }) => {
  const [slots, setSlots] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!activeChildId) return;

    setLoading(true);
    checklistApi.getWeek(activeChildId)
      .then(setSlots)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [activeChildId]);

  const toggleSlot = async (id, isCompleted) => {
    try {
      if (isCompleted) {
        await checklistApi.uncompleteSlot(id);
      } else {
        await checklistApi.completeSlot(id);
      }
      // Optimistically update
      setSlots(slots.map(s => s.id === id ? { ...s, is_completed: !isCompleted } : s));
    } catch (error) {
      console.error('Failed to toggle slot', error);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center p-12">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-accent"></div>
      </div>
    );
  }

  // Create a grid by day
  const slotsByDate = slots.reduce((acc, slot) => {
    if (!acc[slot.date]) acc[slot.date] = [];
    acc[slot.date].push(slot);
    return acc;
  }, {});

  const dates = Object.keys(slotsByDate).sort();

  return (
    <div className="p-4 sm:p-6 lg:p-8 w-full min-h-full bg-gray-50/50">
      <header className="mb-6 sm:mb-10">
        <h1 className="text-2xl sm:text-3xl font-bold text-text-primary mb-2">Weekly Overview</h1>
        <p className="text-text-secondary text-sm sm:text-base">
          Track the full week's curriculum assignments.
        </p>
      </header>

      {dates.length === 0 ? (
        <div className="bg-surface rounded-2xl border border-border p-12 text-center shadow-soft max-w-2xl">
          <h3 className="text-lg font-medium text-text-primary mb-1">No schedule found</h3>
          <p className="text-text-secondary">Please check your calendar settings or time windows.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4 sm:gap-6">
          {dates.map((dateString) => {
            const daySlots = slotsByDate[dateString];
            const dateObj = parseISO(dateString);
            const isCurrentDay = isSameDay(dateObj, new Date());
            
            return (
              <div 
                key={dateString} 
                className={`flex flex-col rounded-2xl overflow-hidden shadow-soft border ${
                  isCurrentDay ? 'border-accent ring-1 ring-accent/20' : 'border-border bg-surface'
                }`}
              >
                <div className={`p-4 text-center ${isCurrentDay ? 'bg-accent text-white' : 'bg-gray-50 text-text-primary border-b border-border'}`}>
                  <p className="text-xs uppercase tracking-widest font-semibold opacity-80">{format(dateObj, 'EEE')}</p>
                  <p className="text-xl font-bold">{format(dateObj, 'MMM d')}</p>
                </div>
                <div className="p-4 flex-1 bg-surface overflow-y-auto max-h-[600px] custom-scrollbar">
                  {daySlots.map(slot => (
                    <div key={slot.id} className="mb-3 last:mb-0">
                      <ChecklistItem slot={slot} onToggle={toggleSlot} />
                    </div>
                  ))}
                  {daySlots.length === 0 && (
                    <p className="text-sm text-text-secondary text-center py-4 italic">No blocks scheduling.</p>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default Weekly;
