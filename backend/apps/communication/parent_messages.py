"""Messages between a parent and the staff who teach their child.

This is the first channel that crosses the staff/parent boundary, so who may
talk to whom is defined narrowly and in one place.

A parent may write to the people responsible for their own child: that child's
class teacher, and the head. Nobody else — not another parent, not a teacher
who does not teach their child, not the kitchen. Staff may reply to any thread
they are part of, and staff who teach a child may open one.

Threads are per (guardian, child, staff member). Keeping the child on the
thread matters: a parent with three children in the school should not have one
undifferentiated conversation, and a teacher needs to know which child is being
discussed before reading a word.
"""

from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.views import SchoolScopedViewSet

from .models import ParentMessage


def staff_for_learner(learner):
    """Who a parent may write to about this child.

    The class teacher, and the head. Kept short on purpose: a parent messaging
    every subject teacher would be a support burden the school did not ask for,
    and the class teacher is the school's own answer to "who do I speak to".
    """
    from apps.students.models import ClassGroup
    from apps.teachers.models import Teacher

    contacts = {}
    group = ClassGroup.objects.filter(
        school=learner.school, grade=learner.grade, stream=learner.stream
    ).select_related("class_teacher__user").first()
    if group and group.class_teacher and group.class_teacher.user_id:
        contacts[group.class_teacher.user_id] = {
            "user_id": group.class_teacher.user_id,
            "name": group.class_teacher.user.get_full_name()
            or group.class_teacher.user.username,
            "role": "Class teacher",
        }
    for head in Teacher.objects.filter(
        school=learner.school, rank__in=["HEAD", "DEPUTY"], user__is_active=True
    ).select_related("user"):
        contacts.setdefault(
            head.user_id,
            {
                "user_id": head.user_id,
                "name": head.user.get_full_name() or head.user.username,
                "role": head.get_rank_display(),
            },
        )
    return list(contacts.values())


def guardian_of(user):
    return getattr(user, "guardian_profile", None)


def may_use_thread(user, *, learner, guardian, staff_id):
    """Can this account read or write this thread?"""
    if user.is_superuser or user.role == "ADMIN":
        return True

    own_guardian = guardian_of(user)
    if own_guardian is not None:
        # A parent: must be their guardian record, their child, and a staff
        # member the school lists for that child.
        return (
            own_guardian.id == guardian.id
            and guardian.learners.filter(pk=learner.pk).exists()
            and staff_id in {c["user_id"] for c in staff_for_learner(learner)}
        )

    # Staff: their own threads, or a child they are listed for.
    if user.id == staff_id:
        return True
    return user.id in {c["user_id"] for c in staff_for_learner(learner)}


class ParentMessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.SerializerMethodField()
    learner_name = serializers.CharField(source="learner.full_name", read_only=True)
    from_parent = serializers.BooleanField(read_only=True)

    class Meta:
        model = ParentMessage
        fields = [
            "id", "learner", "learner_name", "guardian", "staff", "sender",
            "sender_name", "body", "read_at", "created_at", "from_parent",
        ]
        read_only_fields = ["school", "sender", "read_at"]

    def get_sender_name(self, obj):
        return obj.sender.get_full_name() or obj.sender.username


class ParentMessageViewSet(SchoolScopedViewSet):
    queryset = ParentMessage.objects.select_related(
        "learner", "guardian", "staff", "sender"
    ).all()
    serializer_class = ParentMessageSerializer
    filterset_fields = ["learner", "staff", "guardian"]

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()
        if user.is_superuser or user.role == "ADMIN":
            return qs
        guardian = guardian_of(user)
        if guardian is not None:
            return qs.filter(guardian=guardian)
        return qs.filter(Q(staff=user) | Q(sender=user))

    def perform_create(self, serializer):
        user = self.request.user
        learner = serializer.validated_data["learner"]
        guardian = serializer.validated_data["guardian"]
        staff_id = serializer.validated_data["staff"].id

        if learner.school_id != user.school_id or guardian.school_id != user.school_id:
            raise PermissionDenied("That learner belongs to another school.")
        if not guardian.learners.filter(pk=learner.pk).exists():
            raise ValidationError(
                {"guardian": "That guardian is not recorded for this learner."}
            )
        if not may_use_thread(user, learner=learner, guardian=guardian, staff_id=staff_id):
            raise PermissionDenied(
                "You can only message about your own child, and only the staff "
                "the school lists for that child."
            )
        serializer.save(school=user.school, sender=user)


