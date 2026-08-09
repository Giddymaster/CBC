"""Each staff member's own view: what they do, who they report to, and the
reports flowing up or down that line.

One endpoint serves teaching and non-teaching staff alike — the payload just
carries whichever responsibilities apply to them.
"""

from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.images import downscale_photo
from apps.common.views import SchoolScopedViewSet

from .models import Duty, StaffReport, SupportStaff, Teacher


def _initials(name):
    parts = [p for p in (name or "").split() if p]
    return "".join(p[0].upper() for p in parts[:2]) or "?"


def _person(user, request=None):
    """A supervisor/colleague card: name, what they do, and how to reach them."""
    if user is None:
        return None
    kind, profile = _staff_profile(user)
    title = ""
    photo = None
    if profile is not None:
        title = (
            profile.get_rank_display() if kind == "TEACHING"
            else (profile.title or profile.get_category_display())
        )
        if profile.photo:
            photo = request.build_absolute_uri(profile.photo.url) if request else profile.photo.url
    name = user.get_full_name() or user.username
    return {
        "id": user.id,
        "name": name,
        "initials": _initials(name),
        "title": title,
        "role": user.role,
        "phone": user.phone,
        "email": user.email,
        "photo": photo,
    }


def _staff_profile(user):
    """The teacher or support-staff record behind this login, if any."""
    teacher = getattr(user, "teacher_profile", None)
    if teacher is not None:
        return "TEACHING", teacher
    support = getattr(user, "support_profile", None)
    if support is not None:
        return "NON_TEACHING", support
    return None, None


class StaffReportSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source="author.get_full_name", read_only=True)
    reviewed_by_name = serializers.CharField(
        source="reviewed_by.get_full_name", read_only=True, default=None
    )

    class Meta:
        model = StaffReport
        fields = "__all__"
        read_only_fields = [
            "school", "author", "supervisor", "status", "submitted_at",
            "reviewed_by", "reviewed_at", "review_comment",
        ]


