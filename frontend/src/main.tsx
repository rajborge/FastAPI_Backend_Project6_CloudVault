import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import AccountPage from './AccountPage.tsx'
import PublicSharePage from './PublicSharePage.tsx'

const params = new URLSearchParams(window.location.search)
const accountAction = params.get('account_action')
const accountToken = params.get('token') ?? ''
if (accountAction) window.history.replaceState({}, '', window.location.pathname)

const shareMatch = window.location.pathname.match(/^\/shares\/([^/]+)$/)

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {accountAction ? <AccountPage action={accountAction} token={accountToken} /> : shareMatch ? <PublicSharePage token={decodeURIComponent(shareMatch[1])} /> : <App />}
  </StrictMode>,
)
