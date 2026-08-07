"""Control-plane API.

Two audiences, kept strictly apart:

- **The operator** (`/api/platform/...`) provisions schools, manages plans,
  issues invoices, marks them paid, and posts announcements. Superuser only.
- **A school admin** may read their *own* school's standing (`/api/my-school/
  subscription/`) and the announcements addressed to them. Nothing else of the
  control plane is visible to a tenant.
"""

from django.contrib.auth import get_user_model
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.audit import record as audit
from apps.schools.models import School
from apps.schools.serializers import SchoolSerializer

from .access import is_operator
from .models import (
    AnnouncementReceipt,
    Plan,
    PlatformAnnouncement,
    Subscription,
    SubscriptionInvoice,
)
from .services import (
    active_learner_count,
    issue_invoice,
    mark_invoice_paid,
    provision_school,
    replace_school_admin,
    reset_admin_password,
    set_subscription_status,
)

User = get_user_model()


def _admin_dict(user):
    """The safe, operator-visible view of a school's admin account. Contact and
    status only — never anything from the tenant's own records."""
    return {
        "id": user.id,
        "username": user.username,
        "name": user.get_full_name() or user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "phone": user.phone,
        "email": user.email,
        "is_active": user.is_active,
        "must_change_password": user.must_change_password,
        "last_login": user.last_login.isoformat() if user.last_login else None,
    }


class IsOperator(BasePermission):
    message = "This is the platform operator area."

    def has_permission(self, request, view):
        return is_operator(request.user)


# --- Serializers ---------------------------------------------------------
class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = "__all__"


class InvoiceSerializer(serializers.ModelSerializer):
    school = serializers.CharField(source="subscription.school.name", read_only=True)
    overdue = serializers.SerializerMethodField()

    class Meta:
        model = SubscriptionInvoice
        fields = "__all__"
        read_only_fields = [
            "subscription", "learner_count", "unit_price", "minimum_charge",
            "amount", "currency", "status", "paid_on", "marked_by",
        ]

    def get_overdue(self, obj):
        return obj.is_overdue()


class SubscriptionSerializer(serializers.ModelSerializer):
    school_name = serializers.CharField(source="school.name", read_only=True)
    school_code = serializers.CharField(source="school.code", read_only=True)
    plan_name = serializers.CharField(source="plan.name", read_only=True)
    state = serializers.SerializerMethodField()
    can_write = serializers.SerializerMethodField()
    days_left = serializers.SerializerMethodField()
    learners = serializers.SerializerMethodField()
    outstanding = serializers.SerializerMethodField()

    class Meta:
        model = Subscription
        fields = [
            "id", "school", "school_name", "school_code", "plan", "plan_name",
            "status", "trial_ends_on", "paid_through", "grace_days", "notes",
            "state", "can_write", "days_left", "learners", "outstanding",
        ]
        read_only_fields = ["school"]

    def get_state(self, obj):
        return obj.effective_state()

    def get_can_write(self, obj):
        return obj.can_write()

    def get_days_left(self, obj):
        return obj.days_left()

    def get_learners(self, obj):
        return active_learner_count(obj.school)

    def get_outstanding(self, obj):
        return obj.invoices.filter(
            status=SubscriptionInvoice.Status.SENT
        ).count()


# --- Operator: plans -----------------------------------------------------
class PlanViewSet(viewsets.ModelViewSet):
    queryset = Plan.objects.all()
    serializer_class = PlanSerializer
    permission_classes = [IsOperator]


