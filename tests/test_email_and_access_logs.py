import logging
import smtplib
from unittest.mock import MagicMock

from uvicorn.logging import AccessFormatter
from app.core.config import settings
from app.core.privacy import CapabilityFilter
from app.services import account_service


def test_redaction_preserves_uvicorn_formatter_arguments():
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "",
        0,
        '%s - "%s %s HTTP/%s" %s',
        ("127.0.0.1:123", "GET", "/shares/private-token/download", "1.1", 200),
        None,
    )
    CapabilityFilter().filter(record)
    output = AccessFormatter(
        '%(client_addr)s - "%(request_line)s" %(status_code)s', use_colors=False
    ).format(record)
    assert "[redacted]" in output and "private-token" not in output
    assert len(record.args) == 5


def test_gmail_starttls_and_app_password_format(monkeypatch):
    smtp = MagicMock()
    monkeypatch.setattr(account_service.smtplib, "SMTP", smtp)
    monkeypatch.setattr(settings, "MAIL_HOST", "smtp.gmail.com")
    monkeypatch.setattr(settings, "MAIL_PORT", 587)
    monkeypatch.setattr(settings, "MAIL_SSL", False)
    monkeypatch.setattr(settings, "MAIL_STARTTLS", True)
    monkeypatch.setattr(settings, "MAIL_PASSWORD", "test app pass only")
    account_service.send_account_email("receiver@example.com", "test-token", "verify")
    connection = smtp.return_value.__enter__.return_value
    connection.starttls.assert_called_once()
    connection.login.assert_called_once_with(settings.MAIL_USERNAME, "testapppassonly")
    assert (
        "account_action=verify"
        in connection.send_message.call_args.args[0].get_content()
    )


def test_smtp_ssl_port_465_does_not_starttls(monkeypatch):
    smtp = MagicMock()
    monkeypatch.setattr(account_service.smtplib, "SMTP_SSL", smtp)
    monkeypatch.setattr(settings, "MAIL_PORT", 465)
    account_service.send_account_email("receiver@example.com", "test-token", "verify")
    smtp.return_value.__enter__.return_value.starttls.assert_not_called()


def test_email_failure_diagnostics_do_not_contain_provider_secrets():
    secret = "private-provider-value"
    message = account_service.delivery_error(
        smtplib.SMTPAuthenticationError(535, secret.encode())
    )
    assert secret not in message and "authentication failed" in message


def test_legacy_local_api_email_links_use_frontend(monkeypatch):
    monkeypatch.setattr(settings, "ACCOUNT_FRONTEND_URL", "")
    monkeypatch.setattr(settings, "FILE_SHARE_URL", "http://localhost:8000")
    monkeypatch.setattr(settings, "CORS_ORIGINS", "http://localhost:5173")
    assert settings.account_frontend_url == "http://localhost:5173"
    smtp = MagicMock()
    monkeypatch.setattr(account_service.smtplib, "SMTP", smtp)
    account_service.send_account_email("receiver@example.com", "test-token", "verify")
    body = smtp.return_value.__enter__.return_value.send_message.call_args.args[0].get_content()
    assert "http://localhost:5173/?account_action=verify" in body
    assert "localhost:8000" not in body


def test_existing_api_email_link_redirect_and_token_redaction(monkeypatch):
    from app.main import account_link_redirect
    from app.core.privacy import redact_path

    monkeypatch.setattr(settings, "ACCOUNT_FRONTEND_URL", "http://localhost:5173")
    response = account_link_redirect("verify", "test-private-token")
    assert response.status_code == 303
    assert response.headers["location"] == "http://localhost:5173/?account_action=verify&token=test-private-token"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "test-private-token" not in redact_path("/?account_action=verify&token=test-private-token")
