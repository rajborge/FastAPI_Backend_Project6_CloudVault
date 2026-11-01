# Deploying and operating CloudVault

## First deployment

1. Back up the existing database and storage before upgrading. Test restoration into an isolated stack. Older permission-role downgrades intentionally map OWNER to EDITOR and COMMENTER to VIEWER and therefore lose role detail.
2. Copy `.env.example` to a private `.env`. Set database credentials and a random JWT secret of at least 32 bytes. Generate a separate Fernet key with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` for `MFA_ENCRYPTION_KEY`. Keep it in your secret manager and include it in encrypted backups; do not commit it or rotate it without re-encrypting stored MFA secrets.
3. Set `PUBLIC_DOMAIN` to your hostname and point DNS at the host. Set real SMTP credentials. Use STARTTLS for remote SMTP; local mail capture services can set `MAIL_STARTTLS=false` and `MAIL_AUTH_ENABLED=false`. Set `REQUIRE_VERIFIED_EMAIL=true` after existing accounts have had a chance to verify.
4. Run `docker compose -f compose.production.yml up -d --build`. Caddy obtains HTTPS certificates and serves the frontend and API from the same origin. Only HTTP/HTTPS ports are exposed. The API trusts forwarded headers only because it has no published port and is reachable through the private Compose network. Do not publish its port with this trust configuration.
5. Configure R2 bucket CORS for your exact HTTPS origin, methods GET/PUT/HEAD, headers Content-Type/x-amz-meta-sha256/If-None-Match, and exposed ETag. Smoke-test multipart resume, cancellation, and a password-protected public download against your own bucket.
6. Keep `SCHEDULER_ENABLED=false` in API instances. The dedicated scheduler holds a PostgreSQL advisory lock so only one scheduler runs. It recovers pending/abandoned jobs every minute. Redis persistence is enabled, and pending file state in PostgreSQL allows scan dispatch recovery after a broker outage.

The production Compose file and Caddy configuration are provided for deployment; no public hostname, SMTP service, or cloud bucket is provisioned automatically.

## Monitoring

- Probe `/health/live` for the API process and `/health/ready` for database readiness. These endpoints do not claim that OCR, R2, or ClamAV is ready.
- Check `docker compose -f compose.production.yml exec worker celery -A app.core.celery_app.celery_app inspect ping` for worker availability.
- Inspect authenticated `/users/me/jobs` for scan/index state counts. `/users/me/storage` includes committed and reserved quota. Alert on a rising pending count, indexing failures, disk pressure, and absent worker pings.
- Do not log full share URLs or account reset/verification query strings. Caddy access logging is disabled; application and Uvicorn share-path logging is redacted. Preserve `Referrer-Policy: no-referrer` on all pages.
- Notifications use a bounded, bearer-authenticated SSE stream and reauthenticate on reconnect. The reverse proxy disables buffering. The fallback scan polling remains available.

## Backup and restore drill

Pause uploads and workers for a consistent database/object snapshot. Use a timestamped directory outside Git, with restricted filesystem permissions:

```sh
mkdir -p backups
docker compose -f compose.production.yml exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > backups/cloudvault.dump
docker compose -f compose.production.yml run --rm --no-deps -v "$PWD/backups:/backup" --entrypoint tar api czf /backup/uploads.tar.gz -C /app/uploads .
```

Encrypt the backup bundle before uploading it to a separate backup location. Back up the MFA encryption key through the secret manager, never in the repository. R2 payloads require a separate object backup/replication strategy; database dumps and local upload archives do not include them. Preserve object keys and hashes referenced by `storage_blobs`.

For each drill, provision a separate empty PostgreSQL database and separate local/object storage, restore using `pg_restore --no-owner`, mount restored uploads, apply `alembic upgrade head`, and verify user counts, blob references, quota totals, clean-file downloads, version restore, and public links. Run the drill without production SMTP or publicly accessible routes. Record the measured recovery time and last successful backup. Never point a restore at the active database.

## Search and OCR

Default search stays dependency-light. To enable learned local embeddings, install `requirements-semantic.txt`, or set `ENABLE_SEMANTIC_SEARCH=true` when building the production Compose stack. Set `EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2` identically in API and worker, and pre-download the model in the deployment environment. No document text is sent to an external embedding service. The first model load can download model weights; production API and worker containers share the `model_cache` volume.

The selected model must emit 384 dimensions. Reindex all clean files after changing models. Search filters by embedding model to prevent mixed-vector comparisons. PDFs with no extractable page text are rendered locally through PDFium and passed to Tesseract. Limits on pages, image pixels, and OCR time bound resource usage. Extraction failures appear as FAILED indexing state and can be retried; unsupported formats remain filename-searchable.
