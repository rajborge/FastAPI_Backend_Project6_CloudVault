# CloudVault

CloudVault is a React/TypeScript file workspace and FastAPI file-storage backend with direct Cloudflare R2 upload sessions, quota reservations, background ClamAV scanning, and PostgreSQL metadata.

## Main features

- React and TypeScript frontend for managing files, folders, shared resources, recycle bin, and activity.
- Registration and login with username or email, JWT access tokens, rotating refresh tokens, and logout revocation.
- Nested folders, file and folder rename/move operations, file restore, and permanent deletion.
- Local uploads and signed Cloudflare R2 uploads, including multipart upload sessions, cancellation, and quota reservations.
- Background ClamAV scanning that blocks downloads until files are clean, with SHA-256 based storage deduplication.
- Public sharing links with optional passwords, expiry, download limits, and revocation.
- File and folder access roles with inherited folder permissions and a shared-with-me view.
- Background text extraction from text files and PDFs, image OCR through Tesseract, and ranked content search with snippets.
- Audit history, health endpoints, Alembic migrations, and a Docker Compose backend stack.

The workspace also includes file previews, comments, revision replacement/restore, sharing-link management, folder picking, upload cancellation/resume, storage usage, and real-time scan/index notifications. Browser refresh tokens use HttpOnly cookies with CSRF protection; account recovery, email verification, authenticator MFA, and one-use MFA recovery codes are available.

Search supports PostgreSQL full-text ranking and either lightweight lexical vectors or an optional local sentence-transformers model. Scanned PDF pages and image files use Tesseract OCR. Indexing failures are visible and retryable. A dedicated scheduler recovers interrupted scan/index jobs independently of API workers.

## Frontend

With the backend running, open a second terminal:

```sh
cd frontend
npm ci
npm run dev
```

The frontend defaults to `http://localhost:8000` for the API. Set `VITE_API_BASE_URL` to override it. The backend currently allows frontend origins at `http://localhost:5173` and `http://127.0.0.1:5173`; configure production origins before deployment.

Use `npm run build` for a production frontend build and `npm run lint` for frontend checks. Docker Compose starts the backend services; the frontend runs separately.

## Deployment and configuration

See [deploy/OPERATIONS.md](deploy/OPERATIONS.md) for same-origin HTTPS deployment, SMTP/MFA configuration, R2 CORS, worker monitoring, and backup/restore drills. `compose.production.yml` includes a Caddy frontend, private service networking, a worker, and a singleton scheduler. It requires your hostname and private deployment settings. No external services are provisioned automatically.

To enable learned embeddings, install `requirements-semantic.txt`, configure `EMBEDDING_MODEL` identically for API and worker, and reindex all files. The model must produce 384 dimensions. The default remains lexical search until a model is configured.

Changes in this update require `alembic upgrade head`. Do this after a verified backup. Existing JWT access tokens with no version claim retain version zero; password resets, detected refresh reuse, and MFA changes invalidate previous sessions.

## Repository hygiene

Keep real credentials in local environment files or deployment secret stores. `.env.example` contains placeholders only. Local environments, uploads, logs, backup snapshots, dependencies, and generated builds are excluded from new commits. Do not commit real user files or access tokens.

## Local stack

1. Install Docker Desktop and start Docker Compose.
2. Copy `.env.example` to `.env` and replace the local database password and JWT secret.
3. Run `docker compose up --build` from the project directory.
4. Open `http://localhost:8000/docs`. Liveness is available at `/health/live`; readiness is at `/health/ready`.

The first ClamAV startup downloads its virus definitions and can take several minutes. Files remain `PENDING_SCAN` and cannot be downloaded until the worker marks them `CLEAN`. Infected files are removed from storage and their quota usage is released.

## Cloudflare R2

Set `R2_ENDPOINT_URL`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, and `R2_BUCKET_NAME` in `.env` to enable direct uploads. Upload sessions reserve the expected file size against the user quota before returning a short-lived URL. Files at or above `R2_UPLOAD_MULTIPART_THRESHOLD_MB` use resumable multipart parts; smaller files use a signed single PUT. The browser must send the signed `Content-Type` and `x-amz-meta-sha256` metadata with the upload. Finalization validates the stored object size and digest metadata, then queues malware scanning.

Until R2 credentials are configured, `/files/upload` remains available for local development. The Glacier-style archive tier is not included because R2 does not provide that tier.

## Tests

Run unit tests with `python -m pytest`. Database integration tests skip unless `TEST_DATABASE_URL` points to a disposable PostgreSQL database ending in `_test`. To run the complete local database suite:

```sh
docker compose -p cloudvault-verification -f compose.test.yml up -d --wait
# Set TEST_DATABASE_URL and DB_* to the isolated test credentials/port in compose.test.yml.
# Set REDIS_HOST=127.0.0.1 and REDIS_PORT=56379.
python scripts/verify_migrations.py
python -m pytest -q
```

The migration verifier intentionally rolls the disposable database back to base and re-upgrades it; never use a database containing real data. Integration fixtures clear test tables. The test database name guard is mandatory.

Frontend checks run from `frontend`: `npm run build`, `npm run lint`, and `npm test`. Install the test browser with `npx playwright install chromium`, or set `PLAYWRIGHT_CHANNEL=chrome` to use an installed Chrome. Browser tests use mocked API responses; live R2/CORS, SMTP delivery, and full OCR/model performance need deployment smoke tests.

GitHub Actions runs backend tests against PostgreSQL/Redis, migration cycles, frontend build/lint/browser tests, dependency audits, and a redacted secret scan. See [IMPLEMENTATION.md](IMPLEMENTATION.md) for verification coverage and deployment-dependent work.
