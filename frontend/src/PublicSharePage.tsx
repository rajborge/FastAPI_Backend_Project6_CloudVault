import { useEffect, useState, type FormEvent } from 'react'
import { Download, HardDrive, LoaderCircle, LockKeyhole, ShieldCheck } from 'lucide-react'
import { downloadSharedFile, getPublicShare, type SharePublicInfo } from './api'

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  const units = ['KB', 'MB', 'GB', 'TB']
  let value = bytes / 1024
  let index = 0
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024
    index += 1
  }
  return `${value.toFixed(value >= 10 ? 0 : 1)} ${units[index]}`
}

export default function PublicSharePage({ token }: { token: string }) {
  const [info, setInfo] = useState<SharePublicInfo | null>(null)
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(true)
  const [downloading, setDownloading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    getPublicShare(token)
      .then(setInfo)
      .catch((cause: unknown) => setError(cause instanceof Error ? cause.message : 'Share link is unavailable.'))
      .finally(() => setLoading(false))
  }, [token])

  async function handleDownload(event: FormEvent) {
    event.preventDefault()
    if (!info) return
    setDownloading(true)
    setError('')
    try {
      await downloadSharedFile(token, info.requires_password ? password : null, info.original_name)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Download failed.')
    } finally {
      setDownloading(false)
    }
  }

  return (
    <main className="auth-page">
      <div className="auth-brand"><span className="brand-mark"><HardDrive size={21} /></span><span>cloudvault</span></div>
      <section className="auth-layout">
        <div className="auth-copy">
          <p className="eyebrow">SECURE SHARE</p>
          <h1>A file has been shared with you.</h1>
          <p className="auth-intro">The link is protected by CloudVault's expiry and download-limit controls.</p>
          <div className="auth-assurance"><ShieldCheck size={18} /><span>Only malware-scanned files can be downloaded.</span></div>
        </div>
        <form className="auth-form" onSubmit={handleDownload}>
          {loading ? (
            <div className="loading-state"><LoaderCircle className="spin" size={22} /><span>Loading share</span></div>
          ) : info ? (
            <>
              <div className="auth-form-heading">
                <p className="eyebrow">SHARED FILE</p>
                <h2>{info.original_name}</h2>
                <p>{formatBytes(info.size)} · {info.mime_type}</p>
              </div>
              {info.requires_password && (
                <label>Password<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} required /></label>
              )}
              {error && <p className="form-error" role="alert">{error}</p>}
              <button className="button button-primary auth-submit" disabled={downloading}>
                {downloading ? <LoaderCircle className="spin" size={17} /> : info.requires_password ? <LockKeyhole size={17} /> : <Download size={17} />}
                {downloading ? 'Preparing…' : 'Download file'}
              </button>
            </>
          ) : (
            <div className="auth-form-heading"><h2>Share unavailable</h2><p>{error || 'This link may have expired or been revoked.'}</p></div>
          )}
        </form>
      </section>
    </main>
  )
}
