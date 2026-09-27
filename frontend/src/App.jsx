import { Navigate, Route, Routes } from 'react-router';
import Shell from './app/Shell';
import { useLearner } from './app/learnerContext';
import Today from './screens/Today';
import Plan from './screens/Plan';
import Curriculum from './screens/Curriculum';
import Progress from './screens/Progress';
import Settings from './pages/Settings';

/** Screens not rebuilt yet, shown for the chosen learner inside the new frame. */
function Legacy({ page: Page }) {
  const { single, refetch } = useLearner();
  return <Page activeChildId={single} onChildrenChanged={refetch} />;
}

export default function App() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<Today />} />
        <Route path="plan" element={<Plan />} />
        <Route path="curriculum" element={<Curriculum />} />
        <Route path="progress" element={<Progress />} />
        <Route path="settings" element={<Legacy page={Settings} />} />
        {/* Addresses from the old menu */}
        <Route path="weekly" element={<Navigate to="/plan" replace />} />
        <Route path="calendar" element={<Navigate to="/plan?view=month" replace />} />
        <Route path="canvas" element={<Navigate to="/" replace />} />
        <Route path="family-today" element={<Navigate to="/" replace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
