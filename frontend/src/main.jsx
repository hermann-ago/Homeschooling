import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import './index.css'
import App from './App.jsx'
import PairingGate from './components/PairingGate.jsx'
import LessonReader from './pages/LessonReader.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <PairingGate>
        <Routes>
          <Route path="/lesson" element={<LessonReader />} />
          <Route path="/*" element={<App />} />
        </Routes>
      </PairingGate>
    </BrowserRouter>
  </StrictMode>,
)
