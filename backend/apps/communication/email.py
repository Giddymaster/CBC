"""Transactional email, one door for the whole app.

Same shape as the SMS sender next door: without an API key it logs and returns
STUBBED, so verification, password reset and any future notice work end to end
on a laptop with no account. With a key it posts to the configured provider —
Resend or SendGrid — which are HTTPS APIs, so no SMTP host or port to babysit.

Callers pass HTML and a plain-text fallback; a mail client that refuses HTML
still shows something readable, and so does the stub log.
"""

import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

RESEND_URL = "https://api.resend.com/emails"
SENDGRID_URL = "https://api.sendgrid.com/v3/mail/send"

SENT = "SENT"
STUBBED = "STUBBED"
FAILED = "FAILED"


def send_email(to: str, subject: str, *, html: str, text: str = "") -> str:
    """Send one email; return SENT / STUBBED / FAILED. Never raises — a failed
    notice must not take down the request that triggered it."""
    if not to:
        return FAILED
    if not settings.EMAIL_API_KEY:
        logger.info("EMAIL (stub) to %s: %s\n%s", to, subject, text or html)
        return STUBBED

    provider = (settings.EMAIL_API_PROVIDER or "resend").lower()
    try:
        if provider == "sendgrid":
            return _sendgrid(to, subject, html, text)
        return _resend(to, subject, html, text)
    except requests.RequestException as exc:
        logger.error("Email to %s failed: %s", to, exc)
        return FAILED


def _resend(to, subject, html, text):
    response = requests.post(
        RESEND_URL,
        headers={"Authorization": f"Bearer {settings.EMAIL_API_KEY}"},
        json={
            "from": settings.DEFAULT_FROM_EMAIL,
            "to": [to],
            "subject": subject,
            "html": html,
            **({"text": text} if text else {}),
        },
        timeout=30,
    )
    if response.ok:
        return SENT
    logger.error("Resend rejected mail to %s: %s %s", to, response.status_code, response.text[:300])
    return FAILED


def _sendgrid(to, subject, html, text):
    content = [{"type": "text/plain", "value": text}] if text else []
    content.append({"type": "text/html", "value": html})
    response = requests.post(
        SENDGRID_URL,
        headers={"Authorization": f"Bearer {settings.EMAIL_API_KEY}"},
        json={
            "personalizations": [{"to": [{"email": to}]}],
            "from": {"email": _bare_address(settings.DEFAULT_FROM_EMAIL)},
            "subject": subject,
            "content": content,
        },
        timeout=30,
    )
    if response.ok:
        return SENT
    logger.error("SendGrid rejected mail to %s: %s %s", to, response.status_code, response.text[:300])
    return FAILED


def _bare_address(value):
    """"Name <a@b.com>" -> "a@b.com"; SendGrid wants the address alone."""
    if "<" in value and ">" in value:
        return value[value.index("<") + 1 : value.index(">")].strip()
    return value.strip()
