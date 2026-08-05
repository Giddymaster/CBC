"""Staff directory for the admin: teaching staff grouped by employment type
(TSC / PNP / BOM / PTA) with ranks, and non-teaching staff by category."""

import secrets

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.views import SchoolScopedViewSet
from apps.timetable.models import LessonRequirement

from .models import StaffField, SupportStaff, Teacher, TeacherAttendance

User = get_user_model()


def require_admin(user):
    if not (user.is_superuser or user.role == "ADMIN"):
        raise PermissionDenied("Only the school admin can change staff records.")


def _valid_supervisor(supervisor_id, *, school, exclude_user_id=None):
    """A supervisor must be a real staff login in this school, and nobody may
    be set as their own supervisor — that would be an unreviewable report line."""
    if supervisor_id in (None, ""):
        return None
    if exclude_user_id is not None and int(supervisor_id) == int(exclude_user_id):
        raise serializers.ValidationError(
            {"supervisor": "A staff member cannot be their own supervisor."}
        )
    exists = (
        Teacher.objects.filter(user_id=supervisor_id, school=school).exists()
        or SupportStaff.objects.filter(user_id=supervisor_id, school=school).exists()
    )
    if not exists:
        raise serializers.ValidationError(
            {"supervisor": "Choose a staff member of this school."}
        )
    return int(supervisor_id)


class StaffFieldSerializer(serializers.ModelSerializer):
    class Meta:
        model = StaffField
        fields = "__all__"
        read_only_fields = ["school", "key"]

    def create(self, validated_data):
        # Derive a stable key from the label; keep it unique within the school.
        from django.utils.text import slugify

        base = slugify(validated_data["label"]).replace("-", "_") or "field"
        key, n = base, 1
        school = validated_data["school"]
        while StaffField.objects.filter(school=school, key=key).exists():
            n += 1
            key = f"{base}_{n}"
        validated_data["key"] = key
        return super().create(validated_data)


class StaffFieldViewSet(SchoolScopedViewSet):
    """Admin-defined extra columns on the staff register."""

    queryset = StaffField.objects.all()
    serializer_class = StaffFieldSerializer
    filterset_fields = ["applies_to"]

    def perform_create(self, serializer):
        require_admin(self.request.user)
        super().perform_create(serializer)

    def perform_update(self, serializer):
        require_admin(self.request.user)
        serializer.save()

    def perform_destroy(self, instance):
        require_admin(self.request.user)
        instance.delete()


class SupportStaffSerializer(serializers.ModelSerializer):
    category_label = serializers.CharField(source="get_category_display", read_only=True)
    employment_label = serializers.CharField(
        source="get_employment_type_display", read_only=True
    )
    username = serializers.CharField(source="user.username", read_only=True, default=None)
    supervisor_name = serializers.CharField(
        source="supervisor.get_full_name", read_only=True, default=None
    )

    class Meta:
        model = SupportStaff
        fields = "__all__"
        read_only_fields = ["school"]

    def validate(self, attrs):
        supervisor = attrs.get("supervisor")
        user = attrs.get("user") or getattr(self.instance, "user", None)
        if supervisor is not None and user is not None and supervisor.id == user.id:
            raise serializers.ValidationError(
                {"supervisor": "A staff member cannot be their own supervisor."}
            )
        return attrs


