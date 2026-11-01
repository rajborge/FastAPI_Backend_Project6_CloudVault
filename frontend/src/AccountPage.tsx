import { useState, type FormEvent } from 'react'
import { API_BASE } from './api'
import { Cloud, ShieldCheck } from 'lucide-react'
import './App.css'

export default function AccountPage({ action, token }: { action: string; token: string }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)
  const verify = action === 'verify'
  const reset = action === 'reset'
  async function submit(e: FormEvent) {
    e.preventDefault(); setBusy(true)
    try {
      const path = verify ? 'verify-email' : reset ? 'reset-password' : action === 'request-verification' ? 'request-verification' : 'forgot-password'
      const response = await fetch(`${API_BASE}/auth/${path}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(verify ? { token } : reset ? { token, password } : { email }),
      })
      if (!response.ok) {
        const result = await response.json().catch(() => ({})) as { detail?: string | { msg: string }[] }
        const detail = typeof result.detail === 'string' ? result.detail : Array.isArray(result.detail) ? result.detail.map((item) => item.msg).join(' ') : 'The request could not be completed. Try again shortly.'
        throw new Error(detail)
      }
      setDone(true)
      setMessage(reset ? 'Password updated. Sign in again.' : verify ? 'Email verified. You can sign in.' : 'If the account is eligible, an email will arrive shortly.')
      setPassword('')
      window.history.replaceState({}, '', window.location.pathname)
    } catch (cause) { setMessage((cause as Error).message) } finally { setBusy(false) }
  }
  return <main className="auth-page">
    <a className="auth-brand" href="/"><span className="brand-mark"><Cloud size={20} /></span>CloudVault</a>
    <section className="auth-layout">
      <div className="auth-copy"><p className="eyebrow">YOUR SPACE. SECURELY STORED.</p><h1>A little more peace of mind.</h1><p className="auth-intro">Keep your account protected and your files close. Complete this step, then return to your workspace.</p><div className="auth-assurance"><ShieldCheck size={16} />Private files. Protected access.</div></div>
      <form className="auth-form" onSubmit={submit}><div className="auth-form-heading"><h2>{verify ? 'Verify your email' : reset ? 'Set a new password' : action === 'request-verification' ? 'Request verification email' : 'Reset your password'}</h2><p>{verify ? 'Confirm this email belongs to you.' : 'We’ll help you get back to your files.'}</p></div>
        {!done && <>{!verify && (reset ? <label>New password<input type="password" autoComplete="new-password" required minLength={8} maxLength={128} value={password} onChange={(e) => setPassword(e.target.value)} /><small>Use uppercase, lowercase, and a number. Minimum 8 characters.</small></label> : <label>Email<input type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></label>)}<button className="button button-primary auth-submit" disabled={busy || ((verify || reset) && !token)}>{busy ? 'Working…' : verify ? 'Verify email' : 'Continue'}</button></>}
        {message && <p role="status" className={done ? 'account-success' : 'form-error'}>{message}</p>}
        {verify && !done && <><p className="muted-copy">Use the most recent email. Verification links expire after 30 minutes.</p><a href="/?account_action=request-verification">Send a fresh verification link</a></>}
        <a href="/">{done ? 'Return to CloudVault' : 'Back to sign in'}</a>
      </form>
    </section>
  </main>
}
