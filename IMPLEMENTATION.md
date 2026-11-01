# Improvement implementation and verification

The project now implements the review's application changes across security, file collaboration, search, reliability, and developer checks. Production activation still requires deployment-owned services and secrets.

## Implemented

- Public share downloads redirect with HTTP 303; application/Uvicorn share paths are redacted. Missing files return 404.
- Quota locks refresh stale user instances. Storage releases use database arithmetic. Refresh rotation is serialized; reuse revokes successors and invalidates previous access tokens. The browser shares one refresh request across concurrent API failures.
- Browser refresh tokens are HttpOnly, SameSite cookies with a separate CSRF value. Password reset and verification use expiring hashed, single-use tokens sent through SMTP. MFA secrets are encrypted, TOTP replay is rejected, and ten hashed one-use recovery codes are issued during enrollment. Security changes renew the current session and invalidate older sessions.
- Auth/share rate limits use atomic Redis counters and fail closed if the limiter is unavailable. Production startup validates HTTPS origins, JWT secret length, DEBUG, and rate-limit configuration.
- A separate singleton scheduler reconciles pending scans and abandoned jobs. Scan/index leases prevent old workers from overwriting newer state. Index status and extraction errors are visible and retryable.
- Folder picking replaces destination UUID prompts. The workspace shows quota, sharing links, preview/comments/version tools, and cancel buttons. Interrupted R2 uploads can resume by selecting the same file in the same tab. Multipart part state comes from object storage; completion is idempotent. Explicit cancellation attempts to abort storage uploads and release reservations; abandoned sessions expire through cleanup.
- File revisions retain their own storage references and quota charges. Restore swaps clean payloads while preserving file identity and current share links. Permanent deletion releases retained revisions. Incoming-file share links and permissions are revoked during replacement.
- File comments enforce viewer/commenter/owner permissions. Safe preview types are limited to PDF, plain text, PNG, JPEG, and WebP. Bearer-authenticated SSE notifies owners about scan/index completion; connections release database sessions between reads.
- Image OCR and scanned-PDF rendering use pixel/page/time limits. Extraction errors no longer silently disappear. Learned local embeddings are optional; model identity is stored with vectors so differently configured models cannot be mixed. PostgreSQL full-text/vector indexes are included.
- GitHub Actions checks backend/database workflows, migration rollback/re-upgrade, frontend build/lint/browser tests, dependencies, and secrets. Frontend dependency security updates and patched backend package versions are included; unused vulnerable JWT libraries were removed from requirements.
- Production Compose/Caddy templates provide same-origin HTTPS, private database/Redis/ClamAV services, persistent Redis, worker health checks, and a dedicated scheduler. Operations documentation covers monitoring and encrypted backup/restore drills.

## Verified locally

- 66 backend unit and PostgreSQL/Redis integration tests, including simultaneous quota reservations and token refresh, atomic storage release, account token use, MFA replay/recovery, session cookies/CSRF, comments, version restore/deletion, search isolation, recovery, idempotent upload completion, and OCR page rendering.
- 6 browser regression tests for the folder access dialog, folder picking, file tools, shared refresh requests, resuming interrupted multipart uploads without re-uploading completed parts, and signed download redirects without forwarded API credentials.
- Production frontend build and lint.
- Full Alembic upgrade, downgrade-to-base, and re-upgrade on a disposable database. Legacy PostgreSQL enum cleanup and role downgrade behavior were corrected.
- Backend and production frontend container builds, Caddy configuration validation, and real Tesseract image/scanned-PDF OCR smoke tests with generated samples.
- Backend requirements and frontend dependency audits reported no known vulnerabilities. A source-only Gitleaks scan reported no leaks.

## Deployment-dependent checks

These have implementation/configuration support but are not claimed as live production validation:

- SMTP delivery requires your mail provider. No real account emails were sent during tests.
- MFA enrollment requires a private `MFA_ENCRYPTION_KEY`. The real `.env` was not edited.
- Real Cloudflare R2 signing/CORS/resume/share behavior requires your bucket. Browser regressions use mocked API responses; object-storage/scanner protocol tests use fakes.
- Full Tesseract recognition quality, learned-model relevance/performance, and resource limits need representative documents and configured model weights. PDF rendering and OCR dispatch have automated regression coverage.
- HTTPS certificate issuance requires your hostname/DNS. The production stack has not been publicly deployed.
- CI is configured locally; GitHub-hosted execution is not claimed until the changes are pushed and the workflow runs.
- Backup procedures are documented. No real production backup or restore was performed.

Use `deploy/OPERATIONS.md` to activate these integrations. Back up the database and storage, then run `alembic upgrade head` before running the updated app.


## Local sharing and email fixes (2 November 2026)

- Preserved Uvicorn access-log arguments during redaction to fix formatter crashes.
- Confirmed the user's R2 permits localhost origins but not the opaque Origin:null produced by redirect-based fetches. Browser downloads now resolve a signed link and navigate directly, without sending API authorization to object storage. Image/PDF previews use direct inline links; text previews render safely inside the app.
- Added Shared with me / Shared by me views with sender/recipient identities, shared date, scan state, role descriptions, and capability-based controls. Only the actual owner manages access; delegated Owner roles are treated as Editor rather than transferring ownership.
- Added SMTP SSL/STARTTLS support and authenticated email-delivery diagnostics. Failed delivery keeps earlier usable links valid. See deploy/LOCAL_EMAIL.md for Gmail app-password setup.
- Added recipient-role, SMTP, verification retry, Uvicorn formatting, native signed-download, and shared-preview regression tests.