class StaffReportViewSet(SchoolScopedViewSet):
    """Staff write their own reports; supervisors and admins review them."""

    queryset = StaffReport.objects.select_related("author", "supervisor", "reviewed_by").all()
    serializer_class = StaffReportSerializer
    filterset_fields = ["status", "author"]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_superuser or user.role == "ADMIN":
            return qs
        # Everyone else sees their own reports plus anything they must review.
        return qs.filter(author=user) | qs.filter(supervisor=user)

    def perform_create(self, serializer):
        user = self.request.user
        _, profile = _staff_profile(user)
        if profile is None:
            raise PermissionDenied("Only staff members file reports.")
        serializer.save(
            school=user.school, author=user, supervisor=profile.supervisor
        )

    def perform_update(self, serializer):
        report = self.get_object()
        if report.author_id != self.request.user.id:
            raise PermissionDenied("You can only edit your own reports.")
        if report.status == StaffReport.Status.APPROVED:
            raise PermissionDenied("An approved report can no longer be edited.")
        serializer.save()

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        report = self.get_object()
        if report.author_id != request.user.id:
            raise PermissionDenied("You can only submit your own reports.")

        _, profile = _staff_profile(request.user)
        supervisor = profile.supervisor if profile else None
        if supervisor is None:
            return Response(
                {"detail": "You have no supervisor set — ask the admin to assign one."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        report.supervisor = supervisor
        report.status = StaffReport.Status.SUBMITTED
        report.submitted_at = timezone.now()
        report.review_comment = ""
        report.save()
        return Response(StaffReportSerializer(report, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def review(self, request, pk=None):
        report = self.get_object()
        user = request.user
        is_admin = user.is_superuser or user.role == "ADMIN"
        if not is_admin and report.supervisor_id != user.id:
            raise PermissionDenied("Only this report's supervisor can review it.")
        if report.status != StaffReport.Status.SUBMITTED:
            return Response(
                {"detail": "Only a submitted report can be reviewed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        decision = request.data.get("decision")
        if decision not in ("approve", "return"):
            return Response({"detail": "decision must be approve or return."}, status=400)

        report.status = (
            StaffReport.Status.APPROVED if decision == "approve"
            else StaffReport.Status.RETURNED
        )
        report.reviewed_by = user
        report.reviewed_at = timezone.now()
        report.review_comment = request.data.get("comment", "")
        report.save()

        from apps.common.audit import record as audit

        audit(
            actor=user,
            school=report.school,
            action="REPORT_REVIEWED",
            target=report,
            label=f"{report.title} — {report.author.get_full_name() or report.author.username}",
            detail={"decision": decision, "comment": report.review_comment},
        )
        return Response(StaffReportSerializer(report, context={"request": request}).data)


class DutySerializer(serializers.ModelSerializer):
    staff_name = serializers.CharField(source="user.get_full_name", read_only=True)

    class Meta:
        model = Duty
        fields = "__all__"
        read_only_fields = ["school"]


# Every hat a school hands out, for the Task Hub. Not a cage — leadership can
# assign any custom title too — but the common ones should be one click away.
TASK_CATALOG = {
    "teaching": [
        "Games Master", "Games Teacher", "Teacher on Duty (TOD)",
        "Exams Coordinator", "Timetable Master",
        "HOD Languages", "HOD Mathematics", "HOD Sciences",
        "HOD Humanities", "HOD Creative Arts", "HOD Pre-Technical",
        "Guidance and Counselling", "Library In-charge",
        "Laboratory In-charge", "ICT Champion", "Environment Master",
        "Sanitation Master", "Clubs and Societies Patron",
        "Drama and Music Patron", "Scouts and Guides Patron",
        "CU / Chaplaincy Patron", "First Aid Coordinator", "Fire Marshal",
        "School Meals Coordinator", "Boarding Master", "Sports Coach",
    ],
    "non_teaching": [
        "Head Cook", "Cook", "Kitchen Hand",
        "Day Security - Main Gate", "Day Security - Back Gate",
        "Night Security", "Bus Driver", "Van Driver",
        "Store Keeper", "Cashier", "Groundsman", "Cleaner In-charge",
        "Maintenance / Electrician", "Copy Typist",
    ],
}


class DutyCatalogView(APIView):
    """GET /api/duties/catalog/ — the school's task list for the Task Hub.
    Class Teacher is listed as special: it seats through the class group,
    not a duty row."""

    def get(self, request):
        return Response({
            **TASK_CATALOG,
            "special": [{
                "key": "class_teacher",
                "title": "Class Teacher",
                "note": "Seated per class (grade and stream); drives the "
                        "attendance register.",
            }],
        })


class DutyViewSet(SchoolScopedViewSet):
    queryset = Duty.objects.select_related("user").all()
    serializer_class = DutySerializer
    filterset_fields = ["user"]

    def _require_admin(self):
        # Leadership hands out the hats: the office, head teacher or deputy.
        from .daily import _require_office

        _require_office(self.request.user)

    def perform_create(self, serializer):
        self._require_admin()
        super().perform_create(serializer)

    def perform_update(self, serializer):
        self._require_admin()
        serializer.save()

    def perform_destroy(self, instance):
        self._require_admin()
        instance.delete()


class MyPhotoView(APIView):
    """POST /api/my-portal/photo/ — staff set their own profile picture."""

    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        _, profile = _staff_profile(request.user)
        if profile is None:
            raise PermissionDenied("This account has no staff profile.")
        photo = request.FILES.get("photo")
        if photo is None:
            return Response({"detail": "Attach a photo."}, status=status.HTTP_400_BAD_REQUEST)
        profile.photo = downscale_photo(photo)
        profile.save(update_fields=["photo", "updated_at"])
        return Response({"photo": request.build_absolute_uri(profile.photo.url)})

    def delete(self, request):
        _, profile = _staff_profile(request.user)
        if profile is None:
            raise PermissionDenied("This account has no staff profile.")
        profile.photo = None
        profile.save(update_fields=["photo", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class MyPortalView(APIView):
    """GET /api/my-portal/ — the signed-in staff member's own dashboard."""

    def get(self, request):
        user = request.user
        kind, profile = _staff_profile(user)
        if profile is None:
            raise PermissionDenied("This account has no staff profile.")

        school = user.school
        from apps.facilities.models import FacilityAssignment
        from apps.students.models import ClassGroup, Learner
        from apps.timetable.models import LessonRequirement

        # --- What they do -------------------------------------------------
        responsibilities = {"class_teacher_of": [], "lessons": [], "facilities": [], "duties": []}

        if kind == "TEACHING":
            for group in ClassGroup.objects.filter(class_teacher=profile):
                responsibilities["class_teacher_of"].append(
                    {
                        "label": str(group),
                        "grade": group.grade,
                        "stream": group.stream,
                        "learners": Learner.objects.filter(
                            school=school, grade=group.grade, stream=group.stream, active=True
                        ).count(),
                    }
                )
            for req in LessonRequirement.objects.filter(teacher=profile).select_related(
                "learning_area"
            ):
                responsibilities["lessons"].append(
                    {
                        "subject": req.learning_area.name,
                        "grade": req.grade,
                        "stream": req.stream,
                        "lessons_per_week": req.lessons_per_week,
                    }
                )

        assignment_filter = (
            {"teacher": profile} if kind == "TEACHING" else {"support_staff": profile}
        )
        for assignment in FacilityAssignment.objects.filter(
            **assignment_filter
        ).select_related("facility__category"):
            facility = assignment.facility
            supplies = list(facility.supplies.all())
            responsibilities["facilities"].append(
                {
                    "id": facility.id,
                    "facility": facility.name,
                    "category": facility.category.name,
                    "position": assignment.position,
                    "supplies_total": len(supplies),
                    "supplies_depleted": [s.item for s in supplies if s.status == "DEPLETED"],
                    "supplies_low": [s.item for s in supplies if s.status == "LOW"],
                }
            )

        responsibilities["duties"] = [
            {"id": d.id, "title": d.title, "description": d.description}
            for d in user.duties.all()
        ]

        # --- Reporting line ----------------------------------------------
        supervises = [
            _person(t.user, request)
            for t in Teacher.objects.filter(supervisor=user).select_related("user")
        ] + [
            _person(s.user, request)
            for s in SupportStaff.objects.filter(supervisor=user).select_related("user")
            if s.user_id
        ]

        mine = StaffReport.objects.filter(author=user)
        to_review = StaffReport.objects.filter(
            supervisor=user, status=StaffReport.Status.SUBMITTED
        ).select_related("author")

        from .models import StaffMessage, StaffTask
        from .supervision import rank_level, scope_label, visible_staff_ids
        from .team import StaffTaskSerializer

        my_tasks = StaffTask.objects.filter(assigned_to=user).select_related("assigned_by")
        # The team is people, not accounts: non-teaching staff without a
        # portal login still count (the team page lists them too).
        from .supervision import SCOPE_WHOLE_SCHOOL

        no_login = SupportStaff.objects.filter(
            school=school, active=True, user__isnull=True
        )
        if rank_level(user) < SCOPE_WHOLE_SCHOOL:
            no_login = no_login.filter(supervisor=user)
        team_size = len(visible_staff_ids(user)) + no_login.count()

        return Response(
            {
                "me": {
                    "name": user.get_full_name() or user.username,
                    "initials": _initials(user.get_full_name() or user.username),
                    "username": user.username,
                    "role": user.role,
                    "kind": kind,
                    "kind_label": "Teaching staff" if kind == "TEACHING" else "Non-teaching staff",
                    "title": (
                        profile.get_rank_display() if kind == "TEACHING"
                        else (profile.title or profile.get_category_display())
                    ),
                    "department": (
                        "Teaching" if kind == "TEACHING" else profile.get_category_display()
                    ),
                    "employment": profile.get_employment_type_display(),
                    "staff_no": profile.tsc_number if kind == "TEACHING" else "",
                    "phone": user.phone,
                    "email": user.email,
                    "school": school.name if school else "",
                    "photo": (
                        request.build_absolute_uri(profile.photo.url) if profile.photo else None
                    ),
                    "joined": profile.created_at.date().isoformat(),
                },
                "supervisor": _person(profile.supervisor, request),
                "supervises": supervises,
                "team": {
                    "size": team_size,
                    "scope": scope_label(user),
                    "rank_level": rank_level(user),
                },
                "my_tasks": StaffTaskSerializer(
                    my_tasks, many=True, context={"request": request}
                ).data,
                "unread_messages": StaffMessage.objects.filter(
                    recipient=user, read_at__isnull=True
                ).count(),
                "responsibilities": responsibilities,
                "reports": {
                    "mine": StaffReportSerializer(
                        mine, many=True, context={"request": request}
                    ).data,
                    "to_review": StaffReportSerializer(
                        to_review, many=True, context={"request": request}
                    ).data,
                },
            }
        )