# --- Operator: subscriptions --------------------------------------------
class SubscriptionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Subscription.objects.select_related("school", "plan").all()
    serializer_class = SubscriptionSerializer
    permission_classes = [IsOperator]
    filterset_fields = ["status", "plan"]
    search_fields = ["school__name", "school__code"]

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        sub = self.get_object()
        set_subscription_status(
            subscription=sub, status=Subscription.Status.CANCELLED, operator=request.user
        )
        return Response(SubscriptionSerializer(sub).data)

    @action(detail=True, methods=["post"])
    def reactivate(self, request, pk=None):
        sub = self.get_object()
        # Back to active if a term is still paid, else trial's over → they owe.
        set_subscription_status(
            subscription=sub, status=Subscription.Status.ACTIVE, operator=request.user
        )
        return Response(SubscriptionSerializer(sub).data)

    @action(detail=True, methods=["post"])
    def invoice(self, request, pk=None):
        """Raise a term's invoice for this school."""
        sub = self.get_object()
        label = (request.data.get("period_label") or "").strip()
        period_end = request.data.get("period_end")
        if not label or not period_end:
            raise ValidationError(
                {"detail": "period_label and period_end are required."}
            )
        invoice = issue_invoice(
            subscription=sub,
            period_label=label,
            period_start=request.data.get("period_start") or None,
            period_end=period_end,
            due_on=request.data.get("due_on") or None,
            operator=request.user,
        )
        return Response(InvoiceSerializer(invoice).data, status=201)


class InvoiceViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = SubscriptionInvoice.objects.select_related(
        "subscription__school"
    ).all()
    serializer_class = InvoiceSerializer
    permission_classes = [IsOperator]
    filterset_fields = ["status", "subscription"]

    @action(detail=True, methods=["post"], url_path="mark-paid")
    def mark_paid(self, request, pk=None):
        invoice = self.get_object()
        if invoice.status == SubscriptionInvoice.Status.PAID:
            return Response({"detail": "Already paid."}, status=400)
        mark_invoice_paid(
            invoice=invoice,
            operator=request.user,
            reference=request.data.get("reference", ""),
        )
        return Response(InvoiceSerializer(invoice).data)

    @action(detail=True, methods=["post"])
    def void(self, request, pk=None):
        invoice = self.get_object()
        invoice.status = SubscriptionInvoice.Status.VOID
        invoice.save(update_fields=["status", "updated_at"])
        return Response(InvoiceSerializer(invoice).data)


# --- Operator: provisioning ---------------------------------------------
class ProvisionView(APIView):
    permission_classes = [IsOperator]

    def post(self, request):
        data = request.data
        required = ["name", "code", "county", "plan", "admin_first_name", "admin_last_name"]
        missing = [f for f in required if not data.get(f)]
        if missing:
            raise ValidationError({"detail": f"Missing: {', '.join(missing)}"})

        plan = Plan.objects.filter(pk=data["plan"], is_active=True).first()
        if plan is None:
            raise ValidationError({"plan": "Unknown or inactive plan."})
        if School.objects.filter(code__iexact=data["code"]).exists():
            raise ValidationError({"code": "A school with this code already exists."})

        # Optional school detail — passed straight through to the School row.
        # Blank strings are fine; the model fields all allow blank.
        optional = {
            field: data.get(field, "")
            for field in (
                "kemis_code", "subcounty", "ward", "zone",
                "category", "gender", "accommodation", "ownership",
            )
        }
        optional["levels"] = School.normalize_levels(data.get("levels") or [])

        school, admin, subscription, generated = provision_school(
            name=data["name"],
            code=data["code"],
            county=data["county"],
            plan=plan,
            operator=request.user,
            admin_first_name=data["admin_first_name"],
            admin_last_name=data["admin_last_name"],
            admin_username=data.get("admin_username", ""),
            admin_password=data.get("admin_password", ""),
            admin_phone=data.get("admin_phone", ""),
            admin_email=data.get("admin_email", ""),
            **optional,
        )
        body = {
            "school": {"id": school.id, "name": school.name, "code": school.code},
            "admin": {"username": admin.username, "name": admin.get_full_name()},
            "subscription": SubscriptionSerializer(subscription).data,
        }
        if generated:
            body["admin"]["generated_password"] = generated
        return Response(body, status=201)


