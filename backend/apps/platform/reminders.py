"""Who to email about a subscription, and what to say.

The command (management/commands/send_subscription_reminders.py) runs this daily;
the request-extension view calls the operator-notification directly. Kept apart
from views and models so both callers share one definition of "the school's
leadership" and the message wording.
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Q

from apps.communication.email import send_email

User = get_user_model()


def leadership_recipients(school):
    """Head teacher, deputy and admin of a school who have an email — the people
    a renewal notice should reach."""
    return list(
        User.objects.filter(school=school, is_active=True)
        .exclude(email="")
        .filter(Q(role="ADMIN") | Q(teacher_profile__rank__in=("HEAD", "DEPUTY")))
        .distinct()
    )


def operator_recipients():
    """Platform operators with an email, plus any OPS_EMAIL fallback."""
    emails = list(
        User.objects.filter(is_superuser=True, school__isnull=True, is_active=True)
        .exclude(email="")
        .values_list("email", flat=True)
    )
    fallback = getattr(settings, "OPS_EMAIL", "")
    if fallback and fallback not in emails:
        emails.append(fallback)
    return emails


def _subscription_link():
    return f"{settings.APP_BASE_URL}/admin/subscription"


def send_expiry_reminder(school, days_left):
    """Pre-expiry: N days to go."""
    recipients = leadership_recipients(school)
    if not recipients:
        return 0
    link = _subscription_link()
    subject = f"ShuleNest subscription ends in {days_left} day{'s' if days_left != 1 else ''}"
    for user in recipients:
        name = user.get_full_name() or user.username
        send_email(
            user.email,
            subject,
            html=(
                f"<p>Hi {name},</p>"
                f"<p><b>{school.name}</b>'s ShuleNest subscription ends in "
                f"<b>{days_left} day{'s' if days_left != 1 else ''}</b>. Renew before then "
                f"to keep full access — after it lapses the system turns read-only "
                f"until payment.</p>"
                f'<p><a href="{link}">View your subscription</a></p>'
            ),
            text=(
                f"Hi {name},\n\n{school.name}'s ShuleNest subscription ends in "
                f"{days_left} days. Renew before then to keep full access; after it "
                f"lapses the system turns read-only until payment.\n\n{link}"
            ),
        )
    return len(recipients)


def send_lapsed_reminder(school):
    """Post-expiry: read-only, please renew."""
    recipients = leadership_recipients(school)
    if not recipients:
        return 0
    link = _subscription_link()
    subject = f"ShuleNest is read-only — renew {school.name}"
    for user in recipients:
        name = user.get_full_name() or user.username
        send_email(
            user.email,
            subject,
            html=(
                f"<p>Hi {name},</p>"
                f"<p><b>{school.name}</b>'s ShuleNest subscription has lapsed, so the "
                f"system is now <b>read-only</b> — your data is safe and fully visible, "
                f"but nothing can be edited until the subscription is renewed.</p>"
                f'<p><a href="{link}">Renew or request an extension</a></p>'
            ),
            text=(
                f"Hi {name},\n\n{school.name}'s ShuleNest subscription has lapsed, so "
                f"the system is now read-only. Your data is safe and visible, but "
                f"nothing can be edited until it is renewed.\n\n{link}"
            ),
        )
    return len(recipients)


def notify_operator_extension_request(*, school, requested_by, note=""):
    """A school's leadership asked to renew/extend — tell the operator."""
    emails = operator_recipients()
    if not emails:
        return 0
    who = requested_by.get_full_name() or requested_by.username
    body_note = f"<p>Note: {note}</p>" if note else ""
    text_note = f"\nNote: {note}\n" if note else ""
    for email in emails:
        send_email(
            email,
            f"Extension requested — {school.name}",
            html=(
                f"<p><b>{school.name}</b> ({school.code}) has requested a "
                f"subscription extension.</p>"
                f"<p>Requested by {who}.</p>{body_note}"
                f'<p><a href="{settings.APP_BASE_URL}/operator">Open the operator console</a></p>'
            ),
            text=(
                f"{school.name} ({school.code}) has requested a subscription "
                f"extension.\nRequested by {who}.{text_note}\n"
                f"{settings.APP_BASE_URL}/operator"
            ),
        )
    return len(emails)