class ParentThreadsView(APIView):
    """GET /api/parent/threads/ — a parent's conversations, one per child+staff."""

    def get(self, request):
        guardian = guardian_of(request.user)
        if guardian is None:
            raise PermissionDenied("This account is not linked to a guardian profile.")

        threads = []
        for learner in guardian.learners.filter(active=True):
            for contact in staff_for_learner(learner):
                messages = ParentMessage.objects.filter(
                    guardian=guardian, learner=learner, staff_id=contact["user_id"]
                ).select_related("sender")
                last = messages.last()
                threads.append(
                    {
                        "learner": learner.id,
                        "learner_name": learner.full_name,
                        # The client posts back with these three ids.
                        "guardian": guardian.id,
                        "staff": contact["user_id"],
                        "staff_name": contact["name"],
                        "staff_role": contact["role"],
                        "messages": ParentMessageSerializer(messages, many=True).data,
                        "unread": messages.filter(
                            read_at__isnull=True
                        ).exclude(sender=request.user).count(),
                        "last_at": last.created_at if last else None,
                    }
                )
        # Most recent conversation first, and threads nobody has used yet last.
        # A single reverse=True sort flips *both* keys and floats the empty
        # threads to the top, burying the conversation the parent just had.
        active = sorted(
            (t for t in threads if t["last_at"]), key=lambda t: t["last_at"], reverse=True
        )
        threads = active + [t for t in threads if not t["last_at"]]

        # Opening the list marks what staff sent as seen.
        ParentMessage.objects.filter(
            guardian=guardian, read_at__isnull=True
        ).exclude(sender=request.user).update(read_at=timezone.now())

        return Response(
            {
                "guardian_id": guardian.id,
                "guardian": guardian.full_name,
                "threads": threads,
            }
        )


class StaffThreadsView(APIView):
    """GET /api/staff/parent-threads/ — parents writing to this staff member."""

    def get(self, request):
        user = request.user
        if guardian_of(user) is not None:
            raise PermissionDenied("Use /api/parent/threads/ instead.")

        rows = (
            ParentMessage.objects.filter(school=user.school, staff=user)
            .select_related("learner", "guardian", "sender")
            .order_by("learner_id", "guardian_id", "created_at")
        )
        threads = {}
        for message in rows:
            key = (message.learner_id, message.guardian_id)
            threads.setdefault(
                key,
                {
                    "learner": message.learner_id,
                    "learner_name": message.learner.full_name,
                    "guardian": message.guardian_id,
                    "guardian_name": message.guardian.full_name,
                    "guardian_phone": message.guardian.phone,
                    "messages": [],
                    "unread": 0,
                },
            )
            thread = threads[key]
            thread["messages"].append(ParentMessageSerializer(message).data)
            if message.read_at is None and message.sender_id != user.id:
                thread["unread"] += 1

        ParentMessage.objects.filter(
            school=user.school, staff=user, read_at__isnull=True
        ).exclude(sender=user).update(read_at=timezone.now())

        return Response({"threads": list(threads.values())})


class LearnerContactsView(APIView):
    """GET /api/learners/<id>/contacts/ — who a parent may write to about a child."""

    def get(self, request, learner_id):
        from apps.students.models import Learner

        learner = Learner.objects.filter(
            school=request.user.school, pk=learner_id
        ).first()
        if learner is None:
            return Response({"detail": "Learner not found."}, status=404)

        guardian = guardian_of(request.user)
        if guardian is not None and not guardian.learners.filter(pk=learner.pk).exists():
            raise PermissionDenied("You can only see contacts for your own child.")
        return Response({"learner": learner.full_name, "contacts": staff_for_learner(learner)})
