import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import PublicSharePage from './PublicSharePage.tsx'

const shareMatch = window.location.pathname.match(/^\/shares\/([^/]+)$/)

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {shareMatch ? <PublicSharePage token={decodeURIComponent(shareMatch[1])} /> : <App />}
  </StrictMode>,
)
