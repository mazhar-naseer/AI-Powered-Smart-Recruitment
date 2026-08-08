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
from app.models import EmailVerification, PasswordReset, User

settings = get_settings()
logger = logging.getLogger("email")


def _deliver(message: EmailMessage, filename: str) -> None:
    if settings.smtp_host:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            if settings.smtp_use_tls:
                smtp.starttls()
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password or "")
            smtp.send_message(message)
    else:
        outbox = Path(".outbox")
        outbox.mkdir(exist_ok=True)
        (outbox / filename).write_text(message.as_string(), encoding="utf-8")


def send_notification_email(user: User, title: str, body: str, action_url: str | None) -> None:
    link = f"{settings.frontend_url}{action_url}" if action_url and action_url.startswith("/") else (action_url or settings.frontend_url)
    message = EmailMessage()
    message["Subject"] = f"{title} | SmartHire"
    message["From"] = settings.smtp_from_email
    message["To"] = user.email
    message.set_content(f"Hello {user.full_name},\n\n{body}\n\nOpen SmartHire: {link}\n\nYou can manage email preferences in Notification Center.")
    message.add_alternative(f'''<!doctype html><html><body style="margin:0;background:#f3f6fb;font-family:Arial;color:#10204a"><table width="100%"><tr><td align="center" style="padding:36px 16px"><table width="620" style="max-width:100%;background:#fff;border:1px solid #dce5f1;border-radius:16px"><tr><td style="padding:26px 34px;background:#082b68;color:white;font-size:23px;font-weight:800">SmartHire</td></tr><tr><td style="padding:36px 34px"><div style="color:#07925a;font-size:12px;font-weight:800;letter-spacing:1px">ACCOUNT NOTIFICATION</div><h1 style="font-size:26px;margin:14px 0;color:#10204a">{escape(title)}</h1><p style="font-size:16px;line-height:1.7;color:#59677f">Hello {escape(user.full_name)},</p><p style="font-size:16px;line-height:1.7;color:#59677f">{escape(body)}</p><p style="margin:30px 0"><a href="{escape(link, quote=True)}" style="display:inline-block;padding:14px 24px;background:#1744bd;color:#fff;text-decoration:none;border-radius:8px;font-weight:700">View in SmartHire</a></p><p style="font-size:12px;color:#8994a8">Manage which events are emailed from your SmartHire Notification Center.</p></td></tr></table></td></tr></table></body></html>''', subtype="html")
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")
    _deliver(message, f"notification-{user.id}-{stamp}.txt")


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


def issue_password_reset(db: Session, user: User) -> None:
    token = secrets.token_urlsafe(32)
    db.execute(update(PasswordReset).where(PasswordReset.user_id == user.id, PasswordReset.consumed_at.is_(None)).values(consumed_at=datetime.now(UTC)))
    db.add(PasswordReset(user_id=user.id, token_hash=_hash(token), expires_at=datetime.now(UTC) + timedelta(minutes=settings.password_reset_minutes)))
    link = f"{settings.frontend_url}/reset-password?token={token}"
    message = EmailMessage()
    message["Subject"] = "Reset your SmartHire password"
    message["From"] = settings.smtp_from_email
    message["To"] = user.email
    message.set_content(f"Hello {user.full_name},\n\nUse this link to reset your SmartHire password: {link}\n\nThis link expires in {settings.password_reset_minutes} minutes. If you did not request this, you can ignore this email.")
    safe_link = escape(link, quote=True)
    message.add_alternative(f"""<!doctype html><html><body style=\"margin:0;background:#f3f6fb;font-family:Arial;color:#10204a\"><table width=\"100%\"><tr><td align=\"center\" style=\"padding:36px 16px\"><table width=\"620\" style=\"max-width:100%;background:#fff;border:1px solid #dce5f1;border-radius:16px\"><tr><td style=\"padding:26px 34px;background:#082b68;color:#fff;font-size:23px;font-weight:800\">SmartHire</td></tr><tr><td style=\"padding:36px 34px\"><div style=\"color:#087848;font-size:12px;font-weight:800;letter-spacing:1px\">SECURITY</div><h1 style=\"font-size:26px;margin:14px 0\">Reset your password</h1><p>Hello {escape(user.full_name)},</p><p>We received a request to reset your SmartHire password. This link expires in {settings.password_reset_minutes} minutes.</p><p style=\"margin:30px 0\"><a href=\"{safe_link}\" style=\"display:inline-block;padding:14px 24px;background:#1744bd;color:#fff;text-decoration:none;border-radius:8px;font-weight:700\">Reset password</a></p><p style=\"font-size:12px;color:#8994a8;word-break:break-all\">If the button does not work, copy this link: {safe_link}</p><p style=\"font-size:12px;color:#8994a8\">If you did not request a password reset, you can safely ignore this email.</p></td></tr></table></td></tr></table></body></html>""", subtype="html")
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")
    _deliver(message, f"password-reset-{user.id}-{stamp}.txt")


def send_team_invitation(email: str, inviter_name: str, organization_name: str, role: str, token: str) -> None:
    link = f"{settings.frontend_url}/team/invitations/{token}"
    message = EmailMessage()
    message["Subject"] = f"Join {organization_name} on SmartHire"
    message["From"] = settings.smtp_from_email
    message["To"] = email
    message.set_content(f"{inviter_name} invited you to join {organization_name} as {role}.\n\nAccept invitation: {link}\n\nThis invitation expires in 7 days.")
    message.add_alternative(f"""<!doctype html><html><body style="margin:0;background:#f3f6fb;font-family:Arial;color:#12234c"><table width="100%"><tr><td align="center" style="padding:40px 16px"><table width="600" style="max-width:100%;background:#fff;border:1px solid #dce4f0;border-radius:16px"><tr><td style="padding:28px;background:#092966;color:#fff;font-size:24px;font-weight:800">SmartHire</td></tr><tr><td style="padding:38px"><p style="color:#087848;font-weight:700">RECRUITER TEAM INVITATION</p><h1>Join {escape(organization_name)}</h1><p style="color:#59677f;line-height:1.7">{escape(inviter_name)} invited you to collaborate as <strong>{escape(role)}</strong>.</p><p style="margin:30px 0"><a href="{escape(link,quote=True)}" style="padding:14px 24px;border-radius:8px;background:#1744bd;color:#fff;text-decoration:none;font-weight:700">Accept invitation</a></p><p style="color:#8994a8;font-size:12px">This secure invitation expires in seven days.</p></td></tr></table></td></tr></table></body></html>""",subtype="html")
    if settings.smtp_host:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            if settings.smtp_use_tls:smtp.starttls()
            if settings.smtp_username:smtp.login(settings.smtp_username, settings.smtp_password or "")
            smtp.send_message(message)
    else:
        outbox=Path(".outbox");outbox.mkdir(exist_ok=True);(outbox/f"invite-{hashlib.sha256(email.encode()).hexdigest()[:16]}.txt").write_text(message.as_string(),encoding="utf-8")


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
