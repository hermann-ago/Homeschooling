import React from 'react';
import { NavLink } from 'react-router-dom';
import { 
  CheckSquare, 
  Calendar as CalendarIcon, 
  BookOpen, 
  Settings, 
  TrendingUp,
  LayoutDashboard,
  Layout,
  Users,
  X,
  LogOut
} from 'lucide-react';
import { supabase } from '../lib/supabase';

const Sidebar = ({ children, activeChildId, setActiveChildId, activeChild, isOpen, onClose }) => {

  const navItems = [
    { to: '/', icon: CheckSquare, label: 'Today' },
    { to: '/canvas', icon: Layout, label: 'Daily Canvas' },
    { to: '/weekly', icon: LayoutDashboard, label: 'Weekly' },
    { to: '/curriculum', icon: BookOpen, label: 'Curriculum' },
    { to: '/progress', icon: TrendingUp, label: 'Progress' },
    { to: '/calendar', icon: CalendarIcon, label: 'Calendar' },
    { to: '/settings', icon: Settings, label: 'Settings' },
  ];

  const allChildrenNavItems = [
    { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
    { to: '/family-today', icon: CalendarIcon, label: 'Family Schedule' },
  ];

  const isAllMode = activeChildId === 'all';

  const handleChildSelect = (id) => {
    setActiveChildId(id);
    onClose?.();
  };

  const handleNavClick = () => {
    onClose?.();
  };

  const sidebarContent = (
    <>
      {/* Header with accent stripe */}
      <div className="relative">
        <div 
          className="h-1.5 w-full transition-colors duration-300"
          style={{ backgroundColor: isAllMode ? '#6B9E8A' : (activeChild?.color || '#6B9E8A') }}
        />
        <div className="p-6 flex items-center justify-between">
          <h1 className="text-xl font-bold text-text-primary tracking-tight">Homeschooler</h1>
          {/* Close button - visible only on mobile */}
          <button 
            onClick={onClose} 
            className="md:hidden p-1.5 text-text-secondary hover:text-text-primary hover:bg-gray-100 rounded-md transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
      </div>

      <div className="px-4 pb-4">
        <h2 className="text-xs uppercase tracking-wider text-text-secondary font-semibold mb-3 px-2">Children</h2>
        <div className="space-y-1">
          {/* All Children option */}
          <button
            onClick={() => handleChildSelect('all')}
            className={`w-full flex items-center px-3 py-2 rounded-lg transition-colors ${
              isAllMode 
                ? 'bg-gray-100 text-text-primary font-medium' 
                : 'hover:bg-gray-50 text-text-secondary'
            }`}
          >
            <Users className="w-4 h-4 mr-3" />
            All Children
          </button>
          
          {children.map(child => (
            <button
              key={child.id}
              onClick={() => handleChildSelect(child.id)}
              className={`w-full flex items-center px-3 py-2 rounded-lg transition-all duration-200 ${
                activeChildId === child.id 
                  ? 'font-medium' 
                  : 'hover:bg-gray-50 text-text-secondary'
              }`}
              style={activeChildId === child.id ? {
                backgroundColor: `${child.color}15`,
                color: child.color,
              } : {}}
            >
              <div 
                className="w-3 h-3 rounded-full mr-3 shadow-sm ring-1 ring-white" 
                style={{ backgroundColor: child.color }}
              />
              {child.name}
            </button>
          ))}
        </div>
      </div>

      <nav className="flex-1 px-4 py-4 border-t border-border">
          <h2 className="text-xs uppercase tracking-wider text-text-secondary font-semibold mb-3 px-2">Menu</h2>
          <ul className="space-y-1">
            {(isAllMode ? allChildrenNavItems : navItems).map((item) => (
              <li key={item.to}>
                <NavLink
                  to={item.to}
                  end={item.to === '/'}
                  onClick={handleNavClick}
                  className={({ isActive }) =>
                    `flex items-center px-3 py-2.5 rounded-lg transition-all duration-200 ${
                      isActive
                        ? 'text-white shadow-sm'
                        : 'text-text-secondary hover:bg-gray-50 hover:text-text-primary'
                    }`
                  }
                  style={({ isActive }) => isActive ? {
                    backgroundColor: isAllMode ? '#6B9E8A' : (activeChild?.color || '#6B9E8A'),
                  } : {}}
                >
                  <item.icon className="w-5 h-5 mr-3" />
                  <span className="font-medium">{item.label}</span>
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>

      {activeChild && (
        <div className="p-4 border-t border-border" style={{ backgroundColor: `${activeChild.color}08` }}>
          <div className="flex items-center">
             <div 
                className="w-8 h-8 rounded-full shadow-sm flex items-center justify-center text-white font-bold text-sm mr-3" 
                style={{ backgroundColor: activeChild.color }}
              >
                {activeChild.name.charAt(0)}
              </div>
              <div className="text-sm">
                <p className="font-semibold text-text-primary">{activeChild.name}</p>
                <p className="text-text-secondary text-xs">{activeChild.grade_year}</p>
              </div>
          </div>
        </div>
      )}
      <div className="p-4 border-t border-border">
        <button onClick={() => supabase?.auth.signOut()} className="w-full flex items-center gap-2 text-sm text-text-secondary hover:text-text-primary">
          <LogOut className="w-4 h-4" /> Sign out
        </button>
      </div>
    </>
  );

  return (
    <>
      {/* Desktop sidebar - always visible on md+ */}
      <aside className="hidden md:flex w-64 bg-surface border-r border-border h-screen flex-col shadow-soft flex-shrink-0">
        {sidebarContent}
      </aside>

      {/* Mobile overlay + drawer */}
      {isOpen && (
        <div className="md:hidden fixed inset-0 z-50">
          {/* Backdrop */}
          <div 
            className="absolute inset-0 bg-black/40 backdrop-blur-sm"
            onClick={onClose}
          />
          {/* Drawer */}
          <aside className="absolute left-0 top-0 bottom-0 w-72 bg-surface shadow-2xl flex flex-col animate-in slide-in-from-left duration-200">
            {sidebarContent}
          </aside>
        </div>
      )}
    </>
  );
};

export default Sidebar;
