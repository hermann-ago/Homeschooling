import React, { useState, useEffect } from 'react';
import { childrenApi } from '../api/children';
import { calendarApi } from '../api/calendar';
import { timeWindowsApi } from '../api/timeWindows';
import { User, Clock, Calendar as CalendarIcon, Save, X, Plus, Trash2 } from 'lucide-react';
import clsx from 'clsx';

const Settings = ({ activeChildId }) => {
  const [children, setChildren] = useState([]);
  const [schoolYear, setSchoolYear] = useState({ start_date: '', end_date: '' });
  const [savingSettings, setSavingSettings] = useState(false);
  
  // Modal states
  const [isChildModalOpen, setIsChildModalOpen] = useState(false);
  const [editingChild, setEditingChild] = useState(null);
  
  const [isTwModalOpen, setIsTwModalOpen] = useState(false);
  const [activeChildForTw, setActiveChildForTw] = useState(null);
  const [timeWindows, setTimeWindows] = useState([]);
  const [newTw, setNewTw] = useState({ weekday: 0, start_time: '09:00', end_time: '12:00' });

  const loadData = () => {
    childrenApi.getAll().then(setChildren).catch(console.error);
    calendarApi.getSchoolYearSettings().then(setSchoolYear).catch(console.error);
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleSchoolYearSave = async (e) => {
    e.preventDefault();
    setSavingSettings(true);
    try {
      await calendarApi.updateSchoolYearSettings(schoolYear);
      alert('School year saved successfully! Remember to recalculate schedules.');
    } catch (e) {
      alert('Failed to save settings.');
    } finally {
      setSavingSettings(false);
    }
  };

  return (
    <div className="p-4 sm:p-6 lg:p-8 w-full min-h-full bg-gray-50/50 space-y-8 sm:space-y-12">
      <header>
        <h1 className="text-2xl sm:text-3xl font-bold text-text-primary mb-2">Settings</h1>
        <p className="text-text-secondary text-sm sm:text-base">Manage family profiles and app-wide configuration.</p>
      </header>

      <section>
        <div className="flex items-center mb-6 border-b border-border pb-2">
          <CalendarIcon className="w-6 h-6 mr-3 text-accent" />
          <h2 className="text-xl font-bold text-text-primary">Academic Year</h2>
        </div>
        
        <form onSubmit={handleSchoolYearSave} className="bg-surface p-6 rounded-2xl border border-border shadow-soft max-w-xl">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 sm:gap-6 mb-6">
            <div>
              <label className="block text-sm font-semibold text-text-secondary mb-2">Start Date</label>
              <input 
                type="date" 
                value={schoolYear.start_date || ''}
                onChange={e => setSchoolYear({...schoolYear, start_date: e.target.value})}
                className="w-full px-4 py-2 border border-border rounded-lg focus:ring-2 focus:ring-accent/20 focus:border-accent outline-none"
              />
            </div>
            <div>
              <label className="block text-sm font-semibold text-text-secondary mb-2">Target End Date</label>
              <input 
                type="date" 
                value={schoolYear.end_date || ''}
                onChange={e => setSchoolYear({...schoolYear, end_date: e.target.value})}
                className="w-full px-4 py-2 border border-border rounded-lg focus:ring-2 focus:ring-accent/20 focus:border-accent outline-none"
              />
            </div>
          </div>
          <p className="text-sm text-text-secondary mb-6">
            The smart scheduler will guarantee all curriculum is completed by the target end date.
          </p>
          <button 
            type="submit" 
            disabled={savingSettings}
            className="flex items-center bg-text-primary text-white px-5 py-2.5 rounded-xl font-medium hover:bg-gray-800 transition disabled:opacity-50"
          >
            <Save className="w-4 h-4 mr-2" /> 
            {savingSettings ? 'Saving...' : 'Save Year Settings'}
          </button>
        </form>
      </section>

      <section>
        <div className="flex items-center mb-6 border-b border-border pb-2">
          <User className="w-6 h-6 mr-3 text-accent" />
          <h2 className="text-xl font-bold text-text-primary">Children Profiles</h2>
        </div>
        
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {children.map(child => (
            <div key={child.id} className="bg-surface p-6 rounded-2xl border border-border shadow-soft flex flex-col">
              <div className="flex items-center mb-4">
                <div 
                  className="w-12 h-12 rounded-full flex items-center justify-center text-white text-xl font-bold mr-4 shadow-sm"
                  style={{ backgroundColor: child.color }}
                >
                  {child.name.charAt(0)}
                </div>
                <div>
                  <h3 className="text-lg font-bold text-text-primary">{child.name}</h3>
                  <p className="text-text-secondary text-sm">{child.grade_year || 'No grade mapped'} • {child.nickname || child.name}</p>
                </div>
              </div>
              
              <div className="mt-auto pt-4 border-t border-border flex justify-between">
                <button 
                  onClick={() => {
                    setEditingChild({...child});
                    setIsChildModalOpen(true);
                  }}
                  className="text-sm font-medium text-text-secondary flex items-center hover:text-accent transition"
                >
                  <User className="w-4 h-4 mr-1.5" /> Edit Profile
                </button>
                <button 
                  onClick={async () => {
                    setActiveChildForTw(child);
                    const tws = await timeWindowsApi.getByChildId(child.id);
                    setTimeWindows(tws);
                    setIsTwModalOpen(true);
                  }}
                  className="text-sm font-medium text-text-secondary flex items-center hover:text-accent transition"
                >
                  <Clock className="w-4 h-4 mr-1.5" /> Time Windows
                </button>
              </div>
            </div>
          ))}
          
          <button 
            onClick={() => {
              setEditingChild({ name: '', nickname: '', grade_year: '', color: '#6B9E8A' });
              setIsChildModalOpen(true);
            }}
            className="border-2 border-dashed border-border rounded-2xl p-6 flex flex-col items-center justify-center text-text-secondary hover:border-accent hover:text-accent transition bg-surface/50 h-full min-h-[160px]"
          >
            <Plus className="w-8 h-8 mb-2" />
            <span className="font-bold">Add New Child</span>
          </button>
        </div>
      </section>

      {/* Child Profile Modal */}
      {isChildModalOpen && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-3xl w-full max-w-md shadow-2xl overflow-hidden animate-in fade-in zoom-in duration-200">
            <div className="p-6 border-b border-border flex justify-between items-center">
              <h3 className="text-xl font-bold text-text-primary">
                {editingChild.id ? 'Edit Profile' : 'Add Child'}
              </h3>
              <button onClick={() => setIsChildModalOpen(false)}><X className="w-6 h-6 text-text-secondary" /></button>
            </div>
            <div className="p-6 space-y-4">
              <div>
                <label className="block text-sm font-semibold text-text-secondary mb-1">Full Name</label>
                <input 
                  className="w-full px-4 py-2 border border-border rounded-lg outline-none focus:ring-2 focus:ring-accent/20 focus:border-accent"
                  value={editingChild.name}
                  onChange={e => setEditingChild({...editingChild, name: e.target.value})}
                />
              </div>
              <div>
                <label className="block text-sm font-semibold text-text-secondary mb-1">Nickname (Optional)</label>
                <input 
                  className="w-full px-4 py-2 border border-border rounded-lg outline-none focus:ring-2 focus:ring-accent/20 focus:border-accent"
                  value={editingChild.nickname || ''}
                  onChange={e => setEditingChild({...editingChild, nickname: e.target.value})}
                />
              </div>
              <div>
                <label className="block text-sm font-semibold text-text-secondary mb-1">Grade Year</label>
                <input 
                  className="w-full px-4 py-2 border border-border rounded-lg outline-none focus:ring-2 focus:ring-accent/20 focus:border-accent"
                  placeholder="e.g. 4th Grade"
                  value={editingChild.grade_year || ''}
                  onChange={e => setEditingChild({...editingChild, grade_year: e.target.value})}
                />
              </div>
              <div>
                <label className="block text-sm font-semibold text-text-secondary mb-1">Brand Color</label>
                <div className="flex space-x-2">
                  {['#6B9E8A', '#E2A898', '#98A8E2', '#E298B9', '#B9E298'].map(c => (
                    <button 
                      key={c}
                      onClick={() => setEditingChild({...editingChild, color: c})}
                      className={clsx(
                        "w-8 h-8 rounded-full border-2 transition",
                        editingChild.color === c ? "border-text-primary scale-110" : "border-transparent"
                      )}
                      style={{ backgroundColor: c }}
                    />
                  ))}
                </div>
              </div>
            </div>
            <div className="p-6 bg-gray-50 flex justify-end space-x-3">
              <button 
                onClick={() => setIsChildModalOpen(false)}
                className="px-4 py-2 text-sm font-medium text-text-secondary hover:text-text-primary"
              >
                Cancel
              </button>
              <button 
                onClick={async () => {
                  try {
                    if (editingChild.id) {
                      await childrenApi.update(editingChild.id, editingChild);
                    } else {
                      await childrenApi.create(editingChild);
                    }
                    loadData();
                    setIsChildModalOpen(false);
                  } catch (e) { alert("Failed to save child."); }
                }}
                className="bg-accent text-white px-6 py-2 rounded-xl font-bold hover:bg-accent-hover transition shadow-sm"
              >
                Save Profile
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Time Windows Modal */}
      {isTwModalOpen && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-3xl w-full max-w-2xl shadow-2xl overflow-hidden animate-in fade-in zoom-in duration-200">
            <div className="p-6 border-b border-border flex justify-between items-center bg-gray-50">
              <div>
                <h3 className="text-xl font-bold text-text-primary">Study Windows</h3>
                <p className="text-sm text-text-secondary">When does {activeChildForTw.name} study?</p>
              </div>
              <button onClick={() => setIsTwModalOpen(false)}><X className="w-6 h-6 text-text-secondary" /></button>
            </div>
            
            <div className="p-6">
              <div className="space-y-3 mb-8 max-h-60 overflow-y-auto pr-2">
                {timeWindows.length === 0 ? (
                  <div className="text-center py-8 text-text-secondary bg-surface border border-dashed border-border rounded-xl">
                    No time windows set yet.
                  </div>
                ) : (
                  timeWindows.map(tw => (
                    <div key={tw.id} className="flex items-center justify-between bg-surface border border-border p-3 rounded-xl">
                      <div className="flex items-center">
                        <span className="w-28 font-bold text-text-primary">
                          {['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'][tw.weekday]}
                        </span>
                        <span className="text-text-secondary ml-4">
                          {tw.start_time} - {tw.end_time}
                        </span>
                      </div>
                      <button 
                        onClick={async () => {
                          await timeWindowsApi.delete(tw.id);
                          const fresh = await timeWindowsApi.getByChildId(activeChildForTw.id);
                          setTimeWindows(fresh);
                        }}
                        className="p-2 text-gray-400 hover:text-red-500 transition"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  ))
                )}
              </div>

              <div className="bg-gray-50 p-4 rounded-2xl border border-border">
                <h4 className="text-sm font-bold text-text-primary mb-3">Add New Window</h4>
                <div className="grid grid-cols-3 gap-4">
                  <div>
                    <label className="block text-xs font-semibold text-text-secondary mb-1">Day</label>
                    <select 
                      className="w-full px-3 py-2 border border-border rounded-lg outline-none"
                      value={newTw.weekday}
                      onChange={e => setNewTw({...newTw, weekday: parseInt(e.target.value)})}
                    >
                      {['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'].map((day, i) => (
                        <option key={i} value={i}>{day}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-text-secondary mb-1">Start</label>
                    <input 
                      type="time" 
                      className="w-full px-3 py-2 border border-border rounded-lg outline-none"
                      value={newTw.start_time}
                      onChange={e => setNewTw({...newTw, start_time: e.target.value})}
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-text-secondary mb-1">End</label>
                    <input 
                      type="time" 
                      className="w-full px-3 py-2 border border-border rounded-lg outline-none"
                      value={newTw.end_time}
                      onChange={e => setNewTw({...newTw, end_time: e.target.value})}
                    />
                  </div>
                </div>
                <button 
                  onClick={async () => {
                    try {
                      await timeWindowsApi.create({ ...newTw, child_id: activeChildForTw.id });
                      const fresh = await timeWindowsApi.getByChildId(activeChildForTw.id);
                      setTimeWindows(fresh);
                    } catch (e) { alert("Failed to add window."); }
                  }}
                  className="w-full mt-4 bg-text-primary text-white py-2 rounded-xl font-bold hover:bg-gray-800 transition"
                >
                  Add Window
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Settings;
