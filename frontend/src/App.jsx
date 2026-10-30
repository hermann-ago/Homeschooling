import { Navigate, Route, Routes } from 'react-router';
import Shell from './app/Shell';
import Today from './screens/Today';
import Plan from './screens/Plan';
import Curriculum from './screens/Curriculum';
import Progress from './screens/Progress';
import Records from './screens/Records';
import Settings from './screens/Settings';
import Books, { BookDetail } from './screens/Books';

export default function App() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<Today />} />
        <Route path="plan" element={<Plan />} />
        <Route path="curriculum" element={<Curriculum />} />
        <Route path="books" element={<Books />} />
        <Route path="books/:bookId" element={<BookDetail />} />
        <Route path="progress" element={<Progress />} />
        <Route path="records" element={<Records />} />
        <Route path="settings" element={<Settings />} />
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
