import hashlib
import json
import logging
import secrets
import smtplib
import urllib.request
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from html import escape
from pathlib import Path

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import EmailVerification, User

settings = get_settings()
logger = logging.getLogger("email")


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def build_verification_message(user: User, code: str, link: str) -> EmailMessage:
    """Build a responsive multipart verification email for major email clients."""
    safe_name = escape(user.full_name)
    safe_code = escape(code)
    safe_link = escape(link, quote=True)
    minutes = settings.email_verification_minutes
    message = EmailMessage()
    message["Subject"] = f"{code} is your SmartHire verification code"
    message["From"] = settings.smtp_from_email
    message["To"] = user.email
    message.set_content(
        f"Hello {user.full_name},\n\n"
        "Welcome to SmartHire. Verify your email address to activate your account.\n\n"
        f"Verification code: {code}\n\nVerify your account: {link}\n\n"
        f"This code and link expire in {minutes} minutes. If you did not create a "
        "SmartHire account, you can safely ignore this email.\n\nSmartHire Security Team"
    )
    message.add_alternative(
        f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Verify your SmartHire account</title></head>
<body style="margin:0;padding:0;background:#f3f6fb;font-family:Arial,Helvetica,sans-serif;color:#111d45;">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;">Your SmartHire verification code is {safe_code}. It expires in {minutes} minutes.</div>
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#f3f6fb;"><tr><td align="center" style="padding:36px 16px;">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="max-width:620px;background:#fff;border:1px solid #dde5f1;border-radius:18px;overflow:hidden;box-shadow:0 12px 32px rgba(10,39,94,.10);">
<tr><td style="padding:30px 38px;background:#06265f;"><table role="presentation" cellspacing="0" cellpadding="0" border="0"><tr><td style="width:42px;height:42px;text-align:center;border-radius:12px;background:#0a9b62;color:#fff;font-size:23px;font-weight:800;">S</td><td style="padding-left:12px;color:#fff;font-size:24px;font-weight:800;letter-spacing:-.4px;">SmartHire</td></tr></table></td></tr>
<tr><td style="padding:42px 38px 34px;">
<div style="display:inline-block;padding:7px 12px;border-radius:999px;background:#eaf8f1;color:#087848;font-size:12px;font-weight:700;letter-spacing:.4px;text-transform:uppercase;">Secure account verification</div>
<h1 style="margin:22px 0 12px;color:#0b1f4f;font-size:30px;line-height:1.2;letter-spacing:-.7px;">Confirm your email address</h1>
<p style="margin:0 0 18px;color:#4d5b75;font-size:16px;line-height:1.7;">Hello {safe_name},</p>
<p style="margin:0;color:#4d5b75;font-size:16px;line-height:1.7;">Welcome to SmartHire. Use the code below to activate your account and securely continue your hiring journey.</p>
<div style="margin:30px 0;padding:24px;text-align:center;border:1px solid #dce5f3;border-radius:14px;background:#f7f9fd;"><div style="margin-bottom:10px;color:#6b7790;font-size:12px;font-weight:700;letter-spacing:1.2px;text-transform:uppercase;">Verification code</div><div style="color:#1236b5;font-size:36px;font-weight:800;letter-spacing:9px;line-height:1.2;">{safe_code}</div></div>
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"><tr><td align="center"><a href="{safe_link}" style="display:inline-block;padding:15px 28px;border-radius:9px;background:#1236b5;color:#fff;text-decoration:none;font-size:15px;font-weight:700;">Verify my account</a></td></tr></table>
<p style="margin:26px 0 0;color:#6b7790;font-size:13px;line-height:1.6;text-align:center;">This code and verification link expire in <strong>{minutes} minutes</strong>.</p>
<div style="margin-top:28px;padding:18px;border-radius:10px;background:#fff8e8;color:#72531b;font-size:13px;line-height:1.6;"><strong>Security notice:</strong> SmartHire will never ask you to share this code. If you did not create this account, you can safely ignore this email.</div>
<p style="margin:28px 0 0;color:#7a859b;font-size:12px;line-height:1.6;word-break:break-all;">Button not working? Copy and paste this link into your browser:<br><a href="{safe_link}" style="color:#1236b5;">{safe_link}</a></p>
</td></tr><tr><td style="padding:24px 38px;border-top:1px solid #e6ebf3;background:#f9fbfe;text-align:center;color:#8390a6;font-size:12px;line-height:1.6;">© {datetime.now(UTC).year} SmartHire · Smarter matching. Stronger teams.<br>This is an automated security email; please do not reply.</td></tr>
</table></td></tr></table></body></html>""",
        subtype="html",
    )
    return message


def _send_over_brevo(message: EmailMessage) -> None:
    """Hand the message to Brevo's HTTPS transactional endpoint.

    Plain urllib, matching app.ai_provider — one HTTPS POST does not justify a
    dependency. urlopen raises HTTPError on a non-2xx, so a rejected sender or a
    bad key surfaces as an exception rather than a silent no-op.
    """
    payload = {
        "sender": {"email": settings.smtp_from_email, "name": settings.smtp_from_name},
        "to": [{"email": message["To"]}],
        "subject": message["Subject"],
        "textContent": message.get_body(preferencelist=("plain",)).get_content(),
        "htmlContent": message.get_body(preferencelist=("html",)).get_content(),
    }
    request = urllib.request.Request(
        "https://api.brevo.com/v3/smtp/email",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "api-key": settings.brevo_api_key},
    )
    with urllib.request.urlopen(request, timeout=settings.smtp_timeout_seconds):
        pass


def _send_over_smtp(message: EmailMessage) -> None:
    # Port 465 is implicit TLS: the handshake happens before any SMTP command, so
    # STARTTLS on that port fails. Ports 587 and 25 upgrade an existing plaintext
    # connection instead. Choosing on the port rather than on smtp_use_tls alone
    # means a 465 provider works without a second, easily-forgotten setting.
    timeout = settings.smtp_timeout_seconds
    if settings.smtp_port == 465:
        client = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=timeout)
    else:
        client = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=timeout)
    with client as smtp:
        if settings.smtp_use_tls and settings.smtp_port != 465:
            smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password or "")
        smtp.send_message(message)


def _deliver(message: EmailMessage, user: User) -> bool:
    """Send the message, returning whether it actually left the process.

    Never raises. Delivery is a side effect of registration, not part of it: a
    refused login, a blocked port, or a provider timeout must not undo an
    otherwise valid signup. The caller decides how to tell the user.
    """
    # Brevo wins when both are set. SMTP is unreachable on the hosts that make
    # an HTTPS provider necessary, so trying it first would only add a timeout.
    transport = _send_over_brevo if settings.brevo_api_key else _send_over_smtp
    if settings.brevo_api_key or settings.smtp_host:
        try:
            transport(message)
        except Exception:
            # Recipient only, never the code or token — this log is not a safe
            # place for a credential that grants account access.
            logger.exception("Verification email to %s could not be sent", user.email)
            return False
        return True

    # No provider configured. Local development reads these files; on an
    # ephemeral host they are only a breadcrumb, so a failed write is not worth
    # an error.
    try:
        outbox = Path(".outbox")
        outbox.mkdir(exist_ok=True)
        (outbox / f"{user.id}.txt").write_text(message.as_string(), encoding="utf-8")
    except OSError:
        logger.warning("No email provider is configured and .outbox is not writable")
    return False


def issue_email_verification(db: Session, user: User) -> tuple[str, str, bool]:
    token, code = secrets.token_urlsafe(32), f"{secrets.randbelow(1_000_000):06d}"
    db.execute(
        update(EmailVerification)
        .where(EmailVerification.user_id == user.id, EmailVerification.consumed_at.is_(None))
        .values(consumed_at=datetime.now(UTC))
    )
    db.add(EmailVerification(
        user_id=user.id, token_hash=_hash(token), code_hash=_hash(code),
        expires_at=datetime.now(UTC) + timedelta(minutes=settings.email_verification_minutes),
    ))
    link = f"{settings.frontend_url}/verify-email?token={token}"
    message = build_verification_message(user, code, link)
    return token, code, _deliver(message, user)


def consume_verification(db: Session, *, email: str | None, code: str | None, token: str | None) -> User | None:
    query = None
    if token:
        query = db.query(EmailVerification).filter(EmailVerification.token_hash == _hash(token))
    elif email and code:
        query = (
            db.query(EmailVerification).join(User)
            .filter(User.email == email.lower().strip(), EmailVerification.code_hash == _hash(code))
        )
    if query is None:
        return None
    verification = query.filter(EmailVerification.consumed_at.is_(None)).order_by(EmailVerification.created_at.desc()).first()
    if not verification or verification.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
        return None
    user = db.get(User, verification.user_id)
    verification.consumed_at = datetime.now(UTC)
    user.email_verified = True
    return user
