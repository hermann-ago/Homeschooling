import React, { useState, useEffect } from 'react';
import { progressApi } from '../api/progress';
import { TrendingUp, AlertCircle, CheckCircle } from 'lucide-react';
import clsx from 'clsx';
import { format, parseISO } from 'date-fns';
import { getStatusColor, getStatusLabel, getStatusIcon } from '../utils/status';

const Progress = ({ activeChildId }) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!activeChildId) return;
    setLoading(true);
    progressApi.getChildProgress(activeChildId)
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [activeChildId]);

  if (loading || !data) {
    return (
      <div className="flex items-center justify-center p-12 h-full">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-accent"></div>
      </div>
    );
  }

  const StatusIcon = getStatusIcon(data.overall_status);

  return (
    <div className="p-4 sm:p-6 lg:p-8 w-full min-h-full bg-gray-50/50">
      <header className="mb-6 sm:mb-10 lg:flex lg:items-center lg:justify-between">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-text-primary mb-2 flex items-center">
            <TrendingUp className="w-6 h-6 sm:w-8 sm:h-8 mr-3 text-accent" />
            {data.child_name}'s Progress
          </h1>
          <p className="text-text-secondary text-sm sm:text-base">Tracking curriculum completion against the school year deadline.</p>
        </div>
        
        <div className={clsx(
          "mt-6 lg:mt-0 px-5 py-3 rounded-full border flex items-center shadow-sm w-fit",
          getStatusColor(data.overall_status)
        )}>
          {StatusIcon && <StatusIcon className="w-5 h-5" />}
          <span className="ml-2 font-bold tracking-tight">Overall: {getStatusLabel(data.overall_status)}</span>
        </div>
      </header>

      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4 sm:gap-6 mb-6 sm:mb-10">
        <div className="bg-surface p-6 rounded-2xl border border-border shadow-soft text-center">
          <p className="text-sm font-semibold text-text-secondary uppercase tracking-wider mb-2">Total Progress</p>
          <div className="text-4xl font-black text-text-primary">
            {data.overall_progress}%
          </div>
        </div>
        
        {/* Placeholder stats */}
        <div className="bg-surface p-6 rounded-2xl border border-border shadow-soft text-center opacity-75">
          <p className="text-sm font-semibold text-text-secondary uppercase tracking-wider mb-2">Active Subjects</p>
          <div className="text-4xl font-black text-text-primary">
            {data.subjects.length}
          </div>
        </div>
      </div>

      <div className="space-y-6">
        <h2 className="text-xl font-bold text-text-primary border-b border-border pb-2">Subject Breakdown</h2>
        
        {data.subjects.length === 0 ? (
          <p className="text-text-secondary italic">No subjects configured for this child.</p>
        ) : (
          data.subjects.map(subject => (
            <div key={subject.subject_id} className="bg-surface p-6 rounded-2xl border border-border shadow-soft">
              <div className="flex flex-col md:flex-row md:items-center justify-between mb-4">
                <div className="flex items-center">
                  <h3 className="text-lg font-bold text-text-primary mr-4">{subject.subject_name}</h3>
                  <span className={clsx("text-xs font-bold px-2.5 py-1 rounded-full border", getStatusColor(subject.status))}>
                    {getStatusLabel(subject.status)}
                  </span>
                </div>
                <div className="mt-2 md:mt-0 text-right text-sm">
                  <span className="font-semibold text-text-primary">{subject.completed_pages}</span> 
                  <span className="text-text-secondary"> / {subject.total_pages} pages</span>
                </div>
              </div>
              
              <div className="w-full bg-gray-100 rounded-full h-4 mb-3 border border-gray-200 overflow-hidden relative">
                <div 
                  className={clsx(
                    "h-4 rounded-full transition-all duration-1000",
                    subject.status === 'at_risk' ? 'bg-red-400' : 
                    subject.status === 'behind' ? 'bg-yellow-400' : 'bg-accent'
                  )} 
                  style={{ width: `${subject.progress_percent}%` }}
                />
              </div>
              
              <div className="flex justify-between text-xs font-medium">
                <span className="text-text-secondary">{subject.progress_percent}% Complete</span>
                {subject.projected_finish_date ? (
                  <span className={clsx(
                    subject.status === 'at_risk' ? 'text-red-500 font-bold' : 'text-text-secondary'
                  )}>
                    Projected finish: {format(parseISO(subject.projected_finish_date), 'MMM d, yyyy')}
                  </span>
                ) : (
                  <span className="text-text-secondary">Insufficient data for projection</span>
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default Progress;
