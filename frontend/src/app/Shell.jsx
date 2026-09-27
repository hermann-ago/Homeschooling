import { NavLink, Outlet } from 'react-router';
import clsx from 'clsx';
import { BookOpen, CalendarDays, SlidersHorizontal, Sun, TrendingUp } from 'lucide-react';
import SyncIndicator from '../components/SyncIndicator';
import ErrorBoundary from '../components/ErrorBoundary';
import { Button } from '../ui';
import { useLearner } from './learnerContext';

const PLACES = [
  { to: '/', label: 'Today', icon: Sun },
  { to: '/plan', label: 'Plan', icon: CalendarDays },
  { to: '/curriculum', label: 'Curriculum', icon: BookOpen },
  { to: '/progress', label: 'Progress', icon: TrendingUp },
];
const SETTINGS = { to: '/settings', label: 'Settings', icon: SlidersHorizontal };

function SideLink({ to, label, icon: Icon }) {
  return (
    <NavLink to={to} end={to === '/'} className={({ isActive }) => clsx(
      'flex items-center gap-3 h-11 px-3 rounded-[10px] text-[15px] border transition-colors',
      'focus-visible:outline-2 focus-visible:outline-action',
      isActive ? 'bg-surface border-line text-ink font-semibold' : 'border-transparent text-muted font-medium hover:text-ink hover:bg-surface/60',
    )}>
      {({ isActive }) => (
        <>
          <Icon aria-hidden="true" className={clsx('w-5 h-5', isActive && 'text-action')} strokeWidth={1.8} />
          {label}
        </>
      )}
    </NavLink>
  );
}

function TabLink({ to, label, icon: Icon }) {
  return (
    <NavLink to={to} end={to === '/'} className={({ isActive }) => clsx(
      'flex flex-col items-center justify-center gap-0.5 text-xs',
      isActive ? 'text-action font-bold' : 'text-muted font-medium',
    )}>
      <Icon aria-hidden="true" className="w-[22px] h-[22px]" strokeWidth={1.8} />
      {label}
    </NavLink>
  );
}

export function Brand() {
  return (
    <div className="flex items-center gap-2.5">
      <span className="w-[34px] h-[34px] rounded-[10px] bg-action text-white grid place-items-center">
        <BookOpen aria-hidden="true" className="w-[18px] h-[18px]" strokeWidth={2} />
      </span>
      <span className="font-display text-[21px] font-semibold">Homeschool</span>
    </div>
  );
}

/** The frame around every screen: sidebar on wide screens, tab bar on phones. */
export default function Shell() {
  const { error, refetch, isLoading } = useLearner();
  return (
    <div className="flex h-dvh bg-paper text-ink overflow-hidden">
      <nav aria-label="Main" className="hidden md:flex w-60 shrink-0 flex-col gap-7 px-4 py-6 border-r border-line">
        <div className="px-2"><Brand /></div>
        <div className="flex flex-col gap-1">
          {PLACES.map((place) => <SideLink key={place.to} {...place} />)}
        </div>
        <div className="flex-1" />
        <div className="rounded-xl bg-paper-deep px-3 py-3.5"><SyncIndicator /></div>
        <SideLink {...SETTINGS} />
      </nav>

      <div className="flex-1 min-w-0 flex flex-col">
        <main className="flex-1 min-h-0 overflow-y-auto">
          <ErrorBoundary>
            {error ? (
              <div className="h-full grid place-items-center p-6 text-center">
                <div className="flex flex-col items-center gap-3">
                  <p className="font-semibold">The family's learners could not be loaded.</p>
                  <p className="text-sm text-muted">{error.message}</p>
                  <Button variant="primary" onClick={() => refetch()}>Try again</Button>
                </div>
              </div>
            ) : isLoading ? (
              <p className="p-10 text-muted">Loading…</p>
            ) : <Outlet />}
          </ErrorBoundary>
        </main>
        <nav aria-label="Main" className="md:hidden grid grid-cols-5 h-[68px] shrink-0 border-t border-line bg-surface pb-1">
          {[...PLACES, SETTINGS].map((place) => <TabLink key={place.to} {...place} />)}
        </nav>
      </div>
    </div>
  );
}
