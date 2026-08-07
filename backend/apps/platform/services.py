"""Provisioning a school, and the invoice lifecycle."""

import secrets

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework.authtoken.models import Token

from apps.common.audit import record as audit
from apps.schools.models import School

from .models import Subscription, SubscriptionInvoice

User = get_user_model()


def _unique_admin_username(source):
    """A stable, collision-free username derived from a person's name."""
    base = "".join(ch for ch in source.lower() if ch.isalnum())[:12] or "admin"
    username, n = f"{base}admin", 1
    while User.objects.filter(username=username).exists():
        n += 1
        username = f"{base}admin{n}"
    return username


def provision_school(
    *, name, code, county, plan, operator,
    admin_first_name, admin_last_name, admin_username="", admin_password="",
    admin_phone="", admin_email="", **school_extra,
):
    """Create a school, its first admin, and a trial subscription — atomically.

    Returns (school, admin, subscription, generated_password | None). The
    password is handed back once so you can pass it to the school; only its hash
    is stored. The admin must replace it on first sign-in.
    """
    with transaction.atomic():
        school = School.objects.create(
            name=name, code=code, county=county, **school_extra
        )

        username = (admin_username or "").strip().lower()
        if not username:
            base = "".join(ch for ch in name.lower() if ch.isalnum())[:12] or "admin"
            username, n = f"{base}admin", 1
            while User.objects.filter(username=username).exists():
                n += 1
                username = f"{base}admin{n}"

        generated = None
        password = admin_password
        if not password:
            password = secrets.token_urlsafe(9)
            generated = password

        admin = User.objects.create_user(
            username=username,
            password=password,
            first_name=admin_first_name,
            last_name=admin_last_name,
            role="ADMIN",
            school=school,
            phone=admin_phone,
            email=admin_email,
        )
        # An operator-issued password is a handover credential.
        admin.must_change_password = True
        admin.save(update_fields=["must_change_password"])

        today = timezone.localdate()
        subscription = Subscription.objects.create(
            school=school,
            plan=plan,
            status=Subscription.Status.TRIAL,
            trial_ends_on=today + timezone.timedelta(days=plan.trial_days),
            created_by=operator,
        )

        audit(
            actor=operator,
            school=school,
            action="SCHOOL_PROVISIONED",
            target=school,
            label=school.name,
            detail={"plan": plan.name, "trial_days": plan.trial_days},
        )
    return school, admin, subscription, generated


def reset_admin_password(*, admin, operator):
    """Issue a fresh handover password for a school admin who is locked out.

    Returns the plaintext password once. The account is flagged so the admin
    must replace it at first sign-in, and the old token is killed so the person
    who lost access truly has to use the new one.
    """
    password = secrets.token_urlsafe(9)
    admin.set_password(password)
    admin.must_change_password = True
    admin.password_changed_at = timezone.now()
    admin.save(
        update_fields=["password", "must_change_password", "password_changed_at"]
    )
    Token.objects.filter(user=admin).delete()
    audit(
        actor=operator,
        school=admin.school,
        action="PASSWORD_RESET",
        target=admin,
        label=admin.get_full_name() or admin.username,
        detail={"by": "operator", "forced_change": True},
    )
    return password


def replace_school_admin(
    *, school, operator, first_name, last_name,
    phone="", email="", username="",
):
    """The school changed hands: create its new admin and retire the old one.

    Every currently-active admin of the school is deactivated (and their tokens
    dropped), so exactly one person holds the keys afterwards. Returns
    (new_admin, generated_password).
    """
    with transaction.atomic():
        uname = (username or "").strip().lower()
        if uname and User.objects.filter(username__iexact=uname).exists():
            raise ValueError("A user with that username already exists.")
        if not uname:
            uname = _unique_admin_username(f"{first_name}{last_name}")

        generated = secrets.token_urlsafe(9)
        pw = generated

        retired = list(
            school.users.filter(role=User.Role.ADMIN, is_active=True)
        )

        new_admin = User.objects.create_user(
            username=uname,
            password=pw,
            first_name=first_name,
            last_name=last_name,
            role=User.Role.ADMIN,
            school=school,
            phone=phone,
            email=email,
        )
        new_admin.must_change_password = True
        new_admin.save(update_fields=["must_change_password"])

        for old in retired:
            old.is_active = False
            old.save(update_fields=["is_active"])
            Token.objects.filter(user=old).delete()

        audit(
            actor=operator,
            school=school,
            action="ADMIN_REPLACED",
            target=new_admin,
            label=new_admin.get_full_name() or uname,
            detail={"retired": [u.username for u in retired]},
        )
    return new_admin, generated


def active_learner_count(school):
    from apps.students.models import Learner

    return Learner.objects.filter(school=school, active=True).count()


def issue_invoice(*, subscription, period_label, period_end, operator,
                  period_start=None, due_on=None, learner_count=None):
    """Raise a term's bill. Amount is snapshotted from the plan and the current
    active-learner count."""
    plan = subscription.plan
    if learner_count is None:
        learner_count = active_learner_count(subscription.school)
    amount = plan.quote(learner_count)

    invoice = SubscriptionInvoice.objects.create(
        subscription=subscription,
        period_label=period_label,
        period_start=period_start,
        period_end=period_end,
        learner_count=learner_count,
        unit_price=plan.price_per_learner,
        minimum_charge=plan.minimum_charge,
        amount=amount,
        currency=plan.currency,
        status=SubscriptionInvoice.Status.SENT,
        due_on=due_on,
    )
    audit(
        actor=operator,
        school=subscription.school,
        action="SUBSCRIPTION_INVOICED",
        target=invoice,
        label=f"{subscription.school.name} — {period_label}",
        detail={"amount": str(amount), "learners": learner_count},
    )
    return invoice


def mark_invoice_paid(*, invoice, operator, reference="", paid_on=None):
    """Record payment and extend access through the term it covers."""
    paid_on = paid_on or timezone.localdate()
    invoice.status = SubscriptionInvoice.Status.PAID
    invoice.paid_on = paid_on
    invoice.payment_reference = reference
    invoice.marked_by = operator
    invoice.save(update_fields=[
        "status", "paid_on", "payment_reference", "marked_by", "updated_at"
    ])

    subscription = invoice.subscription
    # Extend paid_through to the furthest term ever paid, and leave a trial.
    if subscription.paid_through is None or invoice.period_end > subscription.paid_through:
        subscription.paid_through = invoice.period_end
    if subscription.status == Subscription.Status.TRIAL:
        subscription.status = Subscription.Status.ACTIVE
    subscription.save(update_fields=["paid_through", "status", "updated_at"])

    audit(
        actor=operator,
        school=subscription.school,
        action="SUBSCRIPTION_PAID",
        target=invoice,
        label=f"{subscription.school.name} — {invoice.period_label}",
        detail={"amount": str(invoice.amount), "reference": reference},
    )
    return invoice


def set_subscription_status(*, subscription, status, operator):
    """Operator override: cancel a school, or reactivate a cancelled one."""
    subscription.status = status
    subscription.save(update_fields=["status", "updated_at"])
    audit(
        actor=operator,
        school=subscription.school,
        action="SUBSCRIPTION_STATUS",
        target=subscription,
        label=f"{subscription.school.name} → {status}",
    )
    return subscription
