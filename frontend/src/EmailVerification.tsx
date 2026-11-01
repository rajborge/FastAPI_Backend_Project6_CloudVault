import { useEffect, useState } from 'react'
import { apiRequest } from './api'

type EmailState = { email: string; is_verified: boolean; delivery_status: string; delivery_error: string | null; sent_at: string | null }

export default function EmailVerification() {
  const [status, setStatus] = useState<EmailState | null>(null)
  const [message, setMessage] = useState('')
  const [sending, setSending] = useState(false)
  const [refresh, setRefresh] = useState(0)
  useEffect(() => {
    let active = true
    const read = () => apiRequest<EmailState>('/auth/email-status').then((value) => {
      if (!active) return
      setStatus(value)
      if (value.is_verified || value.delivery_status === 'SENT' || value.delivery_status === 'FAILED') setSending(false)
    }).catch((cause: Error) => { if (active) { setMessage(cause.message); setSending(false) } })
    void read()
    const timer = sending ? window.setInterval(() => void read(), 4000) : undefined
    return () => { active = false; window.clearInterval(timer) }
  }, [refresh, sending])
  async function send() {
    setMessage('')
    try {
      await apiRequest('/auth/me/request-verification', { method: 'POST' })
      setSending(true); setRefresh((n) => n + 1)
      setMessage('Verification requested. Waiting for delivery status…')
    } catch (cause) { setMessage((cause as Error).message) }
  }
  return <section className="verification-card" aria-label="Email verification">
    <h3>Email verification</h3><p>{status?.email ?? 'Loading your email…'} <strong>{status?.is_verified ? 'Verified' : 'Not verified'}</strong></p>
    {status?.is_verified ? <p>Your account email is verified.</p> : <>
      <p>Send a verification link to the email registered on your account, then open the link in that inbox.</p>
      {status?.delivery_status === 'SENT' && <p role="status">Email sent. Check your inbox and spam folder. The link expires in 30 minutes.</p>}
      {status?.delivery_status === 'FAILED' && <p role="alert" className="form-error">{status.delivery_error ?? 'Email delivery failed. Check your local mail setup.'}</p>}
      {message && status?.delivery_status !== 'SENT' && <p role="status">{message}</p>}
      <div className="sharing-actions"><button className="button button-primary" disabled={sending} onClick={() => void send()}>{sending ? 'Sending…' : 'Send verification email'}</button><button className="button button-secondary" onClick={() => setRefresh((n) => n + 1)}>Refresh verification status</button></div>
    </>}
  </section>
}
