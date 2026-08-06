"""Create the platform operator and a starter plan, and give the demo school a
subscription so the control plane has something to show.

The operator is a superuser with **no school** — the plane boundary made
concrete. The demo `admin` stays a school admin and is not an operator.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.platform.models import Plan, Subscription
from apps.schools.models import School

User = get_user_model()


class Command(BaseCommand):
    help = "Seed the platform operator, a plan, and the demo school's subscription"

    def handle(self, *args, **options):
        operator, made = User.objects.get_or_create(
            username="owner",
            defaults={
                "first_name": "Platform",
                "last_name": "Owner",
                "is_superuser": True,
                "is_staff": True,
                "school": None,
            },
        )
        if made:
            operator.set_password("owner12345")
            operator.save()
            self.stdout.write("  + operator 'owner' (password 'owner12345')")
        else:
            self.stdout.write("  ~ operator 'owner' already exists")

        plan, _ = Plan.objects.get_or_create(
            name="Standard",
            defaults={
                "price_per_learner": "50.00",
                "minimum_charge": "3000.00",
                "trial_days": 30,
            },
        )
        self.stdout.write(f"  ~ plan '{plan.name}' — KES {plan.price_per_learner}/learner/term")

        school = School.objects.first()
        if school and not hasattr(school, "subscription"):
            today = timezone.localdate()
            Subscription.objects.create(
                school=school,
                plan=plan,
                status=Subscription.Status.TRIAL,
                trial_ends_on=today + timezone.timedelta(days=plan.trial_days),
                created_by=operator,
            )
            self.stdout.write(f"  + subscription for '{school.name}' (trial)")

        self.stdout.write(self.style.SUCCESS("Platform seeded."))