class SupportStaffViewSet(SchoolScopedViewSet):
    queryset = SupportStaff.objects.select_related("user", "supervisor").all()
    serializer_class = SupportStaffSerializer
    filterset_fields = ["category", "employment_type", "active"]
    search_fields = ["full_name", "title"]

    @action(detail=True, methods=["post"], url_path="create-login")
    def create_login(self, request, pk=None):
        """Give a non-teaching staff member a portal login."""
        require_admin(request.user)
        staff = self.get_object()
        if staff.user_id:
            return Response(
                {"detail": f"{staff.full_name} already has the login '{staff.user.username}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        base = (request.data.get("username") or staff.full_name.split(" ")[0]).strip().lower()
        base = "".join(ch for ch in base if ch.isalnum()) or "staff"
        username, n = base, 1
        while User.objects.filter(username=username).exists():
            n += 1
            username = f"{base}{n}"

        password = request.data.get("password") or secrets.token_urlsafe(8)
        first, _, last = staff.full_name.partition(" ")
        account = User.objects.create_user(
            username=username, password=password, first_name=first, last_name=last,
            role="SUPPORT", school=request.user.school, phone=staff.phone,
        )
        staff.user = account
        staff.save(update_fields=["user", "updated_at"])
        return Response(
            {"username": username, "generated_password": password, "name": staff.full_name},
            status=status.HTTP_201_CREATED,
        )

    def perform_create(self, serializer):
        require_admin(self.request.user)
        super().perform_create(serializer)

    def perform_update(self, serializer):
        require_admin(self.request.user)
        serializer.save()

    def perform_destroy(self, instance):
        # Staff records are kept for history — deactivate instead of deleting.
        require_admin(self.request.user)
        instance.active = False
        instance.save(update_fields=["active", "updated_at"])


class AddTeacherSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=50)
    last_name = serializers.CharField(max_length=50)
    tsc_number = serializers.CharField(max_length=20)
    employment_type = serializers.ChoiceField(choices=Teacher.EmploymentType.choices)
    rank = serializers.ChoiceField(
        choices=Teacher.Rank.choices, default=Teacher.Rank.TEACHER
    )
    phone = serializers.CharField(max_length=15, allow_blank=True, default="")
    username = serializers.CharField(max_length=150, allow_blank=True, default="")
    password = serializers.CharField(allow_blank=True, default="", write_only=True)
    supervisor = serializers.IntegerField(required=False, allow_null=True)


class AddTeacherView(APIView):
    """POST /api/school/staff/add-teacher/ (admin only).

    Creates the portal user account (role TEACHER) and the teacher profile in
    one step. If no username/password is supplied, they are generated and the
    password is returned once so the admin can hand it over.
    """

    def post(self, request):
        user = request.user
        if not (user.is_superuser or user.role == "ADMIN"):
            raise PermissionDenied("Only the school admin can add staff.")

        params = AddTeacherSerializer(data=request.data)
        params.is_valid(raise_exception=True)
        data = params.validated_data

        if Teacher.objects.filter(tsc_number__iexact=data["tsc_number"]).exists():
            raise serializers.ValidationError(
                {"tsc_number": "A teacher with this TSC/payroll number already exists."}
            )

        username = data["username"].strip().lower()
        if not username:
            base = (data["first_name"] or "teacher").strip().lower().replace(" ", "")
            username, n = base, 1
            while User.objects.filter(username=username).exists():
                n += 1
                username = f"{base}{n}"
        elif User.objects.filter(username=username).exists():
            raise serializers.ValidationError({"username": "Username already taken."})

        password = data["password"] or secrets.token_urlsafe(8)
        account = User.objects.create_user(
            username=username,
            password=password,
            first_name=data["first_name"],
            last_name=data["last_name"],
            role="TEACHER",
            school=user.school,
            phone=data["phone"],
        )
        teacher = Teacher.objects.create(
            school=user.school,
            user=account,
            tsc_number=data["tsc_number"],
            employment_type=data["employment_type"],
            rank=data["rank"],
            supervisor_id=_valid_supervisor(
                data.get("supervisor"), school=user.school, exclude_user_id=account.id
            ),
        )
        body = {
            "id": teacher.id,
            "name": account.get_full_name(),
            "username": username,
            "tsc_number": teacher.tsc_number,
            "employment_type": teacher.employment_type,
            "rank": teacher.rank,
        }
        if not data["password"]:
            body["generated_password"] = password  # shown once, then only hashes exist
        return Response(body, status=status.HTTP_201_CREATED)


class EditTeacherSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=50, required=False)
    last_name = serializers.CharField(max_length=50, required=False)
    tsc_number = serializers.CharField(max_length=20, required=False)
    employment_type = serializers.ChoiceField(
        choices=Teacher.EmploymentType.choices, required=False
    )
    rank = serializers.ChoiceField(choices=Teacher.Rank.choices, required=False)
    phone = serializers.CharField(max_length=15, allow_blank=True, required=False)
    active = serializers.BooleanField(required=False)
    extra = serializers.DictField(required=False)
    supervisor = serializers.IntegerField(required=False, allow_null=True)


