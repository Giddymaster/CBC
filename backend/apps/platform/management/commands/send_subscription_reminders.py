"""Daily subscription reminders to a school's leadership.

    python manage.py send_subscription_reminders

Two windows, one email a day per school:

- **Ending soon** — while a school still has full access and the horizon
  (paid term, or trial end) is 1–5 days away, a countdown reminder. That five-day
  cap is the whole pre-expiry campaign: at most five emails, one per day.
- **Lapsed** — once the term has run out and the system is read-only, a daily
  renewal nudge until it is sorted or the school is cancelled.

`last_reminder_on` guards the once-a-day promise: the command can run hourly (or
be retried) and never sends a school two emails in a day. Cron it once a
morning; nothing breaks if it fires more often.

    # crontab: 07:00 daily
    0 7 * * * cd /root/CBC && dc run --rm web python manage.py send_subscription_reminders
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.platform.models import Subscription
from apps.platform.reminders import send_expiry_reminder, send_lapsed_reminder

PRE_EXPIRY_WINDOW = 5  # days before the horizon that reminders begin


class Command(BaseCommand):
    help = "Email a school's head/deputy/admin when its subscription is ending or has lapsed."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Report who would be emailed without sending or recording anything.",
        )

    def handle(self, *args, **options):
        today = timezone.localdate()
        dry = options["dry_run"]
        expiring = lapsed = skipped = 0

        subs = Subscription.objects.select_related("school", "plan")
        for sub in subs:
            state = sub.effective_state(today)
            # Cancelled schools are off-boarded — the operator drives those, not
            # a daily nudge. Already reminded today — the once-a-day guard.
            if state == Subscription.CANCELLED_STATE:
                continue
            if sub.last_reminder_on == today:
                skipped += 1
                continue

            phase = None
            days = sub.days_left(today)
            if state in (Subscription.ACTIVE_STATE, Subscription.TRIAL_STATE):
                if days is not None and 0 < days <= PRE_EXPIRY_WINDOW:
                    phase = "expiring"
            elif state in (Subscription.GRACE_STATE, Subscription.READ_ONLY_STATE):
                phase = "lapsed"

            if phase is None:
                continue

            if dry:
                self.stdout.write(
                    f"[dry] {sub.school.name}: {phase}"
                    + (f" ({days}d left)" if phase == "expiring" else "")
                )
            else:
                sent = (
                    send_expiry_reminder(sub.school, days)
                    if phase == "expiring"
                    else send_lapsed_reminder(sub.school)
                )
                if sent:
                    sub.last_reminder_on = today
                    sub.save(update_fields=["last_reminder_on", "updated_at"])

            if phase == "expiring":
                expiring += 1
            else:
                lapsed += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"{'Would remind' if dry else 'Reminded'}: {expiring} ending soon, "
                f"{lapsed} lapsed. {skipped} already reminded today."
            )
        )
