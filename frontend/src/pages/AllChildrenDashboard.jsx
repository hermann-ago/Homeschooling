import React, { useState, useEffect } from 'react';
import { progressApi } from '../api/progress';
import { checklistApi } from '../api/checklist';
import {
  Users, TrendingUp, CheckSquare, ChevronRight, BookOpen,
  AlertCircle, Target
} from 'lucide-react';
import clsx from 'clsx';
import { format, parseISO } from 'date-fns';
import { getStatusColor, getStatusLabel } from '../utils/status';

const AllChildrenDashboard = ({ children, setActiveChildId }) => {
  const [familyProgress, setFamilyProgress] = useState(null);
  const [childProgressDetails, setChildProgressDetails] = useState({});
  const [todayCounts, setTodayCounts] = useState({});
  const [missedCounts, setMissedCounts] = useState({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const progress = await progressApi.getFamilyOverview();
        setFamilyProgress(progress);

        const detailsMap = {};
        const counts = {};
        const missed = {};
        for (const child of children) {
          try {
            const detail = await progressApi.getChildProgress(child.id);
            detailsMap[child.id] = detail;
          } catch { detailsMap[child.id] = null; }
          try {
            const todaySlots = await checklistApi.getToday(child.id);
            const completed = todaySlots.filter(s => s.is_completed).length;
            counts[child.id] = { total: todaySlots.length, completed };
          } catch { counts[child.id] = { total: 0, completed: 0 }; }
          try {
            const missedSlots = await checklistApi.getMissed(child.id);
            missed[child.id] = missedSlots.filter(s => !s.is_completed).length;
          } catch { missed[child.id] = 0; }
        }
        setChildProgressDetails(detailsMap);
        setTodayCounts(counts);
        setMissedCounts(missed);
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    };
    if (children.length > 0) load();
  }, [children]);

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

  const totalTasks = Object.values(todayCounts).reduce((sum, c) => sum + c.total, 0);
  const completedTasks = Object.values(todayCounts).reduce((sum, c) => sum + c.completed, 0);
  const totalMissed = Object.values(missedCounts).reduce((sum, n) => sum + n, 0);

  return (
    <div className="min-h-full bg-gray-50/50">
      <div className="p-4 sm:p-6 lg:p-8 w-full">

        {/* Header */}
        <header className="mb-6 lg:mb-8">
          <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-4">
            <div>
              <h1 className="text-2xl sm:text-3xl font-bold text-text-primary mb-1 flex items-center">
                <Users className="w-7 h-7 sm:w-8 sm:h-8 mr-3 text-accent" />
                Family Dashboard
              </h1>
              <p className="text-text-secondary text-sm sm:text-base">
                {format(new Date(), 'EEEE, MMMM do, yyyy')}
              </p>
            </div>

            <div className="flex gap-3 flex-wrap">
              <div className="flex items-center gap-2 bg-white border border-border rounded-xl px-4 py-2.5 shadow-sm">
                <div className="w-8 h-8 bg-accent/10 rounded-lg flex items-center justify-center">
                  <Target className="w-4 h-4 text-accent" />
                </div>
                <div>
                  <p className="text-[10px] font-semibold text-text-secondary uppercase tracking-wider">Today</p>
                  <p className="text-sm font-bold text-text-primary">{completedTasks}/{totalTasks} done</p>
                </div>
              </div>
              {totalMissed > 0 && (
                <div className="flex items-center gap-2 bg-white border border-red-100 rounded-xl px-4 py-2.5 shadow-sm">
                  <div className="w-8 h-8 bg-red-50 rounded-lg flex items-center justify-center">
                    <AlertCircle className="w-4 h-4 text-red-500" />
                  </div>
                  <div>
                    <p className="text-[10px] font-semibold text-red-400 uppercase tracking-wider">Catch Up</p>
                    <p className="text-sm font-bold text-red-600">{totalMissed} missed</p>
                  </div>
                </div>
              )}
            </div>
          </div>
        </header>

        {/* Children Cards — Side-by-side vertical columns */}
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-5">
          {children.map(child => {
            const progress = childProgressMap[child.id];
            const details = childProgressDetails[child.id];
            const todayCount = todayCounts[child.id] || { total: 0, completed: 0 };
            const missedCount = missedCounts[child.id] || 0;
            const progressPercent = progress?.overall_progress || 0;

            return (
              <div
                key={child.id}
                className="bg-white border border-border rounded-2xl shadow-soft overflow-hidden transition-all duration-300 flex flex-col hover:shadow-md group"
              >
                {/* Colored header bar */}
                <div className="h-1.5 w-full" style={{ backgroundColor: child.color }} />

                <div className="p-5 flex flex-col flex-1">
                  {/* Child identity */}
                  <div className="flex items-center gap-3 mb-4">
                    <div
                      className="w-11 h-11 rounded-xl flex items-center justify-center text-white text-lg font-bold shadow-sm flex-shrink-0"
                      style={{ backgroundColor: child.color }}
                    >
                      {child.name.charAt(0)}
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <h2 className="text-base font-bold text-text-primary leading-tight truncate">{child.name}</h2>
                        {progress && (
                          <span className={clsx("text-[9px] font-bold px-1.5 py-0.5 rounded-full border whitespace-nowrap", getStatusColor(progress.overall_status))}>
                            {getStatusLabel(progress.overall_status)}
                          </span>
                        )}
                      </div>
                      <p className="text-text-secondary text-xs">{child.grade_year || 'No grade'}</p>
                    </div>
                  </div>

                  {/* Year progress */}
                  <div className="mb-4">
                    <div className="flex justify-between text-xs mb-1.5">
                      <span className="font-medium text-text-secondary flex items-center">
                        <TrendingUp className="w-3.5 h-3.5 mr-1" />
                        Year Progress
                      </span>
                      <span className="font-bold" style={{ color: child.color }}>{progressPercent}%</span>
                    </div>
                    <div className="w-full bg-gray-100 rounded-full h-2.5 border border-gray-200 overflow-hidden">
                      <div
                        className="h-2.5 rounded-full transition-all duration-1000"
                        style={{ width: `${progressPercent}%`, backgroundColor: child.color }}
                      />
                    </div>
                  </div>

                  {/* Today + Catch Up stats row */}
                  <div className="flex gap-2 mb-4">
                    <div className="flex-1 bg-gray-50 rounded-xl p-2.5 border border-gray-100 text-center">
                      <p className="text-[10px] text-text-secondary font-medium mb-0.5">Today</p>
                      <p className="text-sm font-bold text-text-primary">
                        {todayCount.completed}/{todayCount.total}
                      </p>
                      {todayCount.total > 0 && (
                        <div className="w-full bg-gray-200 rounded-full h-1 mt-1.5 overflow-hidden">
                          <div
                            className="h-1 rounded-full transition-all"
                            style={{
                              width: `${(todayCount.completed / todayCount.total) * 100}%`,
                              backgroundColor: child.color
                            }}
                          />
                        </div>
                      )}
                    </div>
                    {missedCount > 0 && (
                      <div className="flex-1 bg-red-50/60 rounded-xl p-2.5 border border-red-100 text-center">
                        <p className="text-[10px] text-red-400 font-medium mb-0.5">Catch Up</p>
                        <p className="text-sm font-bold text-red-600">{missedCount}</p>
                      </div>
                    )}
                  </div>

                  {/* Subject breakdown */}
                  <div className="flex-1">
                    {details && details.subjects.length > 0 ? (
                      <div className="space-y-2">
                        {details.subjects.map(subject => (
                          <div key={subject.subject_id} className="group/subj">
                            <div className="flex items-center justify-between mb-1">
                              <div className="flex items-center gap-1.5 min-w-0">
                                <span className={clsx(
                                  "w-1.5 h-1.5 rounded-full flex-shrink-0",
                                  subject.status === 'on_track' ? 'bg-green-400' :
                                  subject.status === 'behind' ? 'bg-yellow-400' : 'bg-red-400'
                                )} />
                                <p className="text-xs font-semibold text-text-primary truncate">{subject.subject_name}</p>
                              </div>
                              <span className="text-[10px] text-text-secondary font-medium ml-2 whitespace-nowrap">{subject.progress_percent}%</span>
                            </div>
                            <div className="w-full bg-gray-100 rounded-full h-1.5 overflow-hidden">
                              <div
                                className="h-1.5 rounded-full transition-all duration-700"
                                style={{ width: `${subject.progress_percent}%`, backgroundColor: child.color }}
                              />
                            </div>
                            {subject.projected_finish_date && (
                              <p className={clsx(
                                "text-[9px] mt-0.5 text-right",
                                subject.status === 'at_risk' ? 'text-red-500 font-medium' : 'text-text-secondary'
                              )}>
                                Est. {format(parseISO(subject.projected_finish_date), 'MMM d')}
                              </p>
                            )}
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-xs text-text-secondary italic">No subjects configured.</p>
                    )}
                  </div>
                </div>

                {/* Footer link */}
                <button
                  onClick={() => setActiveChildId(child.id)}
                  className="w-full py-2.5 border-t border-border text-xs font-semibold text-text-secondary hover:text-accent hover:bg-accent/5 transition-colors flex items-center justify-center gap-1.5 group/btn mt-auto"
                >
                  Go to {child.name}
                  <ChevronRight className="w-3.5 h-3.5 group-hover/btn:translate-x-0.5 transition-transform" />
                </button>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

export default AllChildrenDashboard;