class EditTeacherView(APIView):
    """PATCH /api/school/staff/teachers/<id>/ — edit or deactivate a teacher.

    Deactivating (`active: false`) disables the portal login but keeps the
    record, its schemes of work and its history intact.
    """

    def patch(self, request, teacher_id):
        require_admin(request.user)
        teacher = (
            Teacher.objects.filter(school=request.user.school)
            .select_related("user")
            .filter(pk=teacher_id)
            .first()
        )
        if teacher is None:
            return Response({"detail": "Teacher not found."}, status=status.HTTP_404_NOT_FOUND)

        params = EditTeacherSerializer(data=request.data, partial=True)
        params.is_valid(raise_exception=True)
        data = params.validated_data

        if "tsc_number" in data:
            clash = Teacher.objects.filter(tsc_number__iexact=data["tsc_number"]).exclude(
                pk=teacher.pk
            )
            if clash.exists():
                raise serializers.ValidationError(
                    {"tsc_number": "Another teacher already has this TSC/payroll number."}
                )
            teacher.tsc_number = data["tsc_number"]

        for field in ("employment_type", "rank"):
            if field in data:
                setattr(teacher, field, data[field])
        if "extra" in data:
            teacher.extra = {**(teacher.extra or {}), **data["extra"]}
        if "supervisor" in data:
            teacher.supervisor_id = _valid_supervisor(
                data["supervisor"], school=request.user.school,
                exclude_user_id=teacher.user_id,
            )
        teacher.save()

        account = teacher.user
        for field in ("first_name", "last_name", "phone"):
            if field in data:
                setattr(account, field, data[field])
        if "active" in data:
            account.is_active = data["active"]
        account.save()

        return Response(
            {
                "id": teacher.id,
                "name": account.get_full_name() or account.username,
                "tsc_number": teacher.tsc_number,
                "employment_type": teacher.employment_type,
                "rank": teacher.rank,
                "active": account.is_active,
                "extra": teacher.extra,
            }
        )


class StaffDirectoryView(APIView):
    """GET /api/school/staff/ — the whole staff list, teaching and non-teaching."""

    def get(self, request):
        user = request.user
        if not (user.is_superuser or user.role in ("ADMIN", "TEACHER")):
            raise PermissionDenied("Staff only.")
        school = user.school
        today = timezone.localdate()

        present = {
            a.teacher_id: a.status
            for a in TeacherAttendance.objects.filter(school=school, date=today)
        }
        subjects = {}
        for req in LessonRequirement.objects.filter(school=school).select_related(
            "learning_area"
        ):
            subjects.setdefault(req.teacher_id, set()).add(req.learning_area.name)

        include_inactive = request.query_params.get("include_inactive") == "true"

        teacher_qs = Teacher.objects.filter(school=school).select_related("user", "supervisor")
        if not include_inactive:
            teacher_qs = teacher_qs.filter(user__is_active=True)
        teaching = [
            {
                "id": t.id,
                "name": t.user.get_full_name() or t.user.username,
                "username": t.user.username,
                "tsc_number": t.tsc_number,
                "employment_type": t.employment_type,
                "employment_label": t.get_employment_type_display(),
                "rank": t.rank,
                "rank_label": t.get_rank_display(),
                "phone": t.user.phone,
                "subjects": sorted(subjects.get(t.id, [])),
                "present_today": present.get(t.id),
                "active": t.user.is_active,
                "extra": t.extra or {},
                "user_id": t.user_id,
                "supervisor": t.supervisor_id,
                "supervisor_name": (
                    t.supervisor.get_full_name() or t.supervisor.username
                ) if t.supervisor else None,
            }
            for t in teacher_qs
        ]

        support_qs = SupportStaff.objects.filter(school=school).select_related(
            "user", "supervisor"
        )
        if not include_inactive:
            support_qs = support_qs.filter(active=True)
        non_teaching = SupportStaffSerializer(
            support_qs.order_by("category", "full_name"), many=True
        ).data

        fields = StaffFieldSerializer(
            StaffField.objects.filter(school=school), many=True
        ).data

        return Response(
            {
                "date": today.isoformat(),
                "teaching": teaching,
                "teaching_groups": [
                    {"key": key, "label": label}
                    for key, label in Teacher.EmploymentType.choices
                ],
                "non_teaching": non_teaching,
                "non_teaching_groups": [
                    {"key": key, "label": label}
                    for key, label in SupportStaff.Category.choices
                ],
                "fields": fields,
                # Everyone who could be named as a supervisor.
                "supervisor_choices": [
                    {
                        "id": u_id,
                        "name": name,
                        "kind": kind,
                    }
                    for u_id, name, kind in sorted(
                        [
                            (t.user_id, t.user.get_full_name() or t.user.username, "Teaching")
                            for t in teacher_qs
                        ]
                        + [
                            (s.user_id, s.full_name, "Non-teaching")
                            for s in support_qs
                            if s.user_id
                        ],
                        key=lambda row: row[1],
                    )
                ],
                "employment_choices": {
                    "teaching": [
                        {"value": v, "label": l} for v, l in Teacher.EmploymentType.choices
                    ],
                    "non_teaching": [
                        {"value": v, "label": l} for v, l in SupportStaff.EmploymentType.choices
                    ],
                },
                "rank_choices": [{"value": v, "label": l} for v, l in Teacher.Rank.choices],
                "totals": {
                    "teaching": len(teaching),
                    "non_teaching": len(non_teaching),
                },
            }
        )
