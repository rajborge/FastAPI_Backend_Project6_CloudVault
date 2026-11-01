# Local email with Gmail app passwords

Enable 2-Step Verification for the sending Google account, then generate an app password at https://myaccount.google.com/apppasswords. App passwords may be unavailable for accounts restricted by an organization or certain security settings. See https://support.google.com/accounts/answer/185833.

Set these values in your private `.env` (never in `.env.example` or Git):

```dotenv
MAIL_HOST=smtp.gmail.com
MAIL_PORT=587
MAIL_STARTTLS=true
MAIL_SSL=false
MAIL_AUTH_ENABLED=true
MAIL_USERNAME=your-address@gmail.com
MAIL_FROM=your-address@gmail.com
MAIL_PASSWORD=your-app-password
FILE_SHARE_URL=http://localhost:5173
```

Use the app password, not the ordinary Google password. CloudVault strips visual spaces from Gmail app passwords at login. Alternatively use port 465 with `MAIL_SSL=true` and `MAIL_STARTTLS=false`.

Restart the API after changing `.env`: `docker compose up -d --force-recreate api`. No email credential should be entered into the CloudVault web interface or shared in chat.

In CloudVault, open **Account security → Email verification → Send verification email**. Delivery status reports SENT or a sanitized failure reason. Open the emailed link and click **Verify email**, then refresh verification status in the original app tab. Check spam if delivery reports SENT. A Gmail app password authenticates the sender; the account being verified must have an email address whose inbox you can access.

`FILE_SHARE_URL` must be the browser address of the frontend, not `http://api:8000` or a Docker hostname. For another device on the same LAN, use a frontend URL reachable from that device and configure the corresponding API/CORS addresses. A localhost link works only on the machine running the frontend.

Public forgot-password and verification-request responses remain generic to protect account privacy. Authenticated delivery diagnostics are visible only for the signed-in account. Failed SMTP delivery does not invalidate an earlier usable verification link. Links are single-use and expire after 30 minutes.

## Local MFA

Run `python scripts/setup_local_mfa.py` once, then recreate the API, worker and scheduler. This creates `.env.mfa.local`, a Git-ignored local key file loaded by Docker Compose. The key is never printed. Preserve this file: changing or losing it prevents existing MFA secrets from being decrypted. Your original `.env` is not modified.

Open **Account security → Two-step authentication**. Enter your CloudVault password, choose **Set up MFA**, then add the displayed setup key to a time-based account in your authenticator app. Enter its current six-digit code and choose **Enable MFA**. Save the one-use recovery codes privately. Email verification is independent of MFA enrollment.

`ACCOUNT_FRONTEND_URL` can explicitly set the destination for verification and reset links. For local development, an old `FILE_SHARE_URL=http://localhost:8000` now falls back to the configured frontend CORS origin; already-sent API-root links redirect to the frontend. Request a fresh email if a link has expired or was replaced by a newer request.
