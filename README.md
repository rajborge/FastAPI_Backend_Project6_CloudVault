# CloudVault

CloudVault is a FastAPI file-storage backend with direct Cloudflare R2 upload sessions, quota reservations, background ClamAV scanning, and PostgreSQL metadata.

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

Search currently uses PostgreSQL full-text search and deterministic hashed lexical vectors stored in pgvector. Transformer-based semantic embeddings are a possible future upgrade. OCR currently targets image files; scanned PDF OCR needs a separate pipeline. Notification and WebSocket scaffolding is present but is not exposed by the main application.

## Frontend

With the backend running, open a second terminal:

```sh
cd frontend
npm ci
npm run dev
```

The frontend defaults to `http://localhost:8000` for the API. Set `VITE_API_BASE_URL` to override it. The backend currently allows frontend origins at `http://localhost:5173` and `http://127.0.0.1:5173`; configure production origins before deployment.

Use `npm run build` for a production frontend build and `npm run lint` for frontend checks. Docker Compose starts the backend services; the frontend runs separately.

## Suggested next steps

1. Add CI for backend tests, frontend build/lint, and integration tests against PostgreSQL, Redis, object storage, and ClamAV.
2. Complete account recovery and email verification, add MFA, and harden browser token handling and authentication rate limits.
3. Add file version history, previews, and comments to complement the existing sharing roles.
4. Upgrade content search with semantic embeddings, scanned PDF OCR, and explicit indexing progress/error states.
5. Finish real-time upload/scan notifications and add operational monitoring, backups, and restore drills.

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

Run the backend tests with `python -m pytest`. Tests use fake object storage, scanner, and database dependencies and do not require cloud credentials. Database migrations and end-to-end Compose behavior should also be verified against the running local services.
