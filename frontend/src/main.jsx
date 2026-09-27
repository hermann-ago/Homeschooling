import { StrictMode, Suspense, lazy } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Route, Routes } from 'react-router'
import { QueryClientProvider } from '@tanstack/react-query'
import '@fontsource-variable/figtree'
import '@fontsource-variable/fraunces'
import './index.css'
import App from './App.jsx'
import ServerGate from './components/ServerGate.jsx'
// The lesson (PDF pages, handwriting, read-along) and the style guide load only when opened, so Today
// and the other screens start quickly on tablets.
const Lesson = lazy(() => import('./screens/Lesson.jsx'))
const StyleGuide = lazy(() => import('./screens/StyleGuide.jsx'))
import { createQueryClient } from './api/queries.js'
import { FeedbackProvider } from './ui/feedback.jsx'
import LearnerProvider from './app/LearnerProvider.jsx'

const queryClient = createQueryClient()

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <FeedbackProvider>
        <BrowserRouter>
          <ServerGate>
            <LearnerProvider>
              <Suspense fallback={<main className="min-h-dvh grid place-items-center text-muted">Opening…</main>}>
                <Routes>
                  <Route path="/lesson" element={<Lesson />} />
                  <Route path="/styleguide" element={<StyleGuide />} />
                  <Route path="/*" element={<App />} />
                </Routes>
              </Suspense>
            </LearnerProvider>
          </ServerGate>
        </BrowserRouter>
      </FeedbackProvider>
    </QueryClientProvider>
  </StrictMode>,
)
