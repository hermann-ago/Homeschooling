import React, { useState, useEffect } from 'react';
import { Routes, Route } from 'react-router-dom';
import Sidebar from './components/Sidebar';
import ErrorBoundary from './components/ErrorBoundary';
import Today from './pages/Today';
import Weekly from './pages/Weekly';
import Curriculum from './pages/Curriculum';
import Calendar from './pages/Calendar';
import Settings from './pages/Settings';
import Progress from './pages/Progress';
import AllChildrenDashboard from './pages/AllChildrenDashboard';
import DailyCanvas from './pages/DailyCanvas';
import { childrenApi } from './api/children';
import { Menu } from 'lucide-react';
import { hexToRgb } from './utils/colors';


function App() {
  const [children, setChildren] = useState([]);
  const [activeChildId, setActiveChildId] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const loadChildren = () => {
    childrenApi.getAll().then(data => {
      setChildren(data);
      if (!activeChildId && data.length > 0) {
        setActiveChildId(data[0].id);
      }
    }).catch(console.error);
  };

  useEffect(() => {
    loadChildren();
  }, []);

  const activeChild = activeChildId !== 'all'
    ? children.find(c => c.id === activeChildId)
    : null;

  // Build CSS custom properties from active child's color
  const childColor = activeChild?.color || '#6B9E8A';
  const rgb = hexToRgb(childColor);
  const childStyle = {
    '--child-color': childColor,
    '--child-color-light': `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, 0.1)`,
    '--child-color-hover': `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, 0.85)`,
  };

  return (
    <div className="flex h-screen bg-background font-sans text-text-primary overflow-hidden" style={childStyle}>
      <Sidebar
        children={children}
        activeChildId={activeChildId}
        setActiveChildId={setActiveChildId}
        activeChild={activeChild}
        onChildrenChanged={loadChildren}
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
      />
      
      <div className="flex-1 flex flex-col overflow-hidden min-w-0">
        {/* Mobile top bar - only visible on small screens */}
        <div className="md:hidden flex items-center justify-between px-4 py-3 bg-surface border-b border-border flex-shrink-0">
          <button 
            onClick={() => setSidebarOpen(true)}
            className="p-2 text-text-secondary hover:text-text-primary hover:bg-gray-100 rounded-lg transition"
          >
            <Menu className="w-5 h-5" />
          </button>
          <h1 className="text-lg font-bold text-text-primary tracking-tight">Homeschooler</h1>
          {activeChild ? (
            <div 
              className="w-8 h-8 rounded-full flex items-center justify-center text-white font-bold text-sm shadow-sm" 
              style={{ backgroundColor: activeChild.color }}
            >
              {activeChild.name.charAt(0)}
            </div>
          ) : (
            <div className="w-8 h-8" /> /* spacer */
          )}
        </div>

        <main className="flex-1 overflow-y-auto w-full">
          <ErrorBoundary>
          {activeChildId === 'all' ? (
            <AllChildrenDashboard children={children} setActiveChildId={setActiveChildId} />
          ) : activeChildId ? (
            <Routes>
              <Route path="/" element={<Today activeChildId={activeChildId} />} />
              <Route path="/weekly" element={<Weekly activeChildId={activeChildId} />} />
              <Route path="/curriculum" element={<Curriculum activeChildId={activeChildId} />} />
              <Route path="/progress" element={<Progress activeChildId={activeChildId} />} />
              <Route path="/calendar" element={<Calendar activeChildId={activeChildId} />} />
              <Route path="/canvas" element={<DailyCanvas activeChildId={activeChildId} />} />
              <Route path="/settings" element={<Settings activeChildId={activeChildId} onChildrenChanged={loadChildren} />} />
            </Routes>
          ) : (
            <div className="flex items-center justify-center h-full">
              <div className="text-center">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-accent mx-auto mb-4"></div>
                <p className="text-text-secondary">Loading children...</p>
              </div>
            </div>
          )}
          </ErrorBoundary>
        </main>
      </div>
    </div>
  );
}

export default App;
