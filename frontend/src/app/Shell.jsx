import { useState } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router';
import clsx from 'clsx';
import { BookOpen, Library, CalendarDays, SlidersHorizontal, Sun, TrendingUp, Table2, MoreHorizontal } from 'lucide-react';
import SyncIndicator from '../components/SyncIndicator';
import ErrorBoundary from '../components/ErrorBoundary';
import { Button, Dialog } from '../ui';
import { useLearner } from './learnerContext';
import useViewportHeight from './useViewportHeight';

const PLACES = [
  { to: '/', label: 'Today', icon: Sun },
  { to: '/plan', label: 'Plan', icon: CalendarDays },
  { to: '/curriculum', label: 'Curriculum', icon: BookOpen },
  { to: '/books', label: 'Books', icon: Library },
  { to: '/progress', label: 'Progress', icon: TrendingUp },
  { to: '/records', label: 'Records', icon: Table2 },
];
const SETTINGS = { to: '/settings', label: 'Settings', icon: SlidersHorizontal };

function SideLink({ to, label, icon: Icon }) {
  return (
    <NavLink to={to} end={to === '/'} className={({ isActive }) => clsx(
      'flex items-center justify-center xl:justify-start gap-3 h-11 px-3 rounded-[10px] text-[15px] border transition-colors',
      'focus-visible:outline-2 focus-visible:outline-action',
      isActive ? 'bg-surface border-line text-ink font-semibold' : 'border-transparent text-muted font-medium hover:text-ink hover:bg-surface/60',
    )} title={label}>
      {({ isActive }) => (
        <>
          <Icon aria-hidden="true" className={clsx('w-5 h-5', isActive && 'text-action')} strokeWidth={1.8} />
          <span className="sr-only xl:not-sr-only">{label}</span>
        </>
      )}
    </NavLink>
  );
}

function TabLink({ to, label, icon: Icon }) {
  return (
    <NavLink to={to} end={to === '/'} className={({ isActive }) => clsx(
      'flex min-w-0 flex-col items-center justify-center gap-0.5 px-1 py-2 text-[11px] min-h-14',
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
  useViewportHeight();
  const { error, refetch, isLoading } = useLearner();
  const [moreOpen, setMoreOpen] = useState(false);
  const { pathname } = useLocation();
  const secondary = [...PLACES.slice(4), SETTINGS];
  const moreActive = secondary.some((place) => pathname.startsWith(place.to));
  return (
    <div className="app-shell flex h-dvh bg-paper text-ink overflow-hidden">
      <nav aria-label="Main" className="hidden md:flex w-20 xl:w-60 shrink-0 flex-col gap-7 px-2 xl:px-4 py-6 border-r border-line">
        <div className="hidden xl:block px-2"><Brand /></div>
        <BookOpen aria-label="Homeschool" className="xl:hidden self-center w-8 h-8 text-action" />
        <div className="flex flex-col gap-1">
          {PLACES.map((place) => <SideLink key={place.to} {...place} />)}
        </div>
        <div className="flex-1" />
        <div className="hidden xl:block rounded-xl bg-paper-deep px-3 py-3.5"><SyncIndicator /></div>
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
        <nav aria-label="Main" className="mobile-tab-bar md:hidden grid grid-cols-5 shrink-0 border-t border-line bg-surface">
          {PLACES.slice(0, 4).map((place) => <TabLink key={place.to} {...place} />)}
          <button type="button" aria-label="More pages" aria-haspopup="dialog" aria-expanded={moreOpen} aria-current={moreActive ? 'page' : undefined} onClick={() => setMoreOpen(true)} className={clsx('flex flex-col items-center justify-center gap-0.5 px-1 py-2 min-h-14 text-[11px]', moreActive ? 'text-action font-bold' : 'text-muted')}>
            <MoreHorizontal aria-hidden="true" size={22} />More
          </button>
        </nav>
        <Dialog open={moreOpen} title="More pages" onClose={() => setMoreOpen(false)}>
          <nav aria-label="More pages" className="flex flex-col gap-2">{secondary.map(({ to, label, icon: Icon }) => <NavLink key={to} to={to} onClick={() => setMoreOpen(false)} className="flex items-center gap-3 min-h-12 rounded-xl px-3 py-2 font-semibold text-action hover:bg-paper"><Icon size={21} aria-hidden="true" />{label}</NavLink>)}</nav>
          <div className="mt-4 border-t border-line pt-4"><SyncIndicator /></div>
        </Dialog>
      </div>
    </div>
  );
}
