import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import './index.css'
import App from './App.jsx'
import ServerGate from './components/ServerGate.jsx'
import LessonReader from './pages/LessonReader.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <ServerGate>
        <Routes>
          <Route path="/lesson" element={<LessonReader />} />
          <Route path="/*" element={<App />} />
        </Routes>
      </ServerGate>
    </BrowserRouter>
  </StrictMode>,
)