# --- Operator: managing a school after it is live ----------------------
class OperatorSchoolView(APIView):
    """GET/PATCH /api/platform/schools/<pk>/ — the school's profile, contact,
    and admin account(s), plus its subscription standing.

    Strictly the control plane: profile metadata, the admin contacts the
    operator uses to reach the school, and billing. No learner, guardian, staff
    or assessment data ever passes through here — that stays inside the tenant.
    """

    permission_classes = [IsOperator]

    # What the operator may correct after registration. Deliberately excludes
    # anything that would touch the tenant's own data.
    EDITABLE = {
        "name", "code", "kemis_code", "levels", "county", "subcounty", "ward",
        "zone", "category", "gender", "accommodation", "ownership",
        "contact_phone", "contact_email", "paybill_account_prefix",
    }

    def _get(self, pk):
        school = School.objects.filter(pk=pk).first()
        if school is None:
            raise NotFound("No such school.")
        return school

    def get(self, request, pk):
        school = self._get(pk)
        admins = school.users.filter(role=User.Role.ADMIN).order_by(
            "-is_active", "username"
        )
        sub = getattr(school, "subscription", None)
        return Response({
            "school": SchoolSerializer(school).data,
            "admins": [_admin_dict(u) for u in admins],
            "subscription": SubscriptionSerializer(sub).data if sub else None,
        })

    def patch(self, request, pk):
        school = self._get(pk)
        data = {k: v for k, v in request.data.items() if k in self.EDITABLE}
        if not data:
            raise ValidationError({"detail": "No editable fields supplied."})
        serializer = SchoolSerializer(school, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        audit(
            actor=request.user, school=school, action="SCHOOL_UPDATED",
            target=school, label=school.name, detail={"fields": sorted(data)},
        )
        return Response(SchoolSerializer(school).data)


class OperatorSchoolAdminView(APIView):
    """POST /api/platform/schools/<pk>/admin/ — replace the school's admin.

    Creates the new admin and deactivates whoever held the role before, so the
    school ends up with exactly one active key-holder. The one-time password is
    returned for handover.
    """

    permission_classes = [IsOperator]

    def post(self, request, pk):
        school = School.objects.filter(pk=pk).first()
        if school is None:
            raise NotFound("No such school.")
        first = (request.data.get("first_name") or "").strip()
        last = (request.data.get("last_name") or "").strip()
        if not first or not last:
            raise ValidationError(
                {"detail": "first_name and last_name are required."}
            )
        try:
            admin, generated = replace_school_admin(
                school=school,
                operator=request.user,
                first_name=first,
                last_name=last,
                phone=(request.data.get("phone") or "").strip(),
                email=(request.data.get("email") or "").strip(),
                username=(request.data.get("username") or "").strip(),
            )
        except ValueError as exc:
            raise ValidationError({"username": str(exc)})
        return Response(
            {"admin": _admin_dict(admin), "generated_password": generated},
            status=201,
        )


class OperatorAdminMemberView(APIView):
    """PATCH /api/platform/schools/<pk>/admin/<uid>/ — correct an admin's
    contact details, or activate/deactivate the account."""

    permission_classes = [IsOperator]
    FIELDS = {"first_name", "last_name", "phone", "email", "is_active"}

    def _target(self, pk, uid):
        user = User.objects.filter(
            pk=uid, school_id=pk, role=User.Role.ADMIN
        ).first()
        if user is None:
            raise NotFound("No such admin for this school.")
        if user.is_superuser:
            raise PermissionDenied("A platform superuser is not managed here.")
        return user

    def patch(self, request, pk, uid):
        user = self._target(pk, uid)
        for field in self.FIELDS:
            if field in request.data:
                setattr(user, field, request.data[field])
        user.save()
        return Response(_admin_dict(user))


class OperatorAdminResetView(APIView):
    """POST /api/platform/schools/<pk>/admin/<uid>/reset-password/ — issue a
    fresh handover password for a locked-out admin."""

    permission_classes = [IsOperator]

    def post(self, request, pk, uid):
        user = User.objects.filter(
            pk=uid, school_id=pk, role=User.Role.ADMIN
        ).first()
        if user is None:
            raise NotFound("No such admin for this school.")
        if user.is_superuser:
            raise PermissionDenied("A platform superuser's password is not reset here.")
        password = reset_admin_password(admin=user, operator=request.user)
        return Response({
            "username": user.username,
            "name": user.get_full_name() or user.username,
            "generated_password": password,
            "detail": "Hand this over now — it is not shown again.",
        })


class OperatorOverviewView(APIView):
    """GET /api/platform/overview/ — the operator's front page."""

    permission_classes = [IsOperator]

    def get(self, request):
        from django.db.models import Count, Q, Sum

        subs = Subscription.objects.select_related("school", "plan").all()
        by_state = {}
        for sub in subs:
            by_state[sub.effective_state()] = by_state.get(sub.effective_state(), 0) + 1

        unpaid = SubscriptionInvoice.objects.filter(
            status=SubscriptionInvoice.Status.SENT
        )
        return Response(
            {
                "schools": subs.count(),
                "by_state": by_state,
                "outstanding_invoices": unpaid.count(),
                "outstanding_amount": str(
                    unpaid.aggregate(t=Sum("amount"))["t"] or 0
                ),
                "learners_total": School.objects.aggregate(
                    n=Count("learners", filter=Q(learners__active=True))
                )["n"],
            }
        )


# --- Operator: announcements --------------------------------------------
class AnnouncementSerializer(serializers.ModelSerializer):
    category_label = serializers.CharField(source="get_category_display", read_only=True)

    class Meta:
        model = PlatformAnnouncement
        fields = "__all__"
        read_only_fields = ["created_by"]


class AnnouncementViewSet(viewsets.ModelViewSet):
    queryset = PlatformAnnouncement.objects.all()
    serializer_class = AnnouncementSerializer
    permission_classes = [IsOperator]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


# --- Tenant side: a school admin's own standing -------------------------
class MySchoolSubscriptionView(APIView):
    """GET /api/my-school/subscription/ — what my school owes and its standing."""

    def get(self, request):
        user = request.user
        if not (user.is_superuser or user.role == "ADMIN"):
            raise PermissionDenied("Only the school admin can see the subscription.")
        if user.school_id is None:
            raise PermissionDenied("This account is not attached to a school.")

        sub = getattr(user.school, "subscription", None)
        if sub is None:
            return Response({"subscription": None, "invoices": []})

        invoices = sub.invoices.exclude(status=SubscriptionInvoice.Status.VOID)
        return Response(
            {
                "subscription": SubscriptionSerializer(sub).data,
                "invoices": InvoiceSerializer(invoices, many=True).data,
            }
        )


class PlatformAnnouncementFeedView(APIView):
    """GET /api/platform-announcements/ — notices addressed to this admin,
    with unread count. POST marks them all seen."""

    def get(self, request):
        user = request.user
        if not (user.is_superuser or user.role == "ADMIN"):
            return Response({"items": [], "unread": 0})

        published = PlatformAnnouncement.objects.filter(published=True)
        seen = set(
            AnnouncementReceipt.objects.filter(user=user).values_list(
                "announcement_id", flat=True
            )
        )
        items = [
            {
                "id": a.id,
                "title": a.title,
                "body": a.body,
                "category": a.category,
                "category_label": a.get_category_display(),
                "link": a.link,
                "at": a.created_at.isoformat(),
                "seen": a.id in seen,
            }
            for a in published[:50]
        ]
        return Response({"items": items, "unread": sum(1 for i in items if not i["seen"])})

    def post(self, request):
        user = request.user
        for a in PlatformAnnouncement.objects.filter(published=True):
            AnnouncementReceipt.objects.get_or_create(announcement=a, user=user)
        return Response({"ok": True})
