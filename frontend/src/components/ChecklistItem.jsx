import React, { useState, useEffect } from 'react';
import { checklistApi } from '../api/checklist';
import { format, isToday, isPast, parseISO } from 'date-fns';
import { CheckCircle2, Circle, AlertCircle, CalendarIcon, BookOpen } from 'lucide-react';
import clsx from 'clsx';

const ChecklistItem = ({ slot, onToggle, onViewPages, showDate = false }) => {
  const isMissed = !slot.is_completed && isPast(parseISO(slot.date)) && !isToday(parseISO(slot.date));
  
  return (
    <div 
      className={clsx(
        "group flex items-center p-4 rounded-xl border transition-all duration-200 cursor-pointer mb-3 shadow-sm hover:shadow-md",
        slot.is_completed ? "bg-accent-light/50 border-accent/20" : "bg-surface border-border",
        isMissed && !slot.is_completed ? "border-status-at-risk-text/30 bg-status-at-risk-bg/30" : ""
      )}
      onClick={() => onToggle(slot.id, slot.is_completed)}
    >
      <button className="mr-4 flex-shrink-0 focus:outline-none transition-transform active:scale-90">
        {slot.is_completed ? (
          <CheckCircle2 className="w-8 h-8 text-accent fill-accent/20" />
        ) : (
          <Circle className={clsx("w-8 h-8", isMissed ? "text-status-at-risk-text" : "text-gray-300 group-hover:text-accent/50")} />
        )}
      </button>
      
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between mb-1">
          <p className={clsx(
            "font-semibold text-lg truncate transition-colors",
            slot.is_completed ? "text-text-secondary line-through" : "text-text-primary"
          )}>
            {slot.subject_name}
          </p>
          <span className="text-xs font-medium text-text-secondary bg-gray-100 px-2 py-1 rounded-full whitespace-nowrap ml-2">
            {slot.time_start} - {slot.time_end}
          </span>
        </div>
        
        {slot.topic_title ? (
          <p className={clsx(
            "text-sm truncate",
            slot.is_completed ? "text-text-secondary/70" : "text-text-secondary"
          )}>
            {slot.topic_title}
          </p>
        ) : (
          <p className="text-sm text-text-secondary italic">Unassigned time block</p>
        )}
        
        <div className="flex items-center mt-2 space-x-3">
          {(slot.page_from !== null && slot.page_to !== null) && (
            <span className={clsx(
              "text-xs font-medium px-2 py-0.5 rounded",
              slot.is_completed ? "bg-gray-100 text-gray-500" : "bg-accent/10 text-accent"
            )}>
              Pages {slot.page_from} - {slot.page_to}
            </span>
          )}
          
          {slot.pdf_path && onViewPages && (
            <button 
              onClick={(e) => { e.stopPropagation(); onViewPages(slot); }}
              className="group/btn flex items-center text-xs font-medium text-text-secondary hover:text-accent transition-colors px-2 py-0.5 rounded bg-gray-50 hover:bg-accent/10"
              title="View pages"
            >
              <BookOpen className="w-3.5 h-3.5 mr-1" />
              View Pages
            </button>
          )}
          
          {showDate && (
             <span className="text-xs text-text-secondary flex items-center">
                <CalendarIcon className="w-3 h-3 mr-1" />
                {format(parseISO(slot.date), 'MMM d, yyyy')}
             </span>
          )}
          
          {isMissed && !slot.is_completed && !showDate && (
             <span className="text-xs text-status-at-risk-text flex items-center font-medium bg-status-at-risk-bg px-2 py-0.5 rounded flex items-center">
                <AlertCircle className="w-3 h-3 mr-1" />
                Missed
             </span>
          )}
        </div>
      </div>
    </div>
  );
};

export default ChecklistItem;
