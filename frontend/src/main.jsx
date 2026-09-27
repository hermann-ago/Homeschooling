import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Route, Routes } from 'react-router'
import { QueryClientProvider } from '@tanstack/react-query'
import '@fontsource-variable/figtree'
import '@fontsource-variable/fraunces'
import './index.css'
import App from './App.jsx'
import ServerGate from './components/ServerGate.jsx'
import Lesson from './screens/Lesson.jsx'
import StyleGuide from './pages/StyleGuide.jsx'
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
              <Routes>
                <Route path="/lesson" element={<Lesson />} />
                <Route path="/styleguide" element={<StyleGuide />} />
                <Route path="/*" element={<App />} />
              </Routes>
            </LearnerProvider>
          </ServerGate>
        </BrowserRouter>
      </FeedbackProvider>
    </QueryClientProvider>
  </StrictMode>,
)
