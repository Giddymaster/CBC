"""One command that answers "why is no email arriving?".

    python manage.py email_test you@example.com

It prints what the container actually sees — provider, whether a key is
present, the from address — then attempts a real send and reports the
provider's verdict inline. The three failure modes it separates:

- key missing in THIS container  -> "stub mode" (fix .env.prod, recreate)
- provider refused the request   -> the HTTP status and response body
- all good                       -> SENT, and the message is in your inbox
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Diagnose transactional email: show config, then send a real test message."

    def add_arguments(self, parser):
        parser.add_argument("to", help="Address to send the test email to")

    def handle(self, *args, **options):
        to = options["to"]
        key = settings.EMAIL_API_KEY
        self.stdout.write(f"provider : {settings.EMAIL_API_PROVIDER}")
        self.stdout.write(
            f"api key  : {'SET (' + key[:6] + '…)' if key else 'NOT SET — stub mode, nothing will send'}"
        )
        self.stdout.write(f"from     : {settings.DEFAULT_FROM_EMAIL}")
        self.stdout.write(f"base url : {settings.APP_BASE_URL}")

        if not key:
            raise CommandError(
                "EMAIL_API_KEY is empty inside this container. Add it to "
                "deploy/.env.prod and run `dc up -d` so the containers are "
                "recreated with the new environment."
            )

        # Send directly (not through the logger-only wrapper) so the provider's
        # response is shown here, not buried in the logs.
        import requests

        provider = (settings.EMAIL_API_PROVIDER or "resend").lower()
        try:
            if provider == "sendgrid":
                from apps.communication.email import SENDGRID_URL, _bare_address

                response = requests.post(
                    SENDGRID_URL,
                    headers={"Authorization": f"Bearer {key}"},
                    json={
                        "personalizations": [{"to": [{"email": to}]}],
                        "from": {"email": _bare_address(settings.DEFAULT_FROM_EMAIL)},
                        "subject": "ShuleNest email test",
                        "content": [{"type": "text/plain", "value": "It works."}],
                    },
                    timeout=30,
                )
            else:
                from apps.communication.email import RESEND_URL

                response = requests.post(
                    RESEND_URL,
                    headers={"Authorization": f"Bearer {key}"},
                    json={
                        "from": settings.DEFAULT_FROM_EMAIL,
                        "to": [to],
                        "subject": "ShuleNest email test",
                        "html": "<b>It works.</b>",
                        "text": "It works.",
                    },
                    timeout=30,
                )
        except requests.RequestException as exc:
            raise CommandError(f"Network error reaching {provider}: {exc}")

        self.stdout.write(f"status   : {response.status_code}")
        self.stdout.write(f"response : {response.text[:500]}")
        if response.ok:
            self.stdout.write(self.style.SUCCESS(f"SENT — check {to} (and spam)."))
        else:
            raise CommandError(
                "The provider refused the send — the response above says why. "
                "Common causes: wrong API key; the from address is not on a "
                "domain verified in the provider's dashboard."
            )
